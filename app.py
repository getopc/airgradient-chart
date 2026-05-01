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
MQTT_BROKER = "8738ec3a2de44ce7926a5be975e970e3.s1.eu.hivemq.cloud"
MQTT_PORT = 8883 
MQTT_USER = "plug1"
MQTT_PASS = "Ab1234567@"
# 대소문자 주의: 타스모타 콘솔에서 확인한 것과 똑같이 맞춰야 합니다. (보통 Power)
MQTT_TOPIC_CMD = "cmnd/living_fan/Power" 

# ==========================================
# 2. 기본 UI 및 세션 초기화
# ==========================================
st.set_page_config(page_title="스마트 환기 통합 대시보드", layout="wide")
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
        
        # cmd는 "ON" 또는 "OFF"
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
    if history_df.empty: return history_df
    if "time" in history_df.columns:
        history_df["time"] = pd.to_datetime(history_df["time"], errors="coerce")
    numeric_cols = ["co2", "temp", "humidity", "tvoc", "nox", "pm01", "PM2.5", "pm10"]
    for col in numeric_cols:
        if col in history_df.columns:
            history_df[col] = pd.to_numeric(history_df[col], errors="coerce")
    return history_df.ffill().fillna(0)

# ==========================================
# 5. 데이터 처리 및 메인 로직
# ==========================================
data = fetch_data()

if data:
    latest = data[0] if isinstance(data, list) else data
    co2 = latest.get("rco2", 0)

    # 데이터 저장 로직
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

    # UI 출력
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("온도", f"{new_row['temp']} °C")
    m2.metric("습도", f"{new_row['humidity']} %")
    m3.metric("CO2", f"{co2} ppm", delta=f"{co2 - 400} ppm" if co2 > 400 else None, delta_color="inverse")
    m4.metric("PM2.5", f"{new_row['PM2.5']} μg/m³")

    st.divider()

    # 사이드바 설정
    st.sidebar.header("⚙️ 제어 설정")
    auto_mode = st.sidebar.toggle("🤖 자동 환기 모드", value=True)
    if auto_mode:
        st.sidebar.success("상태: 자동 제어 중")
    else:
        st.sidebar.warning("상태: 수동 제어 중")

    # 장치 제어 버튼 (수동)
    st.subheader("🎮 장치 제어")
    col_on, col_off = st.columns(2)
    with col_on:
        if st.button("🔌 즉시 켜기 (ON)", use_container_width=True, type="primary"):
            if control_tasmota_mqtt("ON"):
                st.session_state.plug_state = "ON"
                st.session_state.last_changed = time.time()
                st.toast("수동 명령: 가동 시작", icon="✅")
                st.rerun()
    with col_off:
        if st.button("🚫 즉시 끄기 (OFF)", use_container_width=True):
            if control_tasmota_mqtt("OFF"):
                st.session_state.plug_state = "OFF"
                st.session_state.last_changed = time.time()
                st.toast("수동 명령: 가동 중지", icon="🛑")
                st.rerun()

    # 자동 제어 로직
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
            st.sidebar.info(f"대기 중: {int(MIN_HOLD_SECONDS - elapsed)}초 남음")

    # 이메일 알림 (통합)
    if co2 > 1000:
        st.error(f"🚨 실내 CO2 농도 위험! (현재: {co2} ppm)")
        if not st.session_state.alert_sent:
            send_email_alert("🚨 공기질 위험 경보", f"현재 CO2 수치가 {co2}ppm 입니다. 환기가 필요합니다.")
            st.session_state.alert_sent = True
    elif co2 < 800:
        st.session_state.alert_sent = False

else:
    st.error("🔄 데이터를 불러오는 중이거나 장치에 연결할 수 없습니다.")

# 새로고침
time.sleep(REFRESH_INTERVAL)
st.rerun()