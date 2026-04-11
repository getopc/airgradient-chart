import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
import time
import smtplib
from email.mime.text import MIMEText

# ==========================================
# 1. 설정값
# ==========================================
DEVICE_IP = "172.30.1.55"
API_URL = "https://api.airgradient.com/public/api/v1/locations/measures/current"
API_TOKEN = "74cf04f0-11c0-4498-9d7f-e191977faeb4"

MIN_HOLD_SECONDS = 300
REFRESH_INTERVAL = 5
FILE_PATH = "data_log.csv"

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
def control_tasmota(ip, cmd):
    try:
        url = f"http://{ip}/cm?cmnd=Power%20{cmd}"
        res = requests.get(url, timeout=3)
        return res.status_code == 200
    except Exception as e:
        st.error(f"Tasmota 연결 실패: {e}")
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
        fig1 = px.line(history_df, x="time", y=chart_cols, template="plotly_dark")
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        st.subheader("CO2 농도 변화")
        fig2 = px.line(history_df, x="time", y="co2", template="plotly_dark")
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.subheader("📋 최근 측정 기록 (상세 데이터)")

    display_df = history_df.copy()
    display_df["time"] = pd.to_datetime(display_df["time"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
    display_df = display_df.sort_values(by="time", ascending=False)

    display_cols = [col for col in ["time", "co2", "temp", "humidity", "tvoc", "nox", "PM2.5"] if col in display_df.columns]
    display_df = display_df[display_cols]

    latest_row = display_df.head(1)

    st.dataframe(
        latest_row,
        use_container_width=True,
        column_config={
            "time": "측정 시간",
            "co2": st.column_config.NumberColumn("CO2 (ppm)", format="%d"),
            "temp": st.column_config.NumberColumn("온도 (°C)", format="%.1f"),
            "humidity": st.column_config.NumberColumn("습도 (%)", format="%d"),
            "tvoc": st.column_config.NumberColumn("TVOC", format="%d"),
            "nox": st.column_config.NumberColumn("NOX", format="%d"),
            "PM2.5": st.column_config.NumberColumn("PM2.5", format="%d")
    }
)

    # ==========================================
    # 7. 자동 제어 로직
    # ==========================================
    now = time.time()
    elapsed = now - st.session_state.last_changed

    st.sidebar.header("🕹️ 제어 상태")
    st.sidebar.write(f"현재 상태: **{st.session_state.plug_state}**")

    if elapsed < MIN_HOLD_SECONDS:
        st.sidebar.info(f"⏳ 유지 모드: {int(MIN_HOLD_SECONDS - elapsed)}초 후 변경 가능")
    else:
        if co2 >= 800 and st.session_state.plug_state != "ON":
            if control_tasmota(DEVICE_IP, "ON"):
                st.session_state.plug_state = "ON"
                st.session_state.last_changed = now
                st.toast("환기 시스템 가동!", icon="✅")

        elif co2 < 500 and st.session_state.plug_state != "OFF":
            if control_tasmota(DEVICE_IP, "OFF"):
                st.session_state.plug_state = "OFF"
                st.session_state.last_changed = now
                st.toast("환기 시스템 정지", icon="🛑")

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