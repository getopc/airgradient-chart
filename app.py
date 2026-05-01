import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
import time
import smtplib
from email.mime.text import MIMEText
import paho.mqtt.client as mqtt

# ==========================================
# 1. 설정값
# ==========================================
DEVICE_IP = "172.30.1.94"
API_URL = "https://api.airgradient.com/public/api/v1/locations/measures/current"
API_TOKEN = "74cf04f0-11c0-4498-9d7f-e191977faeb4"

MIN_HOLD_SECONDS = 300
REFRESH_INTERVAL = 5
FILE_PATH = "data_log.csv"
MQTT_BROKER = "8738ec3a2de44ce7926a5be975e970e3.s1.eu.hivemq.cloud" # 본인의 Cluster URL
MQTT_PORT = 8883  # 클라우드 표준 보안 포트
MQTT_USER = "plug1"
MQTT_PASS = "Ab1234567@"
MQTT_TOPIC_CMD = "cmnd/living_fan/Power"

# ==========================================
# 2. 기본 UI 설정
# ==========================================
st.set_page_config(page_title="스마트 환기 통합 대시보드", layout="wide")
st.title("📡 공기질 + 자동 환기 제어 시스템")

# ==========================================
# 3. 세션 상태 초기화
# ==========================================
if "plug_state" not in st.session_state:
    st.session_state.plug_state = "UNKNOWN"
if "last_changed" not in st.session_state:
    st.session_state.last_changed = time.time() - MIN_HOLD_SECONDS
if "alert_sent" not in st.session_state:
    st.session_state.alert_sent = False

# ==========================================
# 4. 함수 정의
# ==========================================
def control_tasmota_mqtt(cmd):
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        
        # 1. 아이디/비밀번호 설정
        client.username_pw_set(MQTT_USER, MQTT_PASS)
        
        # 2. TLS 보안 설정 (클라우드 접속 필수)
        client.tls_set() 
        
        # 3. 연결 및 발행
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        
        msg = client.publish(MQTT_TOPIC_CMD, cmd, qos=1)
        msg.wait_for_publish()
        
        client.loop_stop()
        client.disconnect()
        return True
    except Exception as e:
        st.error(f"클라우드 MQTT 접속 실패: {e}")
        return False

def fetch_data():
    try:
        res = requests.get(API_URL, params={"token": API_TOKEN}, timeout=5)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        st.sidebar.error(f"API 호출 실패: {e}")
        return None

def send_email_alert(subject, body):
    try:
        sender = "mjjk06162@gmail.com"
        password = st.secrets["GMAIL_PASSWORD"]

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = sender

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, sender, msg.as_string())
    except Exception as e:
        st.sidebar.warning(f"이메일 전송 실패: {e}")

def normalize_history_df(history_df):
    if history_df.empty:
        return history_df

    if "time" in history_df.columns:
        history_df["time"] = pd.to_datetime(history_df["time"], errors="coerce")

    if "PM2.5" not in history_df.columns:
        history_df["PM2.5"] = pd.NA

    pm25_aliases = ["PM2.5", "pm25", "pm2.5", "PM25"]
    for col in pm25_aliases:
        if col in history_df.columns and col != "PM2.5":
            history_df["PM2.5"] = history_df["PM2.5"].fillna(history_df[col])

    drop_cols = [col for col in ["pm25", "pm2.5", "PM25"] if col in history_df.columns]
    if drop_cols:
        history_df = history_df.drop(columns=drop_cols)

    numeric_cols = ["co2", "temp", "humidity", "tvoc", "nox", "pm01", "PM2.5", "pm10"]
    for col in numeric_cols:
        if col in history_df.columns:
            history_df[col] = pd.to_numeric(history_df[col], errors="coerce")

    history_df = history_df.ffill().fillna(0)

    ordered_cols = ["time", "co2", "temp", "humidity", "tvoc", "nox", "pm01", "PM2.5", "pm10"]
    existing_cols = [col for col in ordered_cols if col in history_df.columns]
    remaining_cols = [col for col in history_df.columns if col not in existing_cols]
    history_df = history_df[existing_cols + remaining_cols]

    return history_df

# ==========================================
# 5. 데이터 처리
# ==========================================
data = fetch_data()

if data:
    latest = data[0] if isinstance(data, list) else data
    co2 = latest.get("rco2", 0)

    new_row = {
        "time": datetime.now(),
        "co2": latest.get("rco2"),
        "temp": latest.get("atmp"),
        "humidity": latest.get("rhum"),
        "tvoc": latest.get("tvocIndex"),
        "nox": latest.get("noxIndex"),
        "pm01": latest.get("pm01"),
        "PM2.5": latest.get("pm02"),
        "pm10": latest.get("pm10")
    }

    try:
        history_df = pd.read_csv(FILE_PATH)
    except FileNotFoundError:
        history_df = pd.DataFrame(columns=["time", "co2", "temp", "humidity", "tvoc", "nox", "pm01", "PM2.5", "pm10"])

    history_df = normalize_history_df(history_df)
    history_df = pd.concat([history_df, pd.DataFrame([new_row])], ignore_index=True)
    history_df = normalize_history_df(history_df)
    history_df = history_df.tail(100)
    history_df.to_csv(FILE_PATH, index=False)

    # ==========================================
    # 6. UI
    # ==========================================
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("온도", f"{new_row['temp']} °C")
    m2.metric("습도", f"{new_row['humidity']} %")
    m3.metric("CO2", f"{co2} ppm", delta=f"{co2 - 400} ppm" if co2 > 400 else None, delta_color="inverse")
    m4.metric("PM2.5", f"{new_row['PM2.5']} μg/m³")

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("공기질 지표 (TVOC, PM2.5, NOX)")
        chart_cols = [col for col in ["tvoc", "PM2.5", "nox"] if col in history_df.columns]
    
        # 1. 그래프 생성
        fig1 = px.line(history_df, x="time", y=chart_cols, template="plotly_dark")
    
        # 2. 레이아웃 설정 (축 고정 및 드래그 방지)
        fig1.update_layout(
            xaxis=dict(fixedrange=True), 
            yaxis=dict(fixedrange=True), 
            dragmode=False
        )
    
        # 3. 마지막에 한 번만 출력 (설정값 포함)
        st.plotly_chart(
            fig1, 
            use_container_width=True, 
            config={
                'displayModeBar': False, 
                'scrollZoom': False
            }
        )

    with col2:
        st.subheader("CO2 농도 변화")
        
        # 1. 그래프 생성
        fig2 = px.line(history_df, x="time", y="co2", template="plotly_dark")
        
        # 2. 레이아웃 설정 (축 고정, 드래그 방지)
        fig2.update_layout(
            xaxis=dict(fixedrange=True), 
            yaxis=dict(fixedrange=True),
            dragmode=False
        )
        
        # 3. 마지막에 한 번만 출력 (메뉴바 숨기기, 휠 줌 차단 포함)
        st.plotly_chart(
            fig2, 
            use_container_width=True, 
            config={
                'displayModeBar': False, 
                'scrollZoom': False
            }
        )

    st.subheader("📋 최근 측정 기록 (상세 데이터)")

    # (데이터 전처리 로직은 동일)
    display_df = history_df.copy()
    display_df["time"] = pd.to_datetime(display_df["time"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
    display_df = display_df.sort_values(by="time", ascending=False)
    display_cols = [col for col in ["time", "co2", "temp", "humidity", "tvoc", "nox", "PM2.5"] if col in display_df.columns]
    latest_row = display_df[display_cols].head(1)

    # 1. 데이터 준비
    latest_row = display_df[display_cols].head(1).copy()

    # 2. 특정 컬럼 소수점 1자리로 반올림 (추가된 부분)
    # round(1)은 소수점 첫째 자리까지 남깁니다.
    latest_row["temp"] = latest_row["temp"].astype(float).round(1)
    latest_row["PM2.5"] = latest_row["PM2.5"].astype(float).round(1)

    # 3. 컬럼명 변경
    latest_row.columns = ["측정 시간", "CO2 (ppm)", "온도 (°C)", "습도 (%)", "TVOC", "NOX", "PM2.5"]

    # 4. 출력 (인덱스 숨기기 포함)
    st.table(latest_row.set_index("측정 시간"))


    # ==========================================
    # 7. 자동 제어 로직
    # ==========================================
    st.sidebar.divider()
    st.sidebar.subheader("🛠 제어 시스템 상태")
    st.sidebar.write(f"현재 CO2: {co2} ppm")
    st.sidebar.write(f"현재 플러그 상태: {st.session_state.plug_state}")
    st.sidebar.write(f"마지막 변경 후 경과: {int(elapsed)}초 / {MIN_HOLD_SECONDS}초")
    now = time.time()
    elapsed = now - st.session_state.last_changed

    # 환기 제어 로직
    if elapsed >= MIN_HOLD_SECONDS:
    if co2 >= 800:
        if st.session_state.plug_state != "ON":
            st.sidebar.info("ON 조건 충족! 명령 발송 중...") # 실행 여부 확인용
            if control_tasmota_mqtt("ON"):
                st.session_state.plug_state = "ON"
                st.session_state.last_changed = now
                st.toast("환기 가동!", icon="✅")
            else:
                st.sidebar.error("MQTT 발송 실패!")
        else:
            st.sidebar.write("이미 ON 상태입니다.")
            
    elif co2 < 500:
        if st.session_state.plug_state != "OFF":
            st.sidebar.info("OFF 조건 충족! 명령 발송 중...") # 실행 여부 확인용
            if control_tasmota_mqtt("OFF"):
                st.session_state.plug_state = "OFF"
                st.session_state.last_changed = now
                st.toast("환기 정지", icon="🛑")
            else:
                st.sidebar.error("MQTT 발송 실패!")
        else:
            st.sidebar.write("이미 OFF 상태입니다.")

    # 이메일 알림 로직 (하나로 통합)
    if co2 > 1000:
        st.error(f"🚨 CO2 수치 위험! 현재 {co2}ppm")
        if not st.session_state.alert_sent:
            with st.spinner("📧 경고 메일 발송 중..."):
                send_email_alert("🚨 공기질 위험 경보", f"현재 CO2 수치가 {co2}ppm 입니다.")
                st.session_state.alert_sent = True
    elif co2 < 800:
        st.session_state.alert_sent = False

    # ==========================================
    # 8. 경고 및 이메일 알림 로직
    # ==========================================
    # co2_val 대신 현재 코드에서 정의된 'co2' 변수를 사용합니다.
    if co2 > 1000:
        st.error(f"🚨 실내 이산화탄소 농도 위험! (현재: {co2} ppm)")
        
        # 메일을 아직 안 보냈을 때만 발송 (중복 발송 방지)
        if not st.session_state.alert_sent:
            with st.spinner("📧 경고 이메일을 발송 중입니다..."):
                send_email_alert(
                    "⚠️ [경고] 실내 공기질 위험 알림",
                    f"현재 CO2 농도가 {co2}ppm으로 위험 기준치(1000ppm)를 초과했습니다.\n즉시 환기 시스템을 점검하거나 창문을 열어주세요!"
                )
                st.session_state.alert_sent = True  # 발송 완료 상태로 변경
                st.success("✅ 경고 메일이 성공적으로 발송되었습니다.")
    
    elif co2 < 800:
        # 수치가 800 미만으로 떨어져 안전해지면 발송 가능 상태로 초기화
        if st.session_state.alert_sent:
            st.info("✅ CO2 수치가 정상 범위로 회복되었습니다. 알림 상태가 초기화됩니다.")
            st.session_state.alert_sent = False

    
    # ==========================================
    # 8. 경고 및 알림
    # ==========================================
    if co2 > 1000:
        st.error(f"🚨 CO2 수치 위험! 현재 {co2}ppm - 즉시 환기가 필요합니다.")
        if not st.session_state.alert_sent:
            send_email_alert("🚨 공기질 위험 경보", f"현재 CO2 수치가 {co2}ppm 입니다. 환기 시스템을 확인하세요.")
            st.session_state.alert_sent = True
    elif co2 < 800:
        st.session_state.alert_sent = False

else:
    st.warning("🔄 데이터를 불러오는 중이거나 장치에 연결할 수 없습니다.")

# ==========================================
# 9. 자동 새로고침
# ==========================================
time.sleep(REFRESH_INTERVAL)
st.rerun()
