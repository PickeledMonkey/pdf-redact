@echo off
setlocal
cd /d "%~dp0"

REM Console batch CLI for large / headless redaction (passes all args through)
if exist "%~dp0PDF-Redact\PDF-Redact-Batch.exe" (
    "%~dp0PDF-Redact\PDF-Redact-Batch.exe" %*
    exit /b %ERRORLEVEL%
)
if exist "%~dp0PDF-Redact-Batch.exe" (
    "%~dp0PDF-Redact-Batch.exe" %*
    exit /b %ERRORLEVEL%
)

echo PDF-Redact-Batch.exe not found. Rebuild with Build-Portable.ps1 or use:
echo   python -m pdf_redact.batch --help
exit /b 1
