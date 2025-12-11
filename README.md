# AWS Zendesk WebSocket Integration

AWS 보안 분석 도구를 Zendesk 앱으로 제공하는 WebSocket 기반 실시간 통신 시스템

## 📋 프로젝트 개요

기존 Slack 봇의 모든 AWS 보안 분석 기능을 Zendesk 환경으로 이식하는 실시간 통신 시스템입니다.

### 주요 기능
- **Service Screener**: AWS 계정 종합 보안 점검
- **보안 보고서**: 월간 보안 점검 보고서 생성
- **CloudTrail 분석**: 사용자 활동 및 보안 이벤트 추적
- **CloudWatch 모니터링**: 알람 및 메트릭 분석
- **실시간 진행률**: WebSocket을 통한 실시간 업데이트

## 🏗️ 아키텍처

```
Zendesk App → WebSocket → EC2 (Public, 인바운드 차단) → AWS 분석
```

### 보안 설계
- **Public EC2**: 인바운드 포트 완전 차단
- **WebSocket**: 아웃바운드 연결만 사용
- **Cross-Account**: STS Assume Role 기반 인증

## 🚀 배포 방법

### 로컬 개발
```bash
git clone <repository-url>
cd aws-zendesk-assistant
pip install -r requirements.txt
python backend/main.py
```

### EC2 배포
```bash
# EC2에서 실행
git clone <repository-url>
cd aws-zendesk-assistant
./scripts/deploy.sh
```

## 📁 프로젝트 구조

```
├── backend/                 # WebSocket 서버 (Python)
├── zendesk-app/            # Zendesk 앱 (JavaScript)
├── shared/                 # 공유 리소스 (템플릿, 컨텍스트)
├── reference_contexts/     # 기존 Slack 봇 컨텍스트
├── reference_slack_bot.py  # 기존 Slack 봇 코드 (참조용)
├── scripts/               # 배포 스크립트
├── docs/                  # 문서
└── .kiro/specs/          # 기능 스펙 문서
```

## 🔧 환경 설정

### 필수 환경 변수
```bash
AWS_DEFAULT_REGION=ap-northeast-2
WEBSOCKET_PORT=5000
ZENDESK_JWT_SECRET=<시크릿>
```

### AWS 권한
- Cross-account STS Assume Role 권한
- Service Screener 실행 권한
- CloudTrail, CloudWatch 조회 권한

## 📚 문서

- [기능 스펙](.kiro/specs/zendesk-websocket-integration/)
- [배포 가이드](docs/deployment.md)
- [보안 설정](docs/security_group.md)
- [API 문서](docs/api.md)

## 🤝 기여 방법

1. 로컬에서 개발
2. Git commit & push
3. EC2에서 git pull & 배포

## 📞 문의

보안팀 또는 DevOps 팀에 문의하세요.