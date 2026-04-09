
import requests

def control_tasmota(ip, command):
    """
    command: 'ON', 'OFF', 'TOGGLE' 중 하나
    """
    url = f"http://{ip}/cm?cmnd=Power%20{command}"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            print(f"성공: 플러그 상태를 {command}(으)로 변경했습니다.")
            print(f"응답 데이터: {response.json()}")
        else:
            print(f"오류 발생: 상태 코드 {response.status_code}")
    except Exception as e:
        print(f"연결 실패: {e}")

# 사용 예시
DEVICE_IP = "10.87.189.225"  # 실제 플러그 IP로 변경하세요.

# 플러그 켜기
control_tasmota(DEVICE_IP, "ON")

# 플러그 끄기
# control_tasmota(DEVICE_IP, "OFF")