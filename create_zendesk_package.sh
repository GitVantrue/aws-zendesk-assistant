#!/bin/bash

# Zendesk 앱 패키징 스크립트
# 사용법: bash create_zendesk_package.sh

set -e

echo "🔄 Zendesk 앱 패키징 시작..."

# 임시 디렉토리 생성
TEMP_DIR=$(mktemp -d)
PACKAGE_DIR="$TEMP_DIR/zendesk-aws-assistant"
mkdir -p "$PACKAGE_DIR/assets"

echo "📁 패키지 구조 생성 중..."

# manifest.json 복사
cp zendesk_app/manifest.json "$PACKAGE_DIR/"

# assets 파일 복사
cp zendesk_app/assets/iframe.html "$PACKAGE_DIR/assets/"
cp zendesk_app/assets/main.js "$PACKAGE_DIR/assets/"
cp zendesk_app/assets/logo.svg "$PACKAGE_DIR/assets/"

# 영어 번역 파일만 복사
mkdir -p "$PACKAGE_DIR/assets/translations"
cp zendesk_app/assets/translations/en.json "$PACKAGE_DIR/assets/translations/"

echo "📦 ZIP 파일 생성 중..."

# ZIP 파일 생성
cd "$TEMP_DIR"
zip -r zendesk-aws-assistant.zip zendesk-aws-assistant/
cd -

# 최종 위치로 이동
mv "$TEMP_DIR/zendesk-aws-assistant.zip" ./zendesk-aws-assistant.zip

echo "✅ 완료!"
echo ""
echo "📊 패키지 정보:"
ls -lh zendesk-aws-assistant.zip
echo ""
echo "📋 패키지 내용:"
unzip -l zendesk-aws-assistant.zip
echo ""
echo "🚀 배포 준비 완료!"
echo "   Zendesk 마켓플레이스에 zendesk-aws-assistant.zip을 업로드하세요."
echo ""
echo "⚙️  주의사항:"
echo "   1. Python 서버가 EC2에서 실행 중이어야 합니다"
echo "   2. manifest.json의 serverUrl을 EC2 주소로 설정하세요"
echo "   3. 앱 설정에서 serverUrl 파라미터를 입력해야 합니다"

# 정리
rm -rf "$TEMP_DIR"
