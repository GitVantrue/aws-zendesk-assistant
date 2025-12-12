# Zendesk WebSocket Integration - 현재 상태

## 완료된 작업

### 1. 프로젝트 구조 및 Git 설정
- GitHub 저장소 생성: `https://github.com/GitVantrue/aws-zendesk-assistant.git`
- EC2 배포 워크플로우 구축 (git push → EC2 git pull)

### 2. Zendesk 앱 UI 개발
- 완전한 Zendesk 앱 구현 (manifest.json, HTML, CSS, JavaScript)
- 현대적인 glassmorphism UI 디자인
- WebSocket 클라이언트 로직 구현
- 로컬 HTTP 서버로 테스트 완료

### 3. WebSocket 서버 개발
- Flask-SocketIO 기반 서버 구현
- 기존 Slack bot 로직 완전 포팅
- Cross-account AWS 접근 지원
- 실시간 진행률 업데이트

### 4. AWS EC2 배포
- Private EC2 인스턴스에 배포
- 기존 ALB 인프라 활용
- `/zendesk/*` 경로로 라우팅 설정
- Gunicorn + eventlet으로 프로덕션 실행

### 5. 실제 AWS 기능 구현
- Q CLI 실행 (Service Screener 스캔)
- 월간 보안 보고서 생성
- HTML 보고서 생성 및 저장
- 로컬 파일 경로를 웹 URL로 변환

## 최신 수정사항 (2025-12-12)

### ✅ 완료: Slack bot 코드 정확히 포팅
- `collect_raw_security_data()` 함수를 Slack bot과 동일하게 구현
- `generate_html_report()` 함수를 Slack bot과 동일하게 구현
- Raw JSON 데이터 구조를 Slack bot과 정확히 일치
- EC2, S3, RDS, Lambda, IAM, 보안 그룹, CloudTrail, CloudWatch, Trusted Advisor 모두 수집
- HTML 보고서 템플릿 정확히 적용

### 커밋 정보
- **Commit**: `cc17763`
- **Message**: "Replace with exact Slack bot implementation for data collection and HTML report generation"

## EC2 배포 절차 (매번 git push 후 실행)

```bash
# EC2에 접속 후 다음 명령어 실행:
cd /home/ec2-user/aws-zendesk-assistant
git pull origin main
sudo pkill -f websocket_server.py
nohup python3 websocket_server.py > /tmp/websocket_server.log 2>&1 &
tail -f /tmp/websocket_server.log
```

**각 명령어 설명**:
1. `cd /home/ec2-user/aws-zendesk-assistant` - 프로젝트 디렉토리로 이동
2. `git pull origin main` - 최신 코드 다운로드
3. `sudo pkill -f websocket_server.py` - 기존 WebSocket 서버 프로세스 종료
4. `nohup python3 websocket_server.py > /tmp/websocket_server.log 2>&1 &` - 새로운 서버 시작 (백그라운드)
5. `tail -f /tmp/websocket_server.log` - 실시간 로그 확인 (Ctrl+C로 종료)

## 주요 파일 위치

- **WebSocket 서버**: `/home/ec2-user/aws-zendesk-assistant/websocket_server.py`
- **Zendesk 앱**: `/home/ec2-user/aws-zendesk-assistant/zendesk-app/`
- **Service Screener**: `/home/ec2-user/aws-zendesk-assistant/service-screener-v2/`
- **보고서 저장소**: `/tmp/reports/`
- **로그**: `/tmp/websocket_server.log`

## ⚠️ 중요: 경로 설정 주의사항

### Reference 코드 vs 현재 환경 경로 차이

**Reference 코드 (reference_slack_bot.py):**
- Service Screener 위치: `/root/service-screener-v2/`
- 결과 디렉터리: `/root/service-screener-v2/aws/{account_id}/`
- 실행 명령어: `python3 /root/service-screener-v2/Screener.py --crossAccounts {config.json}`

**현재 EC2 환경:**
- Service Screener 위치: `/home/ec2-user/aws-zendesk-assistant/service-screener-v2/`
- 결과 디렉터리: `/home/ec2-user/aws-zendesk-assistant/service-screener-v2/aws/{account_id}/`
- 실행 명령어: `python3 /home/ec2-user/aws-zendesk-assistant/service-screener-v2/main.py --regions {regions}`

### 코드 작성 시 필수 사항

1. **절대 경로 사용 금지** - 상대 경로 또는 `os.path.dirname(__file__)` 사용
2. **Reference 코드 참고 시** - 경로를 현재 환경에 맞게 변환
3. **Service Screener 실행** - `Screener.py` 사용 (main.py 아님)
4. **결과 위치** - `adminlte/aws/{account_id}/` 또는 `aws/{account_id}/` 확인 필요

### 경로 변환 예시

```python
# ❌ 잘못된 방식 (Reference 코드 그대로)
screener_path = '/root/service-screener-v2/Screener.py'

# ✅ 올바른 방식 (현재 환경)
screener_base = os.path.join(os.path.dirname(__file__), 'service-screener-v2')
screener_path = os.path.join(screener_base, 'Screener.py')
```

## 다음 단계

1. ✅ `/reports/` 라우트 구현 완료
2. Service Screener 실행 로직 수정 (Screener.py + --crossAccounts 사용)
3. 결과 디렉터리 경로 확인 및 복사 로직 수정
4. 테스트: 월간 보고서 생성 후 웹 접근 확인
