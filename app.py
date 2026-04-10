import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
import plotly.graph_objects as go


# --- 설정 ---
API_URL = "https://api.airgradient.com/public/api/v1/locations/measures/current"
API_TOKEN = "74cf04f0-11c0-4498-9d7f-e191977faeb4"
REFRESH_INTERVAL = 300  # 5분 (초 단위)

st.set_page_config(page_title="AirGradient 실시간 모니터링", layout="wide")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Black+Han+Sans&display=swap');

html, body, [class*="css"] {
    font-family: 'Black Han Sans';
}
</style>
""", unsafe_allow_html=True)
# 5분마다 자동으로 스크립트를 재실행하는 타이머 (Streamlit 1.27.0+ 기준)
st_autorefresh = st.empty() 

# --- 데이터 로드 함수 ---
def fetch_data():
    params = {"token": API_TOKEN}
    try:
        response = requests.get(API_URL, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"데이터 연결 오류: {e}")
        return None


# 데이터 가져오기
data = fetch_data()

if data:
    df = pd.DataFrame(data)
    latest = df.iloc[0]
    new_data = {
    "time": datetime.now(),
    "co2": latest["rco2"],
    "temp": latest["atmp"],
    "humidity": latest["rhum"],
    "tvoc": latest["tvocIndex"],
    "pm01": latest["pm01"],
    "pm25": latest["pm02"],
    "pm10": latest["pm10"],
    "nox": latest["noxIndex"]
    }
    
    
    # 헤더 섹션
    last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.markdown("""<h1 style='font-family: "Black Han Sans";'>🍃 AirGradient One 실시간 대시보드</h1>""", unsafe_allow_html=True)
    st.caption(f"마지막 업데이트: {last_update} (5분 간격 자동 새로고침)")

    # 1. 주요 지표 (Metric 카드)
    # 첫 번째 장소의 데이터를 기준으로 표시 (리스트 형태이므로)
    latest = df.iloc[0]
    file_path = "data_log.csv"

    # 1. 기존 데이터 불러오기
    try:
        history_df = pd.read_csv(file_path)
        history_df["time"] = pd.to_datetime(history_df["time"])  # 시간 타입 변환
    except:
        history_df = pd.DataFrame(columns=["time", "co2", "temp", "humidity", "tvoc", "nox", "pm2.5"])

    # 2. 새 데이터 추가
    new_row = pd.DataFrame([new_data])
    history_df = pd.concat([history_df, new_row], ignore_index=True)

    # 3. (선택) 최근 데이터만 유지 (예: 100개)
    history_df = history_df.tail(100)

    # 4. 저장
    history_df.to_csv(file_path, index=False)

    co2_val = latest['rco2']
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("온도 (Temp)", f"{latest['atmp']} °C")
    m2.metric("습도 (Humidity)", f"{latest['rhum']} %")
    m3.metric("CO2 농도", f"{latest['rco2']} ppm")
    m4.metric("TVOC 지수", f"{latest['tvocIndex']}")

    st.divider()

    # 2. 시각화 섹션 (두 개의 컬럼으로 구성)
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📊 대기질 지수 (PM2.5,TVOC,NOx)")
        max_val = history_df[["tvoc", "pm25", "nox"]].max().max()
        fig_pm = px.line(history_df, x='time', y=["tvoc", "pm25", "nox"], markers=True, range_y=[0, max_val + 20])
        st.plotly_chart(fig_pm, use_container_width=True)

    with col2:
        st.subheader("💡 대기질 지수 (CO2)")
        max_val = history_df["co2"]
        fig_pm = px.line(history_df, x='time', y=["co2"], markers=True, range_y=[0,  max_val+ 20])
        st.plotly_chart(fig_pm, use_container_width=True)


    # 3. 상세 데이터 테이블
    with st.expander("🔍 센서 원본 데이터 확인"):

        df_display = df.rename(columns={
            "pm01": "PM1.0",
            "pm02": "PM2.5",
            "pm10": "PM10",
            "rco2": "CO2",
            "tvocIndex": "TVOC",
            "noxIndex": "NOx",
            "atmp": "온도",
            "rhum": "습도"
        })

        df_display = df_display[[
            "PM1.0", "PM2.5", "PM10",
            "CO2", "TVOC", "NOx",
            "온도", "습도"
        ]]
        st.dataframe(df_display, use_container_width=True)

else:
    st.warning("데이터를 불러올 수 없습니다. API 토큰을 다시 확인해 주세요.")

if co2_val > 1000:
    st.error(f"🚨 경고: 이산화탄소 농도가 너무 높습니다! 현재: {co2_val} ppm")
    st.info("💡 환기가 필요합니다. 창문을 열어주세요!")
elif co2_val > 800:
    st.warning(f"⚠️ 주의: 공기가 조금 답답해지고 있어요. 현재: {co2_val} ppm")
else:
    st.success(f"✅ 공기질이 아주 쾌적합니다! 현재: {co2_val} ppm")

if co2_val > 1000:
    st.toast("위험! 수치가 기준치를 초과했습니다.", icon='🔥')

if co2_val > 1000:
    st.sidebar.markdown("### ❗ 긴급 알림")
    st.sidebar.error("실내 공기질 위험 수준!")


import smtplib
from email.mime.text import MIMEText

def send_email_alert(subject, body):
    sender_email = "mjjk06162@gmail.com"
    receiver_email = "mjjk06162@gmail.com"  # 본인에게 보내도 됩니다
    password = st.secrets["GMAIL_PASSWORD"]

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = receiver_email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
    except Exception as e:
        print(f"메일 발송 실패: {e}")

if 'alert_sent' not in st.session_state:
    st.session_state.alert_sent = False

co2_val = latest['rco2']

if co2_val > 1000:
    st.error("🚨 실내 이산화탄소 농도 위험!")
    # 메일을 아직 안 보냈을 때만 발송
    if not st.session_state.alert_sent:
        send_email_alert(
            "⚠️ [경고] 실내 공기질 위험 알림",
            f"현재 CO2 농도가 {co2_val}ppm으로 기준치를 초과했습니다. 환기가 필요합니다!"
        )
        st.session_state.alert_sent = True  # 발송 완료 표시
        st.success("📧 경고 메일이 발송되었습니다.")
elif co2_val < 800:
    # 수치가 다시 정상으로 돌아오면 발송 상태 초기화
    st.session_state.alert_sent = False

# 자동으로 페이지를 재실행하게 만드는 트릭 (맨 아래 배치)
import time
time.sleep(REFRESH_INTERVAL)
st.rerun()

