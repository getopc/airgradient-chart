import streamlit as st
import requests

API_URL = "https://api.airgradient.com/public/api/v1/locations/measures/current"
API_TOKEN = "74cf04f0-11c0-4498-9d7f-e191977faeb4"

st.set_page_config(page_title="공기질 메인화면", layout="wide")

# =========================
# 글씨 크기 스타일
# =========================
st.markdown("""
<style>

[data-testid="stMetric"] {
    background-color: #ffffff;
    padding: 25px;
    border-radius: 20px;
    border: 1px solid #444;
    text-align: center;
}

/* 제목 */
[data-testid="stMetricLabel"] {
    font-size: 35px !important;
}

/* 숫자 */
[data-testid="stMetricValue"] {
    font-size: 65px !important;
}

/* delta 값 */
[data-testid="stMetricDelta"] {
    font-size: 25px !important;
}

</style>
""", unsafe_allow_html=True)

st.title("🏠 실시간 공기질 메인화면")
st.write("현재 실내 공기질 상태를 한눈에 확인하는 화면임")

def fetch_data():
    try:
        res = requests.get(API_URL, params={"token": API_TOKEN}, timeout=5)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        st.error(f"API 호출 실패: {e}")
        return None

data = fetch_data()

if data:
    latest = data[0] if isinstance(data, list) else data

    pm25 = latest.get("pm02", 0)
    co2 = latest.get("rco2", 0)
    nox = latest.get("noxIndex", 0)
    tvoc = latest.get("tvocIndex", 0)
    temp = latest.get("atmp", 0)
    humidity = latest.get("rhum", 0)

    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("🌫️ PM2.5", f"{float(pm25):.1f} μg/m³")
        st.metric("🧪 TVOC", f"{tvoc}")

    with col2:
        st.metric("🫁 CO2", f"{co2} ppm")
        st.metric("🌡️ 온도", f"{float(temp):.1f} °C")

    with col3:
        st.metric("⚗️ NOX", f"{nox}")
        st.metric("💧 습도", f"{humidity} %")

    if st.button("📊 상세 정보 화면으로 이동", use_container_width=True):
        st.switch_page("pages/app.py")

else:
    st.warning("데이터를 불러오는 중임")