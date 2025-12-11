# Implementation Plan

## 1. 프로젝트 구조 및 기반 설정 (Git 기반 배포 준비)

- [ ] 1.1 Git 저장소 설정 및 프로젝트 구조 생성
  - 현재 워크스페이스를 Git 저장소로 초기화 (이미 존재하는 경우 스킵)
  - 원격 저장소 연결 설정
  - 기본 프로젝트 구조 확인/생성 (backend/, zendesk-app/, shared/, docs/, scripts/)
  - EC2 배포를 위한 .gitignore 및 배포 스크립트 생성
  - _Requirements: 7.2_
  - _배포 참고: EC2에서 git clone/pull로 코드 동기화_

- [ ] 1.2 기본 설정 파일 생성
  - requirements.txt 생성 (flask-socketio, boto3, python-dotenv 등)
  - .env.example 환경 변수 템플릿 생성
  - .gitignore 파일 생성
  - README.md 프로젝트 문서 생성
  - _Requirements: 7.2, 7.4_

- [ ] 1.3 Docker 컨테이너 설정
  - Dockerfile 생성 (Python 3.11 기반)
  - docker-compose.yml 생성
  - 컨테이너 리소스 제한 설정
  - _Requirements: 7.1_

## 2. 기존 코드 이식 및 코어 모듈 개발

- [ ] 2.1 AWS 처리 코어 모듈 생성
  - backend/core/aws_processor.py 구현
  - 기존 botQ의 AWS 로직 이식 (analyze_question_type, process_question_async)
  - 플랫폼 독립적으로 리팩토링
  - _Requirements: 4.1_

- [ ]* 2.2 AWS 처리 모듈 속성 테스트 작성
  - **Property 3: Output Consistency with Slack Bot**
  - **Validates: Requirements 4.1, 4.2, 4.5**

- [ ] 2.3 Cross-Account 인증 모듈 구현
  - backend/core/auth_manager.py 생성
  - 기존 get_crossaccount_credentials, get_crossaccount_session 로직 이식
  - STS assume role 프로세스 구현
  - _Requirements: 4.3_

- [ ]* 2.4 Cross-Account 인증 속성 테스트 작성
  - **Property 7: Cross-Account Authentication Consistency**
  - **Validates: Requirements 4.3**

- [ ] 2.5 Service Screener 모듈 구현
  - backend/core/screener.py 생성
  - 기존 run_service_screener 로직 이식
  - 진행률 콜백 시스템 추가
  - _Requirements: 1.4, 4.5_

- [ ]* 2.6 Service Screener 속성 테스트 작성
  - **Property 3: Output Consistency with Slack Bot**
  - **Validates: Requirements 4.5**

## 3. 웹소켓 서버 구현

- [ ] 3.1 기본 웹소켓 서버 구조 생성
  - backend/main.py Flask-SocketIO 서버 구현
  - 연결 관리 및 기본 이벤트 핸들러 구현
  - CORS 설정 및 보안 헤더 추가
  - _Requirements: 1.2_

- [ ]* 3.2 웹소켓 통신 속성 테스트 작성
  - **Property 1: Real-time WebSocket Communication**
  - **Validates: Requirements 1.2, 1.3, 2.3**

- [ ] 3.3 진행률 추적 시스템 구현
  - backend/utils/progress_tracker.py 생성
  - 실시간 진행률 브로드캐스팅 구현
  - 시간 추정 및 단계별 업데이트 로직
  - _Requirements: 2.1, 2.2_

- [ ]* 3.4 진행률 추적 속성 테스트 작성
  - **Property 2: Progress Tracking Consistency**
  - **Validates: Requirements 2.1, 2.2, 2.4**

- [ ] 3.5 메시지 라우터 및 처리기 구현
  - AWS 쿼리 메시지 처리 로직
  - 비동기 작업 관리 (Threading)
  - 결과 응답 및 에러 처리
  - _Requirements: 1.3, 1.5_

## 4. 인증 및 보안 시스템

- [ ] 4.1 Zendesk JWT 인증 구현
  - backend/auth/zendesk_auth.py 생성
  - JWT 토큰 검증 로직 구현
  - 사용자 권한 확인 시스템
  - _Requirements: 5.1, 5.2_

- [ ]* 4.2 인증 및 권한 속성 테스트 작성
  - **Property 4: Authentication and Authorization**
  - **Validates: Requirements 5.1, 5.2, 5.4, 5.5**

- [ ] 4.3 감사 로깅 시스템 구현
  - backend/utils/audit_logger.py 생성
  - 모든 AWS 요청 로깅
  - 사용자 식별 및 보안 이벤트 기록
  - _Requirements: 5.3_

- [ ]* 4.4 감사 로깅 속성 테스트 작성
  - **Property 9: Audit Logging**
  - **Validates: Requirements 5.3**

## 5. 보고서 생성 및 관리

- [ ] 5.1 보고서 생성 모듈 구현
  - backend/core/report_generator.py 생성
  - 기존 HTML 템플릿 이식 및 적용
  - 보고서 URL 생성 및 관리
  - _Requirements: 6.1_

- [ ] 5.2 공유 리소스 복사
  - shared/templates/ 디렉터리에 기존 HTML 템플릿 복사
  - shared/contexts/ 디렉터리에 기존 컨텍스트 파일들 복사
  - 템플릿 경로 및 참조 업데이트
  - _Requirements: 4.2_

- [ ]* 5.3 보고서 생성 속성 테스트 작성
  - **Property 5: Report Generation and Attachment**
  - **Validates: Requirements 6.1, 6.2, 6.3**

## 6. MCP 도구 연동

- [ ] 6.1 MCP 통합 모듈 구현
  - backend/core/mcp_integrations.py 생성
  - CloudTrail MCP 연동 구현
  - CloudWatch MCP 연동 구현
  - General AWS MCP 연동 구현
  - _Requirements: 4.4_

- [ ]* 6.2 MCP 통합 속성 테스트 작성
  - **Property 8: MCP Integration Consistency**
  - **Validates: Requirements 4.4**

## 7. Zendesk 앱 프론트엔드 개발

- [ ] 7.1 Zendesk 앱 기본 구조 생성
  - zendesk-app/manifest.json 생성
  - 앱 메타데이터 및 권한 설정
  - 기본 디렉터리 구조 생성
  - _Requirements: 1.1_

- [ ] 7.2 메인 UI 인터페이스 구현
  - zendesk-app/assets/iframe.html 생성
  - 채팅 인터페이스 HTML 구조
  - 진행률 표시 UI 컴포넌트
  - 보고서 뷰어 인터페이스
  - _Requirements: 1.1, 2.2_

- [ ] 7.3 웹소켓 클라이언트 로직 구현
  - zendesk-app/app.js 메인 JavaScript 구현
  - Socket.IO 클라이언트 연결 관리
  - 실시간 메시지 처리 및 UI 업데이트
  - 에러 처리 및 재연결 로직
  - _Requirements: 1.2, 1.3_

- [ ] 7.4 UI 스타일링 및 UX 개선
  - zendesk-app/app.css 스타일시트 구현
  - 반응형 디자인 적용
  - 채팅 인터페이스 애니메이션
  - 진행률 바 및 시각적 피드백
  - _Requirements: 2.2_

## 8. 에러 처리 및 복원력

- [ ] 8.1 종합적인 에러 처리 시스템 구현
  - backend/utils/error_handler.py 생성
  - 카테고리별 에러 처리 로직
  - 사용자 친화적 에러 메시지 생성
  - _Requirements: 8.1_

- [ ]* 8.2 에러 처리 속성 테스트 작성
  - **Property 6: Error Handling and Resilience**
  - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

- [ ] 8.3 재시도 및 복원 로직 구현
  - 지수 백오프 재시도 메커니즘
  - 네트워크 연결 실패 처리
  - 타임아웃 상황 관리
  - _Requirements: 8.3, 8.4_

- [ ] 8.4 구조화된 로깅 시스템 구현
  - backend/utils/logger.py 생성
  - JSON 형식 로그 출력
  - 로그 레벨별 설정 관리
  - _Requirements: 8.5_

## 9. 헬스 체크 및 모니터링

- [ ] 9.1 헬스 체크 엔드포인트 구현
  - /health API 엔드포인트 생성
  - 시스템 상태 확인 로직
  - 의존성 서비스 상태 체크
  - _Requirements: 7.5_

- [ ]* 9.2 헬스 모니터링 속성 테스트 작성
  - **Property 10: Health Monitoring**
  - **Validates: Requirements 7.5**

## 10. 통합 테스트 및 EC2 배포 준비

- [ ] 10.1 통합 테스트 환경 구축
  - 로컬 개발 환경 설정 (WebSocket 서버 로컬 실행)
  - 테스트용 Zendesk 앱 설정
  - EC2 배포 전 로컬 통합 테스트
  - Git 배포 워크플로우 테스트 (staging 환경)
  - _Requirements: 전체_
  - _참고: 최종 배포는 EC2 콘솔에서 git clone/pull 방식_

- [ ] 10.2 EC2 배포 스크립트 및 문서 작성
  - scripts/deploy.sh EC2 배포 스크립트 생성 (git pull + 서비스 재시작)
  - scripts/setup_ec2.sh EC2 초기 환경 설정 스크립트
  - docs/deployment.md EC2 배포 가이드 작성 (Git 기반 배포 워크플로우)
  - docs/security_group.md 보안 그룹 설정 가이드
  - docs/api.md WebSocket API 문서 작성
  - _Requirements: 7.2_
  - _배포 환경: 실제 EC2 콘솔에서 Git 기반 배포_

- [ ] 10.3 최종 검증 및 성능 테스트
  - 모든 테스트 통과 확인
  - 성능 벤치마크 실행
  - 보안 검증 완료
  - _Requirements: 전체_

## 11. Checkpoint - 모든 테스트 통과 확인
- 모든 테스트가 통과하는지 확인하고, 문제가 있으면 사용자에게 질문합니다.

## 12. EC2 배포 및 운영 가이드

### Git 기반 배포 워크플로우

**로컬 개발 → EC2 배포 프로세스:**

```bash
# 1. 로컬에서 개발 완료
git add .
git commit -m "기능 구현 완료"
git push origin main

# 2. EC2에서 배포 (SSH 접속 후)
cd /opt/zendesk-websocket-integration
git pull origin main
./scripts/deploy.sh

# 3. 서비스 상태 확인
systemctl status zendesk-websocket
docker-compose ps  # Docker 사용 시
```

### EC2 환경 설정 체크리스트

**보안 그룹 설정:**
- [ ] 인바운드 규칙: 모두 삭제 (완전 차단)
- [ ] 아웃바운드 규칙: HTTPS(443), HTTP(80), WebSocket(5000), DNS(53)
- [ ] SSH(22): 관리자 IP만 허용 (Git 배포용)

**인스턴스 설정:**
- [ ] Public IP 할당 또는 Elastic IP 연결
- [ ] 인스턴스 타입: t3.medium 이상
- [ ] 스토리지: 최소 20GB
- [ ] IAM 역할: 기존 Cross-account 권한 유지

**소프트웨어 설치:**
- [ ] Git, Python 3.11, Node.js
- [ ] Docker & Docker Compose (선택사항)
- [ ] 기존 Q CLI 및 Service Screener 환경 유지

**환경 변수 설정:**
- [ ] AWS 자격증명 (기존 설정 유지)
- [ ] WebSocket 포트 설정
- [ ] Zendesk JWT 시크릿

### 운영 모니터링

**로그 확인:**
```bash
# WebSocket 서버 로그
tail -f /var/log/zendesk-websocket.log

# 시스템 로그
journalctl -u zendesk-websocket -f
```

**성능 모니터링:**
```bash
# 프로세스 상태
ps aux | grep websocket

# 메모리 사용량
free -h

# 디스크 사용량 (/tmp/reports 정리)
df -h
du -sh /tmp/reports/*
```

### 트러블슈팅

**일반적인 문제:**
1. **WebSocket 연결 실패**: 보안 그룹 아웃바운드 규칙 확인
2. **AWS API 오류**: Cross-account 자격증명 확인
3. **Service Screener 실패**: 기존 환경 설정 확인
4. **메모리 부족**: 인스턴스 타입 업그레이드 고려

**배포 롤백:**
```bash
# 이전 커밋으로 롤백
git log --oneline -10
git checkout <이전_커밋_해시>
./scripts/deploy.sh
```