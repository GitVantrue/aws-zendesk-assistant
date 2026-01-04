#!/bin/bash

# Zendesk 앱 패키징 스크립트
# 역할: zendesk_app 폴더를 zip으로 패키징

set -e

echo "🔧 Zendesk 앱 패키징 시작..."

# 작업 디렉토리
WORK_DIR=$(pwd)
ZENDESK_APP_DIR="$WORK_DIR/zendesk_app"
OUTPUT_FILE="$WORK_DIR/zendesk-aws-assistant.zip"

# 기존 zip 파일 제거
if [ -f "$OUTPUT_FILE" ]; then
    echo "📦 기존 패키지 제거: $OUTPUT_FILE"
    rm "$OUTPUT_FILE"
fi

# manifest.json 확인
if [ ! -f "$ZENDESK_APP_DIR/manifest.json" ]; then
    echo "❌ manifest.json을 찾을 수 없습니다: $ZENDESK_APP_DIR/manifest.json"
    exit 1
fi

# assets 폴더 확인
if [ ! -d "$ZENDESK_APP_DIR/assets" ]; then
    echo "❌ assets 폴더를 찾을 수 없습니다: $ZENDESK_APP_DIR/assets"
    exit 1
fi

# zip 파일 생성 (manifest.json과 assets만 포함)
echo "📦 패키징 중..."
cd "$ZENDESK_APP_DIR"
zip -r "$OUTPUT_FILE" manifest.json assets/
cd "$WORK_DIR"

# 결과 확인
if [ -f "$OUTPUT_FILE" ]; then
    SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
    echo "✅ 패키징 완료!"
    echo "📁 파일: $OUTPUT_FILE"
    echo "📊 크기: $SIZE"
    echo ""
    echo "📋 패키지 내용:"
    unzip -l "$OUTPUT_FILE"
else
    echo "❌ 패키징 실패"
    exit 1
fi

echo ""
echo "🚀 다음 단계:"
echo "1. Zendesk 마켓플레이스에 로그인"
echo "2. 앱 업로드: $OUTPUT_FILE"
echo "3. 테스트 및 배포"
