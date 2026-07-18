@echo off
setlocal
cd /d "%~dp0"

REM Prefer frozen portable build (no Python install required)
if exist "%~dp0PDF-Redact\PDF-Redact.exe" (
    start "" "%~dp0PDF-Redact\PDF-Redact.exe"
    exit /b 0
)
if exist "%~dp0PDF-Redact.exe" (
    start "" "%~dp0PDF-Redact.exe"
    exit /b 0
)

REM Fallback: source layout with portable .venv (needs one-time Setup-Portable.ps1)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-PDF-Redact.ps1"
endlocal
