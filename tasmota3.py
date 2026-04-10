import requests
import time
import pandas as pd
from datetime import datetime
import streamlit as st

# ==========================================
# 1. 설정값 (IP, API, 유지 시간)
# ==========================================
DEVICE_IP = "172.30.1.55" # 스마트 플러그 IP (노트북과 같은 와이파이 필수!)
API_URL = "https://api.airgradient.com/public/api/v1/locations/measures/current"
API_TOKEN = "74cf04f0-11c0-4498-9d7f-e191977faeb4"
MIN_HOLD_SECONDS = 300  # 상태 변경 후 최소 유지 시간 (5분)

# 화면 기본 설정
st.set_page_config(page_title="스마트 환기 제어 대시보드", layout="centered")

# ==========================================
# 2. 통신 함수 (플러그 제어 및 데이터 수신)
# ==========================================
def turn_on_tasmota(ip):
    on_url = f"http://{ip}/cm?cmnd=Power%20ON"
    try:
        res = requests.get(on_url, timeout=5)
        if res.status_code == 200:
            return True
        return False
    except Exception as e:
        st.error(f"ON 요청 실패: {e} (같은 와이파이에 연결되어 있는지 확인하세요!)")
        return False

def turn_off_tasmota(ip):
    off_url = f"http://{ip}/cm?cmnd=Power%20OFF"
    try:
        res = requests.get(off_url, timeout=5)
        if res.status_code == 200:
            return True
        return False
    except Exception as e:
        st.error(f"OFF 요청 실패: {e} (같은 와이파이에 연결되어 있는지 확인하세요!)")
        return False

def fetch_data():
    params = {"token": API_TOKEN}
    try:
        response = requests.get(API_URL, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"데이터 연결 오류: {e}")
        return None

# ==========================================
# 3. 화면 UI 및 세션 상태 초기화
# ==========================================
st.title("📡 실시간 공기질 및 플러그 제어 대시보드")

# [수정 1] 초기 상태를 UNKNOWN으로 설정 (처음에 무조건 켜거나 끄는 명령을 1회 쏘기 위해)
if 'plug_state' not in st.session_state:
    st.session_state.plug_state = "UNKNOWN"

# [수정 2] 처음 프로그램을 켰을 때 무조건 5분을 기다리지 않고 즉시 반응하게끔 시간 조작
if 'last_changed' not in st.session_state:
    st.session_state.last_changed = time.time() - MIN_HOLD_SECONDS

# ==========================================
# 4. 데이터 수신 및 제어 로직 실행
# ==========================================
data = fetch_data()

if data:
    # 1) 데이터프레임으로 변환하여 rco2 값 추출
    df = pd.DataFrame(data)
    latest = df.iloc[0]
    co2_val = latest['rco2']
    
    # 2) 시간 계산 (마지막 작동 후 몇 초가 지났는가?)
    now = time.time()
    elapsed = now - st.session_state.last_changed

    # 3) 화면에 핵심 수치 예쁘게 띄우기
    col1, col2, col3 = st.columns(3)
    col1.metric("현재 CO2 농도", f"{co2_val} ppm")
    col2.metric("현재 플러그 상태", st.session_state.plug_state)
    col3.metric("마지막 변경 후 경과", f"{int(elapsed)} 초")

    st.markdown("---")

    # 4) 플러그 켜고 끄는 핵심 로직 (5분 경과 여부 확인)
    if elapsed >= MIN_HOLD_SECONDS:
        
        # 환기가 필요한 경우 (ON)
        if co2_val >= 800 and st.session_state.plug_state != "ON":
            st.warning("🚨 CO2 농도 800 이상! 플러그를 켭니다.")
            if turn_on_tasmota(DEVICE_IP):
                st.session_state.plug_state = "ON"
                st.session_state.last_changed = now
                st.success("✅ 플러그를 ON으로 변경했습니다. (최소 5분 유지)")

        # 공기가 깨끗해진 경우 (OFF)
        elif co2_val < 400 and st.session_state.plug_state != "OFF":
            st.info("🌿 CO2 농도 400 미만! 플러그를 끕니다.")
            if turn_off_tasmota(DEVICE_IP):
                st.session_state.plug_state = "OFF"
                st.session_state.last_changed = now
                st.success("✅ 플러그를 OFF로 변경했습니다. (최소 5분 유지)")
                
        # 아무것도 안 해도 되는 경우 (안정 구간)
        else:
            st.write("🔄 현재 안정 구간이거나 상태 유지 중입니다. (대기 상태)")

    else:
        remain = int(MIN_HOLD_SECONDS - elapsed)
        st.info(f"⏳ 잦은 On/Off 방지 중... 현재 상태를 {remain}초 더 유지합니다.")

# ==========================================
# 5. 실시간 감시를 위한 자동 새로고침
# ==========================================
# 5초마다 알아서 최신 데이터를 가져오고 화면을 업데이트합니다.
time.sleep(5)
st.rerun()