#!/bin/bash

# Zendesk 앱 패키징 스크립트 (macOS/Linux)
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
    rm -f "$OUTPUT_FILE"
fi

# manifest.json 확인
MANIFEST="$ZENDESK_APP_DIR/manifest.json"
if [ ! -f "$MANIFEST" ]; then
    echo "❌ manifest.json을 찾을 수 없습니다: $MANIFEST"
    exit 1
fi

# assets 폴더 확인
ASSETS="$ZENDESK_APP_DIR/assets"
if [ ! -d "$ASSETS" ]; then
    echo "❌ assets 폴더를 찾을 수 없습니다: $ASSETS"
    exit 1
fi

# translations 폴더 확인
TRANSLATIONS="$ZENDESK_APP_DIR/translations"
if [ ! -d "$TRANSLATIONS" ]; then
    echo "❌ translations 폴더를 찾을 수 없습니다: $TRANSLATIONS"
    exit 1
fi

# zip 파일 생성
echo "📦 패키징 중..."

# 임시 디렉토리 생성
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# 파일 복사
cp "$MANIFEST" "$TEMP_DIR/manifest.json"
cp -r "$ASSETS" "$TEMP_DIR/assets"
cp -r "$TRANSLATIONS" "$TEMP_DIR/translations"

# zip 생성
cd "$TEMP_DIR"
zip -r "$OUTPUT_FILE" manifest.json assets translations > /dev/null
cd "$WORK_DIR"

echo "✅ 패키징 완료!"
echo "📁 파일: $OUTPUT_FILE"

SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
echo "📊 크기: $SIZE"

echo ""
echo "📋 패키지 내용:"
unzip -l "$OUTPUT_FILE" | tail -n +4 | head -n -2 | awk '{print "  - " $4}'

echo ""
echo "🚀 다음 단계:"
echo "1. Zendesk 마켓플레이스에 로그인"
echo "2. 앱 업로드: $OUTPUT_FILE"
echo "3. 테스트 및 배포"
