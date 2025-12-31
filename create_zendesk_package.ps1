# Zendesk 앱 패키징 스크립트 (PowerShell)
# 사용법: .\create_zendesk_package.ps1

Write-Host "🔄 Zendesk 앱 패키징 시작..." -ForegroundColor Cyan

# 임시 디렉토리 생성
$tempDir = New-Item -ItemType Directory -Path ([System.IO.Path]::GetTempPath() + [System.Guid]::NewGuid().ToString())
$packageDir = Join-Path $tempDir "zendesk-aws-assistant"
$assetsDir = Join-Path $packageDir "assets"

New-Item -ItemType Directory -Path $assetsDir -Force | Out-Null

Write-Host "📁 패키지 구조 생성 중..." -ForegroundColor Yellow

# manifest.json 복사
Copy-Item "zendesk_app/manifest.json" "$packageDir/"

# assets 파일 복사
Copy-Item "zendesk_app/assets/iframe.html" "$assetsDir/"
Copy-Item "zendesk_app/assets/main.js" "$assetsDir/"
Copy-Item "zendesk_app/assets/logo.svg" "$assetsDir/"

# 번역 파일 복사
$translationsDir = Join-Path $packageDir "translations"
New-Item -ItemType Directory -Path $translationsDir -Force | Out-Null
Copy-Item "zendesk_app/assets/translations/en.json" "$translationsDir/"

Write-Host "📦 ZIP 파일 생성 중..." -ForegroundColor Yellow

# ZIP 파일 생성
$zipPath = Join-Path (Get-Location) "zendesk-aws-assistant.zip"

# 기존 ZIP 파일 삭제
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

# PowerShell 7.0 이상에서는 Compress-Archive 사용
if ($PSVersionTable.PSVersion.Major -ge 7) {
    Compress-Archive -Path "$packageDir" -DestinationPath $zipPath -Force
} else {
    # PowerShell 5.1 이하에서는 .NET 사용
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory($packageDir, $zipPath, [System.IO.Compression.CompressionLevel]::Optimal, $false)
}

Write-Host "✅ 완료!" -ForegroundColor Green
Write-Host ""
Write-Host "📊 패키지 정보:" -ForegroundColor Cyan
Get-Item $zipPath | Format-List Length, FullName
Write-Host ""
Write-Host "📋 패키지 내용:" -ForegroundColor Cyan
$zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
$zip.Entries | ForEach-Object { Write-Host "  $($_.FullName)" }
$zip.Dispose()
Write-Host ""
Write-Host "🚀 배포 준비 완료!" -ForegroundColor Green
Write-Host "   Zendesk 마켓플레이스에 zendesk-aws-assistant.zip을 업로드하세요." -ForegroundColor White
Write-Host ""
Write-Host "⚙️  주의사항:" -ForegroundColor Yellow
Write-Host "   1. Python 서버가 EC2에서 실행 중이어야 합니다" -ForegroundColor White
Write-Host "   2. manifest.json의 serverUrl을 EC2 주소로 설정하세요" -ForegroundColor White
Write-Host "   3. 앱 설정에서 serverUrl 파라미터를 입력해야 합니다" -ForegroundColor White

# 정리
Remove-Item $tempDir -Recurse -Force
