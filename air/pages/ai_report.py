import streamlit as st
import requests
# anthropic 대신 google-genai 라이브러리를 임포트합니다.
from google import genai
from google.genai import errors

# ==========================================
# 설정값 (기존 코드와 동일한 API)
# ==========================================
API_URL = "https://api.airgradient.com/public/api/v1/locations/measures/current"
API_TOKEN = "74cf04f0-11c0-4498-9d7f-e191977faeb4"

# 구독 비밀번호 — secrets.toml에 저장 권장
SUBSCRIPTION_CODE = st.secrets.get("SUBSCRIPTION_CODE", "air1234")

st.set_page_config(page_title="AI 공기질 분석", layout="wide")
st.title("🤖 AI 공기질 분석 리포트")

# ==========================================
# 구독 잠금 해제
# ==========================================
if "subscribed" not in st.session_state:
    st.session_state.subscribed = False

if not st.session_state.subscribed:
    st.warning("🔒 이 페이지는 구독자 전용입니다.")
    st.markdown("구독 코드를 입력하면 AI 분석 리포트를 열람할 수 있습니다.")
    
    code_input = st.text_input("구독 코드 입력", type="password", placeholder="코드를 입력하세요")
    
    if st.button("잠금 해제", type="primary"):
        if code_input == SUBSCRIPTION_CODE:
            st.session_state.subscribed = True
            st.rerun()
        else:
            st.error("❌ 코드가 올바르지 않습니다.")
    st.stop()

# ==========================================
# 공기질 데이터 가져오기
# ==========================================
def fetch_data():
    try:
        res = requests.get(API_URL, params={"token": API_TOKEN}, timeout=5)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        st.error(f"API 호출 실패: {e}")
        return None

# ==========================================
# Gemini AI 분석 (스트리밍)
# ==========================================
def run_ai_analysis(air_data):
    api_key = st.secrets.get("GEMINI_API_KEY")

    if not api_key:
        st.error("GEMINI_API_KEY가 Streamlit Secrets에 설정되지 않았음.")
        st.stop()

    client = genai.Client(api_key=api_key)
    st.subheader("사용 가능한 Gemini 모델 목록")

    try:
        for model in client.models.list():
            st.write(model.name, model.supported_actions)
    except Exception as e:
        st.error("모델 목록 조회 실패")
        st.code(str(e))

    if not isinstance(air_data, dict):
        st.error(f"air_data 타입이 dict가 아님: {type(air_data)}")
        st.stop()

    prompt = f"""
다음은 현재 실내 공기질 측정값임.

PM2.5: {air_data.get("pm25")} µg/m³
CO2: {air_data.get("co2")} ppm
TVOC: {air_data.get("tvoc")}
NOx: {air_data.get("nox")}
온도: {air_data.get("temp")} ℃
습도: {air_data.get("humidity")} %

위 데이터를 바탕으로 현재 실내 공기질 상태를 분석하고,
문제가 되는 항목, 원인, 개선 방법을 한국어로 작성해줘.
"""

    try:
        response_stream = client.models.generate_content_stream(
            model="gemini-1.5-flash",
            contents=prompt
        )

        result_box = st.empty()
        full_text = ""

        for chunk in response_stream:
            if chunk.text:
                full_text += chunk.text
                result_box.markdown(full_text)

    except errors.ClientError as e:
        st.error("Gemini API 요청이 실패함.")
        st.code(str(e))
        st.info("API 키, 모델 이름, 할당량, 요청 데이터 크기를 확인해야 함.")

    except Exception as e:
        st.error("예상하지 못한 오류 발생")
        st.code(str(e))

# ==========================================
# 메인 실행
# ==========================================
data = fetch_data()

if data:
    latest = data[0] if isinstance(data, list) else data
    
    air_data = {
        "pm25":     float(latest.get("pm02") or 0),
        "co2":      float(latest.get("rco2") or 0),
        "tvoc":     float(latest.get("tvocIndex") or 0),
        "nox":      float(latest.get("noxIndex") or 0),
        "temp":     float(latest.get("atmp") or 0),
        "humidity": float(latest.get("rhum") or 0),
    }

    # 현재 측정값 요약 카드
    st.subheader("📊 현재 측정값")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("🌫️ PM2.5", f"{air_data['pm25']:.1f} μg/m³")
    c2.metric("🫁 CO₂",   f"{air_data['co2']:.0f} ppm")
    c3.metric("🧪 TVOC",  f"{air_data['tvoc']:.0f}")
    c4.metric("⚗️ NOx",   f"{air_data['nox']:.0f}")
    c5.metric("🌡️ 온도",  f"{air_data['temp']:.1f} °C")
    c6.metric("💧 습도",  f"{air_data['humidity']:.0f} %")

    st.divider()

    # AI 분석 자동 실행
    st.subheader("🤖 AI 분석 리포트")
    if st.button("AI 분석 실행"):
        run_ai_analysis(air_data)
    else:
        st.info("버튼을 누르면 현재 센서값을 바탕으로 AI 분석을 실행함.")
    st.divider()


    # 구독 해제
    if st.button("🔒 로그아웃 (구독 잠금)", use_container_width=True):
        st.session_state.subscribed = False
        st.rerun()
else:
    st.warning("데이터를 불러오지 못했습니다.")
