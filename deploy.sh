#!/bin/bash

# AWS Zendesk Assistant 배포 스크립트
# 사용법: bash deploy.sh

set -e

echo "[INFO] AWS Zendesk Assistant 배포 시작..."

# 1. Git 업데이트
echo "[INFO] Git 업데이트 중..."
cd /root/aws-zendesk-assistant
git pull origin main

# 2. 기존 서비스 중지
echo "[INFO] 기존 서비스 중지 중..."
sudo systemctl stop zendesk-websocket.service 2>/dev/null || true
sudo systemctl stop zendesk-fastapi.service 2>/dev/null || true
sleep 2

# 3. 서비스 파일 복사
echo "[INFO] systemd 서비스 파일 설치 중..."
sudo cp /root/aws-zendesk-assistant/zendesk-websocket.service /etc/systemd/system/
sudo cp /root/aws-zendesk-assistant/zendesk-fastapi.service /etc/systemd/system/
sudo systemctl daemon-reload

# 4. 서비스 시작
echo "[INFO] 서비스 시작 중..."
sudo systemctl start zendesk-websocket.service
sudo systemctl start zendesk-fastapi.service

# 5. 서비스 활성화 (부팅 시 자동 시작)
echo "[INFO] 서비스 자동 시작 설정 중..."
sudo systemctl enable zendesk-websocket.service
sudo systemctl enable zendesk-fastapi.service

# 6. 상태 확인
echo "[INFO] 서비스 상태 확인 중..."
sleep 3
sudo systemctl status zendesk-websocket.service
sudo systemctl status zendesk-fastapi.service

echo "[INFO] ✅ 배포 완료!"
echo ""
echo "📋 서비스 관리 명령어:"
echo "  상태 확인: sudo systemctl status zendesk-websocket.service"
echo "  상태 확인: sudo systemctl status zendesk-fastapi.service"
echo "  로그 확인: sudo journalctl -u zendesk-websocket.service -f"
echo "  로그 확인: sudo journalctl -u zendesk-fastapi.service -f"
echo "  서비스 재시작: sudo systemctl restart zendesk-websocket.service"
echo "  서비스 재시작: sudo systemctl restart zendesk-fastapi.service"
