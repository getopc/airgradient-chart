import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
import time
import smtplib
from email.mime.text import MIMEText
import paho.mqtt.client as mqtt
import math

# ==========================================
# 1. 설정값 및 세션 초기화
# ==========================================
API_URL = "https://api.airgradient.com/public/api/v1/locations/measures/current"
API_TOKEN = "74cf04f0-11c0-4498-9d7f-e191977faeb4"
REFRESH_INTERVAL = 10  # 테스트를 위해 인터벌을 조금 늘림
FILE_PATH = "data_log.csv"

if "alert_sent" not in st.session_state:
    st.session_state.alert_sent = False

# =========================
# 점수화 함수 정의
# =========================
ROOM_VOLUME = 24.0
CADR_SPEC = {"pm25": 200.0, "tvoc": 80.0, "nox": 60.0, "co2": 12.0}
WEIGHTS = {"pm25": 0.30, "co2": 0.30, "tvoc": 0.20, "nox": 0.20}
W_CONC, W_PERF = 0.6, 0.4
W_CADR, W_K = 0.5, 0.5

def score_pm25(v): return 100 if v <= 15 else 80 if v <= 35 else 60 if v <= 55 else 40 if v <= 75 else 20
def score_co2(v): return 100 if v <= 600 else 80 if v <= 800 else 60 if v <= 1000 else 40 if v <= 1500 else 20
def score_tvoc(v): return 100 if v <= 100 else 80 if v <= 200 else 60 if v <= 300 else 40 if v <= 400 else 20
def score_nox(v): return 100 if v <= 20 else 80 if v <= 100 else 60 if v <= 150 else 40 if v <= 250 else 20
def score_ach(ach): return 100 if ach >= 8 else 80 if ach >= 6 else 60 if ach >= 4 else 40 if ach >= 2 else 20
def score_k(k): return 100 if k >= 8 else 80 if k >= 6 else 60 if k >= 4 else 40 if k >= 2 else 20

def overall_grade(s):
    if s >= 85: return ("매우 좋음", "#2E7D32", "😎")
    if s >= 70: return ("좋음", "#66BB6A", "😃")
    if s >= 55: return ("보통", "#FBC02D", "😐")
    if s >= 40: return ("나쁨", "#EF6C00", "😨")
    return ("매우 나쁨", "#C62828", "😡")

def estimate_k(key, current_value):
    hist_key = f"hist_{key}"
    if hist_key not in st.session_state: st.session_state[hist_key] = []
    hist = st.session_state[hist_key]
    now = time.time()
    hist.append((now, current_value))
    st.session_state[hist_key] = [(t, v) for t, v in hist if now - t <= 600]
    if len(hist) < 2: return None, "이력 수집 중"
    t0, c0 = hist[0]; t1, c1 = hist[-1]
    dt_h = (t1 - t0) / 3600.0
    if dt_h < 60/3600 or c0 <= 0 or c1 <= 0 or c1 >= c0: return None, "측정중"
    return (1.0 / dt_h) * math.log(c0 / c1), "정상"

# =========================
# 이메일 전송 함수
# =========================
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
        return True
    except Exception as e:
        st.sidebar.error(f"이메일 전송 실패: {e}")
        return False

# ==========================================
# 2. 데이터 처리 및 실행
# ==========================================
st.set_page_config(page_title="스마트 환기 통합 대시보드", layout="wide")
st.title("📡 공기질 통합 대시보드 (알림 테스트)")

# 초기화 버튼 (알림 다시 테스트용)
if st.sidebar.button("알림 상태 초기화"):
    st.session_state.alert_sent = False
    st.sidebar.success("알림 기록이 초기화되었습니다.")

res = requests.get(API_URL, params={"token": API_TOKEN}, timeout=5)
if res.status_code == 200:
    data = res.json()
    latest = data[0] if isinstance(data, list) else data
    
    # 1. 변수 추출
    co2 = latest.get("rco2", 0)
    pm25 = latest.get("pm02", 0)
    tvoc = latest.get("tvocIndex", 0)
    nox = latest.get("noxIndex", 0)
    temp = latest.get("atmp", 0)
    hum = latest.get("rhum", 0)
    
    values = {"pm25": pm25, "co2": co2, "tvoc": tvoc, "nox": nox}
    
    # 2. 점수 계산
    conc_scores = {"pm25": score_pm25(pm25), "co2": score_co2(co2), "tvoc": score_tvoc(tvoc), "nox": score_nox(nox)}
    cadr_scores = {k: score_ach(CADR_SPEC[k] / ROOM_VOLUME) for k in CADR_SPEC}
    k_scores = {k: (score_k(estimate_k(k, v)[0]) if estimate_k(k, v)[0] else None) for k, v in values.items()}

    final_scores = {}
    for k in WEIGHTS:
        if k_scores[k] is None: final_scores[k] = conc_scores[k]
        else: final_scores[k] = (W_CONC * conc_scores[k]) + (W_PERF * (W_CADR * cadr_scores[k] + W_K * k_scores[k]))

    total = sum(final_scores[k] * WEIGHTS[k] for k in WEIGHTS)
    grade, color, emoji = overall_grade(total)

    # 3. 데이터 저장
    new_row = {"time": datetime.now(), "co2": co2, "temp": temp, "humidity": hum, "tvoc": tvoc, "nox": nox, "PM2.5": pm25}
    try:
        history_df = pd.read_csv(FILE_PATH)
        history_df["time"] = pd.to_datetime(history_df["time"])
    except:
        history_df = pd.DataFrame(columns=["time", "co2", "temp", "humidity", "tvoc", "nox", "PM2.5"])
    
    history_df = pd.concat([history_df, pd.DataFrame([new_row])], ignore_index=True).tail(50)
    history_df.to_csv(FILE_PATH, index=False)

    # 4. 상단 메트릭 및 알림 상태 표시
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("종합 지수", f"{total:.1f}점", delta=grade)
    m2.metric("CO2", f"{co2} ppm")
    m3.metric("온도/습도", f"{temp:.1f}°C / {hum:.0f}%")
    m4.metric("PM2.5", f"{pm25} μg/m³")

    # 5. 그래프 시각화
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📊 주요 오염물질 추이")
        fig1 = px.line(history_df, x="time", y=["PM2.5", "tvoc", "nox"], template="plotly_dark")
        fig1.update_layout(xaxis=dict(fixedrange=True), yaxis=dict(fixedrange=True), dragmode=False)
        st.plotly_chart(fig1, use_container_width=True, config={'displayModeBar': False})
    
    with col2:
        st.subheader("📉 CO2 농도 변화")
        fig2 = px.line(history_df, x="time", y="co2", template="plotly_dark")
        fig2.update_layout(xaxis=dict(fixedrange=True), yaxis=dict(fixedrange=True), dragmode=False)
        st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': False})

    # 6. 표 출력
    st.subheader("📋 최근 측정 기록")

    # 1. 최신 데이터 1줄만 추출
    display_df = history_df.copy().sort_values("time", ascending=False).head(1)
    display_df = display_df.drop(columns=["time"], errors="ignore")

    # 3. 정수형으로 변환 (소수점 제거를 위해)
    # errors='ignore'를 사용하여 숫자가 아닌 값이 섞여 있어도 에러가 나지 않게 처리합니다.
    cols_to_int = ["co2", "humidity", "tvoc", "nox"]
    for col in cols_to_int:
        if col in display_df.columns:
            display_df[col] = pd.to_numeric(display_df[col], errors='coerce').fillna(0).astype(int)

    # 4. 표 출력 및 소수점 포맷팅
    st.dataframe(
        display_df.style.format({
            "temp": "{:.1f}",     # 온도는 소수점 1자리
            "PM2.5": "{:.1f}",    # PM2.5는 소수점 1자리
            "co2": "{:d}",        # 정수형
            "humidity": "{:d}",   # 정수형
            "tvoc": "{:d}",       # 정수형
            "nox": "{:d}"         # 정수형
        }), 
        use_container_width=True
    )
     # 🚨 알림 로직 (펼쳐진 형태)
   # 🚨 항목별 알림 로직 (개별 점수 60점 이하 기준)
    
    # 1. 60점 이하인 항목 찾기
    # conc_scores = {"pm25": 점수, "co2": 점수, ...}
    low_score_items = [name.upper() for name, score in conc_scores.items() if score <= 60]

    if low_score_items:
        # 경고 문구 생성 (예: "주의: CO2, PM25 항목의 공기질이 나쁩니다.")
        items_str = ", ".join(low_score_items)
        
        # 화면 상단 고정 경고
        st.warning(f"### {emoji} 주의: [{items_str}] 항목 점수가 60점 이하입니다!")

        # 알림 발송 영역
        alert_container = st.container()
        with alert_container:
            if not st.session_state.alert_sent:
                st.write(f"📧 **이메일 발송 상태:** [{items_str}] 이상 감지됨...")
                
                # 메일 내용 구성
                email_body = f"""
                🚨 공기질 주의 경보
                
                현재 다음 항목들의 점수가 낮습니다: {items_str}
                
                - 종합 점수: {total:.1f}점
                - 상태: {grade}
                - 상세 수치: CO2 {co2}ppm, PM2.5 {pm25}μg/m³, TVOC {tvoc}, NOX {nox}
                """
                
                success = send_email_alert(f"🚨 공기질 경보 ({items_str})", email_body)
                
                if success:
                    st.session_state.alert_sent = True
                    st.success(f"✅ {items_str} 관련 알림 메일 전송 완료!")
                    st.toast("위험 항목 알림 완료", icon="🚨")
                else:
                    st.error("❌ 이메일 발송 실패")
            else:
                st.info(f"✅ 알림 발송 완료 상태 (감지된 항목: {items_str})")
                if st.button("알림 기록 초기화 (테스트용)"):
                    st.session_state.alert_sent = False
                    st.rerun()
    else:
        # 모든 항목이 60점 초과인 경우 알림 상태 리셋 (선택 사항)
        # 공기가 다시 좋아졌을 때 자동으로 다음 위험 상황을 대비하게 하고 싶다면 아래 주석 해제
        # st.session_state.alert_sent = False
        st.success("✨ 모든 공기질 항목이 양호한 수준입니다.")

else:
    st.error("데이터를 불러올 수 없습니다. API 토큰을 확인하세요.")

time.sleep(REFRESH_INTERVAL)
st.rerun()