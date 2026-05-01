import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
import time
import smtplib
from email.mime.text import MIMEText
import paho.mqtt.client as mqtt
import os

# ==========================================
# 1. 설정값
# ==========================================
API_URL = "https://api.airgradient.com/public/api/v1/locations/measures/current"
API_TOKEN = "74cf04f0-11c0-4498-9d7f-e191977faeb4"

MIN_HOLD_SECONDS = 300
REFRESH_INTERVAL = 5
FILE_PATH = "data_log.csv"

# MQTT 설정
MQTT_BROKER = "8738ec3a2de44ce7926a5be975e970e3.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "plug1"
MQTT_PASS = "Ab1234567@"
MQTT_TOPIC_CMD = "cmnd/living_fan/Power" # 타스모타 표준 대소문자 적용

# ==========================================
# 2. UI 및 세션 초기화
# ==========================================
st.set_page_config(page_title="스마트 환기 통합 대시보드", layout="wide", page_icon="🍃")
st.title("📡 공기질 모니터링 및 자동 환기 시스템")

if "plug_state" not in st.session_state:
    st.session_state.plug_state = "UNKNOWN"
if "last_changed" not in st.session_state:
    st.session_state.last_changed = time.time() - MIN_HOLD_SECONDS
if "alert_sent" not in st.session_state:
    st.session_state.alert_sent = False

# ==========================================
# 3. 주요 함수
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
        st.error(f"MQTT 제어 실패: {e}")
        return False

def fetch_data():
    try:
        res = requests.get(API_URL, params={"token": API_TOKEN}, timeout=5)
        res.raise_for_status()
        data = res.json()
        return data[0] if isinstance(data, list) else data
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

# ==========================================
# 4. 데이터 수집 및 처리
# ==========================================
latest_data = fetch_data()

if latest_data:
    co2 = latest_data.get("rco2", 0)
    
    # 새 데이터 생성
    new_row = {
        "time": datetime.now(),
        "co2": co2,
        "temp": round(latest_data.get("atmp", 0), 1),
        "humidity": latest_data.get("rhum", 0),
        "tvoc": latest_data.get("tvocIndex", 0),
        "nox": latest_data.get("noxIndex", 0),
        "PM2.5": round(latest_data.get("pm02", 0), 1)
    }

    # CSV 데이터 로드 및 병합
    if os.path.exists(FILE_PATH):
        history_df = pd.read_csv(FILE_PATH)
        history_df["time"] = pd.to_datetime(history_df["time"])
    else:
        history_df = pd.DataFrame(columns=["time", "co2", "temp", "humidity", "tvoc", "nox", "PM2.5"])

    history_df = pd.concat([history_df, pd.DataFrame([new_row])], ignore_index=True).tail(100)
    history_df.to_csv(FILE_PATH, index=False)

    # ==========================================
    # 5. UI 출력 (메트릭)
    # ==========================================
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("온도", f"{new_row['temp']} °C")
    m2.metric("습도", f"{new_row['humidity']} %")
    m3.metric("CO2 농도", f"{co2} ppm", delta=f"{co2 - 400} ppm" if co2 > 400 else None, delta_color="inverse")
    m4.metric("미세먼지 (PM2.5)", f"{new_row['PM2.5']} μg/m³")

    st.divider()

    # ==========================================
    # 6. 그래프 섹션
    # ==========================================
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 주요 공기질 지표 추이")
        fig1 = px.line(history_df, x="time", y=["tvoc", "PM2.5", "nox"], template="plotly_dark")
        fig1.update_layout(xaxis=dict(fixedrange=True), yaxis=dict(fixedrange=True), dragmode=False)
        st.plotly_chart(fig1, use_container_width=True, config={'displayModeBar': False})

    with col2:
        st.subheader("📈 CO2 농도 변화")
        fig2 = px.line(history_df, x="time", y="co2", template="plotly_dark", color_discrete_sequence=['#FF4B4B'])
        fig2.update_layout(xaxis=dict(fixedrange=True), yaxis=dict(fixedrange=True), dragmode=False)
        st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': False})

    # ==========================================
    # 7. 상세 데이터 표
    # ==========================================
    st.subheader("📋 최근 측정 기록")
    display_df = history_df.copy().sort_values(by="time", ascending=False).head(5)
    display_df["time"] = display_df["time"].dt.strftime("%H:%M:%S")
    # 1. 데이터 복사 및 정렬
    display_df = history_df.copy().sort_values(by="time", ascending=False).head(5)

    # 2. 실제로 존재하는 컬럼만 선택 (개수 불일치 방지)
    target_cols = ["time", "co2", "temp", "humidity", "tvoc", "nox", "PM2.5"]
    existing_cols = [col for col in target_cols if col in display_df.columns]
    display_df = display_df[existing_cols]

    # 3. 시간 형식 변경
    if "time" in display_df.columns:
        display_df["time"] = pd.to_datetime(display_df["time"]).dt.strftime("%H:%M:%S")

    # 4. 컬럼 이름 변경 (존재하는 것만 매핑)
    name_map = {
        "time": "시간",
        "co2": "CO2(ppm)",
        "temp": "온도(°C)",
        "humidity": "습도(%)",
        "tvoc": "TVOC",
        "nox": "NOX",
        "PM2.5": "PM2.5"
    }

    # 존재하는 컬럼에 대해서만 이름을 변경합니다.
    display_df = display_df.rename(columns=name_map)

    # 5. 출력
    st.table(display_df.set_index("시간") if "시간" in display_df.columns else display_df)

    # ==========================================
    # 8. 제어 설정 및 버튼
    # ==========================================
    st.divider()
    st.sidebar.header("⚙️ 제어 설정")
    auto_mode = st.sidebar.toggle("🤖 자동 환기 모드", value=True)
    st.sidebar.write(f"현재 상태: **{st.session_state.plug_state}**")

    st.subheader("🎮 장치 수동 제어")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔌 즉시 켜기 (ON)", use_container_width=True, type="primary"):
            if control_tasmota_mqtt("ON"):
                st.session_state.plug_state = "ON"
                st.session_state.last_changed = time.time()
                st.toast("수동: 가동 시작", icon="✅")
                st.rerun()
    with c2:
        if st.button("🚫 즉시 끄기 (OFF)", use_container_width=True):
            if control_tasmota_mqtt("OFF"):
                st.session_state.plug_state = "OFF"
                st.session_state.last_changed = time.time()
                st.toast("수동: 가동 중지", icon="🛑")
                st.rerun()

    # ==========================================
    # 9. 자동 제어 및 알림 로직
    # ==========================================
    now = time.time()
    elapsed = now - st.session_state.last_changed

    if auto_mode:
        if elapsed >= MIN_HOLD_SECONDS:
            if co2 >= 800 and st.session_state.plug_state != "ON":
                if control_tasmota_mqtt("ON"):
                    st.session_state.plug_state = "ON"
                    st.session_state.last_changed = now
                    st.toast("자동 가동 시작", icon="🤖")
            elif co2 < 500 and st.session_state.plug_state != "OFF":
                if control_tasmota_mqtt("OFF"):
                    st.session_state.plug_state = "OFF"
                    st.session_state.last_changed = now
                    st.toast("자동 가동 종료", icon="🍃")
        else:
            st.sidebar.info(f"다음 자동 제어까지: {int(MIN_HOLD_SECONDS - elapsed)}초")

    # 위험 알림
    if co2 > 1000:
        st.error(f"🚨 CO2 농도 위험! 현재 {co2}ppm")
        if not st.session_state.alert_sent:
            send_email_alert("🚨 공기질 위험", f"CO2 농도가 {co2}ppm 입니다.")
            st.session_state.alert_sent = True
    elif co2 < 800:
        st.session_state.alert_sent = False

else:
    st.error("🔄 데이터를 불러올 수 없습니다. 장치 연결을 확인하세요.")

# 자동 새로고침
time.sleep(REFRESH_INTERVAL)
st.rerun()
