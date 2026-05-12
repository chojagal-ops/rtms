@echo off
net session >nul 2>&1
if errorlevel 1 (
    echo UAC - click Yes in the dialog...
    powershell -Command "Start-Process -FilePath cmd.exe -ArgumentList '/c \"%~f0\"' -Verb RunAs -Wait"
    exit /b
)
chcp 65001 >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_startup.ps1"
pause
