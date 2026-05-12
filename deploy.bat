@echo off
chcp 65001 >nul
setlocal

set REPO=\\192.168.10.3\품질팀\AI프로그램\RTMS
echo.
echo ====================================
echo   RTMS 자동 배포 (GitHub + Render)
echo ====================================

cd /d "%REPO%"

git add -A
if errorlevel 1 (echo [오류] git add 실패 & pause & exit /b 1)

:: 변경사항 있을 때만 커밋
git diff --cached --quiet
if errorlevel 1 (
    for /f "tokens=1-4 delims=/ " %%a in ("%date%") do set D=%%a%%b%%c
    for /f "tokens=1-2 delims=: " %%a in ("%time%") do set T=%%a%%b
    git commit -m "deploy: %D%-%T%"
    if errorlevel 1 (echo [오류] git commit 실패 & pause & exit /b 1)
    echo [완료] 커밋 생성됨
) else (
    echo [알림] 변경된 파일 없음 - 커밋 건너뜀
)

git push
if errorlevel 1 (echo [오류] git push 실패 & pause & exit /b 1)

echo.
echo ✅ 배포 완료! Render 자동 재배포 시작 (약 2~3분 소요)
echo    확인: https://rtms-y356.onrender.com
echo.
pause
