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

## 현재 이슈 및 해결 방법

### 문제: ALB를 통한 `/reports/` 엔드포인트 404 에러

**원인**: WebSocket 서버에 `/reports/` 라우트가 없어서 ALB가 요청을 처리할 수 없음

**해결책**: 
1. Flask 라우트 추가: `@app.route('/reports/<path:filename>')`
2. `/tmp/reports/` 디렉토리의 파일을 웹으로 제공
3. 디렉토리 구조 지원 (Service Screener 결과 디렉토리)
4. 적절한 MIME 타입 설정

**구현 위치**: `websocket_server.py` 라인 1162-1210

**테스트 방법**:
```bash
# 로컬에서 테스트
curl -I http://q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com/reports/security_report_950027134314_20251212_035333.html

# 또는 브라우저에서
http://q-slack-lb-353058502.ap-northeast-2.elb.amazonaws.com/reports/security_report_950027134314_20251212_035333.html
```

## 배포 절차

1. 로컬에서 코드 수정
2. `git add` → `git commit` → `git push`
3. EC2에서 `git pull origin main`
4. `sudo pkill -f websocket_server.py` (기존 프로세스 종료)
5. `nohup python3 websocket_server.py > /tmp/websocket_server.log 2>&1 &` (재시작)
6. `tail -f /tmp/websocket_server.log` (로그 확인)

## 주요 파일 위치

- **WebSocket 서버**: `/home/ec2-user/aws-zendesk-assistant/websocket_server.py`
- **Zendesk 앱**: `/home/ec2-user/aws-zendesk-assistant/zendesk-app/`
- **보고서 저장소**: `/tmp/reports/`
- **로그**: `/tmp/websocket_server.log`

## 다음 단계

1. ✅ `/reports/` 라우트 구현 완료
2. 테스트: 월간 보고서 생성 후 웹 접근 확인
3. Service Screener 결과 디렉토리 웹 접근 확인
4. 필요시 ALB 헬스 체크 설정 조정
