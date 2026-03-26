import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime

# --- 설정 ---
API_URL = "https://api.airgradient.com/public/api/v1/locations/measures/current"
API_TOKEN = "74cf04f0-11c0-4498-9d7f-e191977faeb4"
REFRESH_INTERVAL = 300  # 5분 (초 단위)

st.set_page_config(page_title="AirGradient 실시간 모니터링", layout="wide")

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
    
    # 헤더 섹션
    last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.title("🍃 AirGradient One 실시간 대시보드")
    st.caption(f"마지막 업데이트: {last_update} (5분 간격 자동 새로고침)")

    # 1. 주요 지표 (Metric 카드)
    # 첫 번째 장소의 데이터를 기준으로 표시 (리스트 형태이므로)
    latest = df.iloc[0]
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("온도 (Temp)", f"{latest['atmp']} °C")
    m2.metric("습도 (Humidity)", f"{latest['rhum']} %")
    m3.metric("CO2 농도", f"{latest['rco2']} ppm")
    m4.metric("TVOC 지수", f"{latest['tvocIndex']}")

    st.divider()

    # 2. 시각화 섹션 (두 개의 컬럼으로 구성)
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📊 미세먼지 단계 (PM01, PM02, PM10)")
        pm_data = pd.DataFrame({
            'Category': ['PM 1.0', 'PM 2.5', 'PM 10'],
            'Value': [latest['pm01'], latest['pm02'], latest['pm10']]
        })
        fig_pm = px.bar(pm_data, x='Category', y='Value', color='Category',
                        range_y=[0, max(pm_data['Value']) + 10],
                        color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig_pm, use_container_width=True)

    with col2:
        st.subheader("💡 대기질 지수 (TVOC & NOx)")
        index_data = pd.DataFrame({
            'Index': ['TVOC Index', 'NOx Index'],
            'Score': [latest['tvocIndex'], latest['noxIndex']]
        })
        fig_index = px.bar(index_data, x='Index', y='Score', color='Index',
                          range_y=[0, 500], # 인덱스는 보통 500 기준
                          color_discrete_sequence=px.colors.qualitative.Safe)
        st.plotly_chart(fig_index, use_container_width=True)

    # 3. 상세 데이터 테이블
    with st.expander("🔍 센서 원본 데이터 확인"):
        st.write(df)

else:
    st.warning("데이터를 불러올 수 없습니다. API 토큰을 다시 확인해 주세요.")

# 자동으로 페이지를 재실행하게 만드는 트릭 (맨 아래 배치)
import time
time.sleep(REFRESH_INTERVAL)
st.rerun()