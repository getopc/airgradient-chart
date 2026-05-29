import streamlit as st
import requests
import anthropic

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
# Claude AI 분석 (스트리밍)
# ==========================================
def run_ai_analysis(air_data: dict):
    prompt = f"""
당신은 실내 공기질 전문 분석 AI입니다.
아래는 현재 측정된 실내 공기질 데이터입니다. 이를 바탕으로 전문적이고 친절한 한국어 분석 리포트를 작성해주세요.

## 현재 측정값
- PM2.5 (미세먼지): {air_data['pm25']} μg/m³
- CO₂ (이산화탄소): {air_data['co2']} ppm
- TVOC (휘발성유기화합물): {air_data['tvoc']}
- NOx (질소산화물): {air_data['nox']}
- 온도: {air_data['temp']} °C
- 습도: {air_data['humidity']} %

## 리포트 작성 형식 (아래 순서대로 작성)
1. **종합 평가** — 전체적인 공기질 상태를 2~3문장으로 요약
2. **항목별 분석** — 각 수치가 기준치 대비 어떤 상태인지, 건강에 미치는 영향
3. **위험 요소** — 현재 수치 중 주의가 필요한 항목과 그 이유
4. **행동 권고** — 지금 당장 취해야 할 조치 (환기, 청정기, 외출 자제 등)
5. **예측 및 조언** — 현재 추세가 지속될 경우 향후 상황과 장기적 관리 팁

전문 용어는 쉽게 풀어서 설명하고, 이모지를 적절히 사용해 읽기 쉽게 작성해주세요.
"""

    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    
    with st.spinner("🧠 AI가 공기질을 분석하고 있습니다..."):
        with client.messages.stream(
            model="claude-opus-4-5",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            report_placeholder = st.empty()
            full_text = ""
            for text in stream.text_stream:
                full_text += text
                report_placeholder.markdown(full_text)

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
    run_ai_analysis(air_data)

    st.divider()

    # 재분석 버튼
    if st.button("🔄 다시 분석하기", use_container_width=True):
        st.rerun()

    # 구독 해제
    if st.button("🔒 로그아웃 (구독 잠금)", use_container_width=True):
        st.session_state.subscribed = False
        st.rerun()
else:
    st.warning("데이터를 불러오지 못했습니다.")