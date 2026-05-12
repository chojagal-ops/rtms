# RTMS Auto-Start Setup (PowerShell)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$rtmsPath  = "\\192.168.10.3\품질팀\AI프로그램\RTMS"
$localDir  = "C:\ProgramData\RTMS"
$venvPath  = "$localDir\venv"
$configFile = "$localDir\rtms_path.txt"
$starterPs  = "$localDir\start_server.ps1"

Write-Host ""
Write-Host " RTMS Auto-Start Setup" -ForegroundColor Cyan
Write-Host " ==============================" -ForegroundColor Cyan
Write-Host ""

# 1. 로컬 폴더 생성
New-Item -ItemType Directory -Force -Path $localDir | Out-Null

# 2. 경로 설정파일 저장 (한글 경로를 UTF-8 파일로 보관 → start_server.ps1이 읽어서 사용)
[System.IO.File]::WriteAllText($configFile, $rtmsPath,
    [System.Text.Encoding]::UTF8)
Write-Host "[1/4] Config saved." -ForegroundColor Green

# 3. 가상환경 생성 (최초 1회)
if (-not (Test-Path "$venvPath\Scripts\python.exe")) {
    Write-Host "[2/4] Creating venv (may take 1-2 min)..." -ForegroundColor Yellow
    python -m venv $venvPath
    Write-Host "      Installing packages..." -ForegroundColor Yellow
    & "$venvPath\Scripts\pip.exe" install -r "$rtmsPath\requirements.txt" --quiet
    Write-Host "[2/4] Venv ready." -ForegroundColor Green
} else {
    Write-Host "[2/4] Venv already exists — skipped." -ForegroundColor Green
}

# 4. 서버 시작 스크립트 생성 (한글 없이 ASCII로 저장)
$starterContent = @'
# RTMS Server Auto-Start Script
$localDir   = "C:\ProgramData\RTMS"
$configFile = "$localDir\rtms_path.txt"
$pythonExe  = "$localDir\venv\Scripts\python.exe"

# 네트워크 준비 대기 (최대 60초)
for ($i = 0; $i -lt 12; $i++) {
    $rtmsPath = [System.IO.File]::ReadAllText($configFile,
        [System.Text.Encoding]::UTF8).Trim()
    if (Test-Path $rtmsPath) { break }
    Start-Sleep -Seconds 5
}

$rtmsPath = [System.IO.File]::ReadAllText($configFile,
    [System.Text.Encoding]::UTF8).Trim()

$appPath = Join-Path $rtmsPath "app.py"
Set-Location $rtmsPath
& $pythonExe $appPath
'@

[System.IO.File]::WriteAllText($starterPs, $starterContent,
    [System.Text.Encoding]::ASCII)
Write-Host "[3/4] Start script created." -ForegroundColor Green

# 5. 예약 작업 등록 (로그인 시 자동 실행)
Unregister-ScheduledTask -TaskName "RTMS_Server" -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$starterPs`""

$trigger = New-ScheduledTaskTrigger -AtLogOn

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 2)

Register-ScheduledTask `
    -TaskName "RTMS_Server" `
    -Action   $action `
    -Trigger  $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "[4/4] Scheduled task registered." -ForegroundColor Green

Write-Host ""
Write-Host " Setup complete!" -ForegroundColor Green
Write-Host " RTMS will start automatically on every login." -ForegroundColor White
Write-Host " Browser URL: http://localhost:5001" -ForegroundColor Yellow
Write-Host ""

# 6. 지금 바로 서버 시작 여부 확인
$ans = Read-Host "Start the server now? (Y / other key)"
if ($ans -match '^[Yy]') {
    Write-Host "Starting server..." -ForegroundColor Cyan
    Start-Process "powershell.exe" `
        -ArgumentList "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$starterPs`""
    Start-Sleep -Seconds 5
    Write-Host "Done! Open http://localhost:5001 in your browser." -ForegroundColor Green
}
