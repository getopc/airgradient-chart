import streamlit as st
import requests
import math
import time
import paho.mqtt.client as mqtt

API_URL = "https://api.airgradient.com/public/api/v1/locations/measures/current"
API_TOKEN = "74cf04f0-11c0-4498-9d7f-e191977faeb4"
MQTT_BROKER = "8738ec3a2de44ce7926a5be975e970e3.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "plug1"
MQTT_PASS = "Ab1234567@"
MQTT_TOPIC_CMD = "cmnd/living_fan/Power"
MIN_HOLD_SECONDS = 300 # 상태 유지 시간 (5분)

# =========================
# 고정 상수
# =========================
ROOM_VOLUME = 2.5  # m³

CADR_SPEC = {
    "pm25": 200.0,
    "tvoc": 80.0,
    "nox":  60.0,
    "co2":  12.0,
}

WEIGHTS = {"pm25": 0.30, "co2": 0.30, "tvoc": 0.20, "nox": 0.20}

W_CONC, W_PERF = 0.6, 0.4
W_CADR, W_K   = 0.5, 0.5

st.set_page_config(page_title="공기질 메인화면", layout="wide")

st.markdown("""
<style>
[data-testid="stMetric"] {
    background-color: #ffffff; padding: 20px; border-radius: 20px;
    border: 1px solid #444; text-align: center;
}
[data-testid="stMetricLabel"] { font-size: 26px !important; }
[data-testid="stMetricValue"] { font-size: 48px !important; }
[data-testid="stMetricDelta"] { font-size: 20px !important; }

.iaq-banner {
    padding: 35px; border-radius: 25px; text-align: center;
    color: white; margin-bottom: 20px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}
.iaq-banner h1 { font-size: 60px; margin: 0; }
.iaq-banner h2 { font-size: 80px; margin: 8px 0; }
.iaq-banner p  { font-size: 24px; margin: 0; }
.sub-grade {
    display:inline-block; padding:5px 12px; border-radius:10px;
    color:white; font-weight:bold; font-size:16px; margin-top:6px;
}
</style>
""", unsafe_allow_html=True)

st.title("🏠 실시간 공기질 메인화면")
st.caption(f"공간 부피 V = {ROOM_VOLUME:.0f} m³ 기준")

# =========================
# 점수화 함수
# =========================
def score_pm25(v):
    if v <= 15: return 100
    if v <= 35: return 80
    if v <= 55: return 60
    if v <= 75: return 40
    return 20

def score_co2(v):
    if v <= 600:  return 100
    if v <= 800:  return 80
    if v <= 1000: return 60
    if v <= 1500: return 40
    return 20

def score_tvoc(v):
    if v <= 100: return 100
    if v <= 200: return 80
    if v <= 300: return 60
    if v <= 400: return 40
    return 20

def score_nox(v):
    if v <= 20:  return 100
    if v <= 100: return 80
    if v <= 150: return 60
    if v <= 250: return 40
    return 20

def score_ach(ach):
    if ach >= 8: return 100
    if ach >= 6: return 80
    if ach >= 4: return 60
    if ach >= 2: return 40
    return 20

def score_k(k):
    if k >= 8: return 100
    if k >= 6: return 80
    if k >= 4: return 60
    if k >= 2: return 40
    return 20

def overall_grade(s):
    if s >= 85: return ("매우 좋음", "#2E7D32", "😎", "쾌적한 공기질입니다")
    if s >= 70: return ("좋음",     "#66BB6A", "😃", "양호한 상태입니다")
    if s >= 55: return ("보통",     "#FBC02D", "😐", "환기를 권장합니다")
    if s >= 40: return ("나쁨",     "#EF6C00", "😨", "환기·청정기 가동 필요")
    return            ("매우 나쁨", "#C62828", "😡🤢🤮", "즉시 환기하세요")

def sub_grade(s):
    if s >= 85: return ("매우 좋음", "#2E7D32")
    if s >= 70: return ("좋음",     "#66BB6A")
    if s >= 55: return ("보통",     "#FBC02D")
    if s >= 40: return ("나쁨",     "#EF6C00")
    return            ("매우 나쁨", "#C62828")

# =========================
# 감쇠계수 k 계산
# =========================
def estimate_k(key, current_value):
    hist_key = f"hist_{key}"
    if hist_key not in st.session_state:
        st.session_state[hist_key] = []
    hist = st.session_state[hist_key]
    now = time.time()
    hist.append((now, current_value))
    st.session_state[hist_key] = [(t, v) for t, v in hist if now - t <= 600]
    hist = st.session_state[hist_key]

    if len(hist) < 2:
        return None, "이력 수집 중"

    t0, c0 = hist[0]
    t1, c1 = hist[-1]
    dt_h = (t1 - t0) / 3600.0

    if dt_h < 60/3600:
        return None, "측정 시간 부족 (1분 미만)"
    if c0 <= 0 or c1 <= 0:
        return None, "센서 워밍업 (값 0)"
    if c1 >= c0:
        return None, "농도 안정/증가 (감쇠 미발생)"

    return (1.0 / dt_h) * math.log(c0 / c1), "정상"

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

    pm25 = float(latest.get("pm02") or 0)
    co2  = float(latest.get("rco2") or 0)
    nox  = float(latest.get("noxIndex") or 0)
    tvoc = float(latest.get("tvocIndex") or 0)
    temp = float(latest.get("atmp") or 0)
    humidity = float(latest.get("rhum") or 0)

    values = {"pm25": pm25, "co2": co2, "tvoc": tvoc, "nox": nox}

    # 농도 점수
    conc_scores = {
        "pm25": score_pm25(pm25),
        "co2":  score_co2(co2),
        "tvoc": score_tvoc(tvoc),
        "nox":  score_nox(nox),
    }

    # CADR 점수 (ACH 환산)
    cadr_scores = {k: score_ach(CADR_SPEC[k] / ROOM_VOLUME) for k in CADR_SPEC}

    # k 추정
    k_results = {}
    k_scores = {}
    for key, val in values.items():
        k_est, status = estimate_k(key, val)
        k_results[key] = (k_est, status)
        k_scores[key] = score_k(k_est) if k_est is not None else None

    # 성분별 종합 점수 — k 없으면 농도 100%
    final_scores = {}
    eval_modes = {}
    for key in WEIGHTS:
        if k_scores[key] is None:
            final_scores[key] = conc_scores[key]
            eval_modes[key] = "농도 100%"
        else:
            s_perf = W_CADR * cadr_scores[key] + W_K * k_scores[key]
            final_scores[key] = W_CONC * conc_scores[key] + W_PERF * s_perf
            eval_modes[key] = "농도 60% + CADR 20% + k 20%"

    total = sum(final_scores[k] * WEIGHTS[k] for k in WEIGHTS)
    grade, color, emoji, msg = overall_grade(total)

    # 종합 등급 배너
    st.markdown(f"""
    <div class="iaq-banner" style="background-color:{color};">
        <p>현재 종합 실내 공기질</p>
        <h2>{emoji} {grade}</h2>
        <h1>{total:.1f} / 100</h1>
        <p>{msg}</p>
    </div>
    """, unsafe_allow_html=True)

    # 항목별 진행바
    st.markdown("#### 📊 성분별 종합 점수 (가중치 적용 전)")
    labels = {"pm25":"🌫️ PM2.5", "co2":"🫁 CO₂", "tvoc":"🧪 TVOC", "nox":"⚗️ NOx"}
    for k in ["pm25","co2","tvoc","nox"]:
        pct = int(WEIGHTS[k]*100)
        st.progress(int(final_scores[k]),
                    text=f"{labels[k]}: {final_scores[k]:.1f}점 (가중치 {pct}%)")

    st.divider()

    # 측정값 카드
    def render_metric(col, label, value, score):
        g, c = sub_grade(score)
        with col:
            st.metric(label, value)
            st.markdown(
                f'<div style="text-align:center;">'
                f'<span class="sub-grade" style="background-color:{c};">{g}</span>'
                f'</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    render_metric(col1, "🌫️ PM2.5", f"{pm25:.1f} μg/m³", final_scores["pm25"])
    render_metric(col2, "🫁 CO₂",   f"{co2:.0f} ppm",    final_scores["co2"])
    render_metric(col3, "⚗️ NOx",   f"{nox:.0f}",        final_scores["nox"])

    col4, col5, col6 = st.columns(3)
    render_metric(col4, "🧪 TVOC",  f"{tvoc:.0f}",       final_scores["tvoc"])
    with col5: st.metric("🌡️ 온도", f"{temp:.1f} °C")
    with col6: st.metric("💧 습도", f"{humidity:.0f} %")

    # 상세
    with st.expander("🔍 CADR · ACH · 감쇠계수 k 상세"):
        for key in ["pm25","co2","tvoc","nox"]:
            ach = CADR_SPEC[key] / ROOM_VOLUME
            k_est, status = k_results[key]
            if k_est is not None:
                k_str = f"{k_est:.2f} /h ({status})"
            else:
                k_str = f"미측정 — {status}"
            st.write(f"**{labels[key]}** — CADR: {CADR_SPEC[key]:.0f} m³/h "
                     f"| ACH: {ach:.2f} 회/h | k: {k_str} "
                     f"| 평가방식: *{eval_modes[key]}*")

    st.divider()
    if "plug_state" not in st.session_state: st.session_state.plug_state = "UNKNOWN"
    if "last_changed" not in st.session_state: st.session_state.last_changed = time.time() - MIN_HOLD_SECONDS

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
            st.error(f"MQTT 접속 실패: {e}")
            return False

    st.subheader("🎮 스마트 환기 제어")

    # 사이드바 혹은 하단에 자동 모드 설정
    auto_mode = st.sidebar.toggle("🤖 자동 환기 모드", value=True)
    st.sidebar.write(f"현재 팬 상태: **{st.session_state.plug_state}**")

    # 수동 제어 버튼
    c_on, c_off = st.columns(2)
    with c_on:
        if st.button("🔌 팬 즉시 켜기 (ON)", use_container_width=True, type="primary"):
            if control_tasmota_mqtt("ON"):
                st.session_state.plug_state = "ON"
                st.session_state.last_changed = time.time()
                st.rerun()
    with c_off:
        if st.button("🚫 팬 즉시 끄기 (OFF)", use_container_width=True):
            if control_tasmota_mqtt("OFF"):
                st.session_state.plug_state = "OFF"
                st.session_state.last_changed = time.time()
                st.rerun()

    # --- 자동 제어 실행 로직 ---
    now = time.time()
    elapsed = now - st.session_state.last_changed

    if auto_mode:
        if elapsed >= MIN_HOLD_SECONDS:
            # 켜기 조건: 네 가지 항목 중 하나라도 60점 이하인 경우
            # (하나라도 공기질이 나빠지면 팬 가동)
            if (conc_scores["co2"] <= 60 or 
                conc_scores["pm25"] <= 60 or 
                conc_scores["tvoc"] <= 60 or 
                conc_scores["nox"] <= 60) and st.session_state.plug_state != "ON":
            
                if control_tasmota_mqtt("ON"):
                    st.session_state.plug_state = "ON"
                    st.session_state.last_changed = now
                    st.toast("공기질 저하(복합 오염)로 환기 팬을 가동합니다! 🌬️")
                    time.sleep(1)
                    st.rerun()
        
            # 끄기 조건: 네 가지 항목 모두가 80점 이상으로 회복되었을 때
            # (모든 지표가 깨끗해져야 팬 정지)
            elif (conc_scores["co2"] >= 80 and 
                  conc_scores["pm25"] >= 80 and 
                  conc_scores["tvoc"] >= 80 and 
                  conc_scores["nox"] >= 80) and st.session_state.plug_state != "OFF":
            
                if control_tasmota_mqtt("OFF"):
                    st.session_state.plug_state = "OFF"
                    st.session_state.last_changed = now
                    st.toast("모든 공기질 지표가 개선되어 팬을 정지합니다. ✅")
                    time.sleep(1)
                    st.rerun()
        else:
            st.sidebar.info(f"⏳ 상태 유지 중: {int(MIN_HOLD_SECONDS - elapsed)}초 후 판단")
    if st.button("📊 상세 정보 화면으로 이동", use_container_width=True):
        st.switch_page("pages/app.py")

else:
    st.warning("데이터를 불러오는 중임")
