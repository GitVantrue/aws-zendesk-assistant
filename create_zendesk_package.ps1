# Zendesk 앱 패키징 스크립트 (PowerShell)
# 역할: zendesk_app 폴더를 zip으로 패키징

$ErrorActionPreference = "Stop"

Write-Host "🔧 Zendesk 앱 패키징 시작..." -ForegroundColor Cyan

# 작업 디렉토리
$WORK_DIR = Get-Location
$ZENDESK_APP_DIR = Join-Path $WORK_DIR "zendesk_app"
$OUTPUT_FILE = Join-Path $WORK_DIR "zendesk-aws-assistant.zip"

# 기존 zip 파일 제거
if (Test-Path $OUTPUT_FILE) {
    Write-Host "📦 기존 패키지 제거: $OUTPUT_FILE" -ForegroundColor Yellow
    Remove-Item $OUTPUT_FILE -Force
}

# manifest.json 확인
$MANIFEST = Join-Path $ZENDESK_APP_DIR "manifest.json"
if (-not (Test-Path $MANIFEST)) {
    Write-Host "❌ manifest.json을 찾을 수 없습니다: $MANIFEST" -ForegroundColor Red
    exit 1
}

# assets 폴더 확인
$ASSETS = Join-Path $ZENDESK_APP_DIR "assets"
if (-not (Test-Path $ASSETS)) {
    Write-Host "❌ assets 폴더를 찾을 수 없습니다: $ASSETS" -ForegroundColor Red
    exit 1
}

# zip 파일 생성
Write-Host "📦 패키징 중..." -ForegroundColor Cyan

# PowerShell에서 zip 생성 (Windows 10 이상)
try {
    # 임시 폴더 생성
    $TEMP_DIR = Join-Path $WORK_DIR "temp_zendesk_package"
    if (Test-Path $TEMP_DIR) {
        Remove-Item $TEMP_DIR -Recurse -Force
    }
    New-Item -ItemType Directory -Path $TEMP_DIR | Out-Null
    
    # 파일 복사
    Copy-Item $MANIFEST -Destination (Join-Path $TEMP_DIR "manifest.json")
    Copy-Item $ASSETS -Destination (Join-Path $TEMP_DIR "assets") -Recurse
    
    # zip 생성
    Compress-Archive -Path (Join-Path $TEMP_DIR "*") -DestinationPath $OUTPUT_FILE -Force
    
    # 임시 폴더 제거
    Remove-Item $TEMP_DIR -Recurse -Force
    
    Write-Host "✅ 패키징 완료!" -ForegroundColor Green
    Write-Host "📁 파일: $OUTPUT_FILE" -ForegroundColor Green
    
    $SIZE = (Get-Item $OUTPUT_FILE).Length / 1MB
    Write-Host "📊 크기: $([Math]::Round($SIZE, 2)) MB" -ForegroundColor Green
    
    Write-Host ""
    Write-Host "📋 패키지 내용:" -ForegroundColor Cyan
    $ZIP = [System.IO.Compression.ZipFile]::OpenRead($OUTPUT_FILE)
    $ZIP.Entries | ForEach-Object { Write-Host "  - $($_.FullName)" }
    $ZIP.Dispose()
    
} catch {
    Write-Host "❌ 패키징 실패: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "🚀 다음 단계:" -ForegroundColor Cyan
Write-Host "1. Zendesk 마켓플레이스에 로그인"
Write-Host "2. 앱 업로드: $OUTPUT_FILE"
Write-Host "3. 테스트 및 배포"
