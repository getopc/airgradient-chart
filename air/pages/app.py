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
API_URL = "https://api.airgradient.com/public/api/v1/locations/measures/current"
API_TOKEN = "74cf04f0-11c0-4498-9d7f-e191977faeb4"
MIN_HOLD_SECONDS = 300
REFRESH_INTERVAL = 5
FILE_PATH = "data_log.csv"
MQTT_BROKER = "8738ec3a2de44ce7926a5be975e970e3.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "plug1"
MQTT_PASS = "Ab1234567@"
MQTT_TOPIC_CMD = "cmnd/living_fan/Power"

if "device_ip" not in st.session_state:
    st.session_state.device_ip = None  # 처음엔 IP가 없음
if "plug_state" not in st.session_state:
    st.session_state.plug_state = "UNKNOWN"
if "last_changed" not in st.session_state:
    st.session_state.last_changed = time.time() - MIN_HOLD_SECONDS
if "alert_sent" not in st.session_state:
    st.session_state.alert_sent = False

st.set_page_config(page_title="스마트 환기 통합 대시보드", layout="wide")

# IP가 아직 입력되지 않았다면 입력 화면을 보여줌
if st.session_state.device_ip is None:
    st.title("🔗 장치 연결")
    st.info("AirGradient 기기의 현재 IP 주소를 입력해주세요.")
    
    input_ip = st.text_input("Device IP Address", placeholder="예: 172.30.1.94")
    
    if st.button("대시보드 시작하기"):
        if input_ip:
            st.session_state.device_ip = input_ip
            st.success(f"IP {input_ip}가 설정되었습니다!")
            time.sleep(1)
            st.rerun()
        else:
            st.error("IP 주소를 입력해야 합니다.")
    st.stop() # IP 입력 전까지 아래 코드를 실행하지 않음
DEVICE_IP = st.session_state.device_ip
# ==========================================
# 2. 기본 UI 및 세션 초기화
# ==========================================
st.title("📡 공기질 + 자동 환기 제어 시스템")

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
        client.username_pw_set(MQTT_USER, MQTT_PASS)
        client.tls_set()
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
    numeric_cols = ["co2", "temp", "humidity", "tvoc", "nox", "pm01", "PM2.5", "pm10"]
    for col in numeric_cols:
        if col in history_df.columns:
            history_df[col] = pd.to_numeric(history_df[col], errors="coerce")
    history_df = history_df.ffill().fillna(0)
    return history_df

st.sidebar.markdown(f"**📍 연결된 IP:** `{DEVICE_IP}`")
if st.sidebar.button("IP 재설정"):
    st.session_state.device_ip = None
    st.rerun()

# ==========================================
# 5. 데이터 처리 및 UI
# ==========================================
data = fetch_data()
if data:
    latest = data[0] if isinstance(data, list) else data
    co2 = latest.get("rco2", 0)
    new_row = {
        "time": datetime.now(),
        "co2": co2,
        "temp": latest.get("atmp"),
        "humidity": latest.get("rhum"),
        "tvoc": latest.get("tvocIndex"),
        "nox": latest.get("noxIndex"),
        "PM2.5": latest.get("pm02")
    }
    try:
        history_df = pd.read_csv(FILE_PATH)
    except FileNotFoundError:
        history_df = pd.DataFrame(columns=["time", "co2", "temp", "humidity", "tvoc", "nox", "PM2.5"])

    history_df = normalize_history_df(history_df)
    history_df = pd.concat([history_df, pd.DataFrame([new_row])], ignore_index=True).tail(100)
    history_df.to_csv(FILE_PATH, index=False)

    # 상단 메트릭
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("온도", f"{new_row['temp']} °C")
    m2.metric("습도", f"{new_row['humidity']} %")
    m3.metric("CO2", f"{co2} ppm", delta=f"{co2 - 400} ppm" if co2 > 400 else None, delta_color="inverse")
    m4.metric("PM2.5", f"{new_row['PM2.5']} μg/m³")
    st.divider()

    # 그래프
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
    latest_row["temp"] = pd.to_numeric(
        latest_row["temp"],
        errors="coerce"
    ).round(1)

    latest_row["PM2.5"] = pd.to_numeric(
        latest_row["PM2.5"],
        errors="coerce"
    ).round(1)

    latest_row.columns = [
        "측정 시간",
        "CO2 (ppm)",
        "온도 (°C)",
        "습도 (%)",
        "TVOC",
        "NOX",
        "PM2.5"
    ]

    styled_df = latest_row.set_index("측정 시간").style.format({
        "온도 (°C)": "{:.1f}",
        "PM2.5": "{:.1f}"
    })

    st.table(styled_df)

    # 자동 제어 설정 (사이드바)
    st.sidebar.divider()
    auto_mode = st.sidebar.toggle("🤖 자동 환기 모드", value=True)
    st.sidebar.write(f"현재 상태: **{st.session_state.plug_state}**")

    # 수동 제어 버튼
    st.divider()
    st.subheader("🎮 장치 제어")
    c_on, c_off = st.columns(2)
    with c_on:
        if st.button("🔌 즉시 켜기 (ON)", use_container_width=True, type="primary"):
            if control_tasmota_mqtt("ON"):
                st.session_state.plug_state = "ON"
                st.session_state.last_changed = time.time()
                st.rerun()
    with c_off:
        if st.button("🚫 즉시 끄기 (OFF)", use_container_width=True):
            if control_tasmota_mqtt("OFF"):
                st.session_state.plug_state = "OFF"
                st.session_state.last_changed = time.time()
                st.rerun()

    # 제어 로직 실행
    now = time.time()
    elapsed = now - st.session_state.last_changed
    if auto_mode:
        if elapsed >= MIN_HOLD_SECONDS:
            if co2 >= 800 and st.session_state.plug_state != "ON":
                if control_tasmota_mqtt("ON"):
                    st.session_state.plug_state = "ON"
                    st.session_state.last_changed = now
            elif co2 < 500 and st.session_state.plug_state != "OFF":
                if control_tasmota_mqtt("OFF"):
                    st.session_state.plug_state = "OFF"
                    st.session_state.last_changed = now
        else:
            st.sidebar.info(f"대기: {int(MIN_HOLD_SECONDS - elapsed)}초")

    # 알림 로직
    if co2 > 1000:
        st.error(f"🚨 CO2 수치 위험! 현재 {co2}ppm")
        if not st.session_state.alert_sent:
            send_email_alert("🚨 공기질 위험 경보", f"현재 CO2 수치가 {co2}ppm 입니다.")
            st.session_state.alert_sent = True
    elif co2 < 800:
        st.session_state.alert_sent = False
else:
    st.warning("🔄 데이터를 불러오는 중입니다...")

time.sleep(REFRESH_INTERVAL)
st.rerun()