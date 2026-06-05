# 스마트 공기질 대시보드

## 1. 프로젝트 개요

본 프로젝트는 AirGradient 센서를 이용하여 실내 공기질 데이터를 측정하고, Streamlit 기반 대시보드에서 시각화하는 시스템입니다.

측정 항목은 PM2.5, CO2, 온도, 습도, TVOC, NOx이며, 사용자는 대시보드를 통해 현재 공기질 상태와 최근 측정 기록을 확인할 수 있습니다.

또한 기준값 초과 시 이메일 알림 또는 플러그 제어 기능을 통해 실내 공기질 개선을 유도할 수 있도록 구성하였습니다.

Gemini AI를 활용하여 현재 공기질 데이터를 분석하고, 종합 평가, 위험 요소, 행동 권고 사항을 포함한 분석 리포트를 제공합니다.

## 2. 주요 기능

* 실내 공기질 데이터 표시
* PM2.5, CO2, 온도, 습도, TVOC, NOx 값 확인
* 최근 측정 기록 표 출력
* 측정 데이터 그래프 시각화
* CSV 파일 기반 측정 데이터 저장 및 불러오기
* 기준값 초과 시 이메일 알림
* Streamlit Secrets를 이용한 이메일 비밀번호 및 API 키 관리
* 스마트 플러그 자동/수동 제어 기능
* Gemini AI 기반 공기질 분석 리포트 제공
* 구독 코드를 기반으로 AI 분석 페이지 잠금 기능

## 3. 프로젝트 구조
```
air/
├─ pages/
│  ├─ 구독_AI.py
│  └─ 상세.py
├─ .streamlit/
│  └─ secrets.toml.example
├─ 메인.py
├─ data_log.csv
├─ requirements.txt
├─ README.md
└─ .gitignore
```

## 4. 실행 환경

본 프로젝트는 Python 기반 Streamlit 대시보드로 제작되었습니다.

- Python 3.x
- streamlit
- pandas
- requests
- plotly
- paho-mqtt
- google-genai

필요한 라이브러리는 `requirements.txt`에 정리되어 있습니다.

## 5. 설치 방법

프로젝트 폴더에서 아래 명령어를 실행합니다.

```bash
pip install -r requirements.txt
```

## 6. 실행 방법

아래 명령어를 입력하여 Streamlit 대시보드를 실행합니다.

```bash
streamlit run 메인.py
```

실행 후 브라우저에서 대시보드 화면을 확인할 수 있습니다.

## 7. 데이터 파일

`data_log.csv`는 대시보드 실행 확인을 위한 샘플 측정 데이터입니다.

전체 원시 측정 데이터는 별도의 CSV 또는 JSON 파일로 제출하였습니다.

CSV 파일의 기본 컬럼 구조는 다음과 같습니다.

| 컬럼명      | 설명        |
| -------- | --------- |
| time     | 측정 시간     |
| PM2.5    | 초미세먼지 농도  |
| co2      | 이산화탄소 농도  |
| temp     | 온도        |
| humidity | 습도        |
| tvoc     | 총휘발성유기화합물 |
| nox      | 질소산화물     |

## 8. Secrets 설정

본 프로젝트는 이메일 알림 및 API 연동을 위해 Streamlit Secrets를 사용합니다.

보안상 실제 이메일 비밀번호와 API 키는 GitHub에 포함하지 않았습니다.

로컬에서 실행하려면 `.streamlit/secrets.toml.example` 파일을 참고하여 `.streamlit/secrets.toml` 파일을 직접 생성해야 합니다.

예시는 다음과 같습니다.

```toml
EMAIL_ADDRESS = "your_email@gmail.com"
EMAIL_PASSWORD = "your_app_password"
AIRGRADIENT_API_TOKEN = "your_airgradient_api_token"
SUBSCRIPTION_CODE = "your_subscription_code"
SUBSCRIPTION_CODE = "your_subscription_code"
```

Streamlit Community Cloud에 배포할 경우, 앱 설정의 Secrets 메뉴에 동일한 내용을 입력해야 합니다.

## 9. 보안 관련 주의사항

다음 파일은 GitHub에 업로드하지 않습니다.

```text
.streamlit/secrets.toml
.env
.venv/
__pycache__/
```

실제 이메일 앱 비밀번호, API 키, 개인 IP 주소는 공개 저장소에 포함하지 않습니다.

## 10. 실행 링크

배포된 대시보드는 아래 링크에서 확인할 수 있습니다.

```text
https://y9aciw4c4iidunh2vcaxqf.streamlit.app/
```

## 11. 제출 내용

본 GitHub 저장소에는 대시보드 소스 코드, 실행에 필요한 라이브러리 목록, 샘플 데이터, 실행 방법, Secrets 설정 예시를 포함하였습니다.

전체 측정 원시 데이터는 별도 파일로 제출하였습니다.
