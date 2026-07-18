<#
.SYNOPSIS
    Optional first-time setup for source-layout portable folder (needs system Python).

    The preferred distribution is the frozen Build-Portable.ps1 output which needs
    NO Python install — just unzip and run Start-PDF-Redact.bat.
#>

[CmdletBinding()]
param(
    [string]$PythonExe = "python"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$AppRoot = $PSScriptRoot
$venvPath = Join-Path $AppRoot '.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'
$requirements = Join-Path $AppRoot 'requirements.txt'

function Test-PythonVersion {
    param([string]$Exe)
    $versionText = & $Exe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    $parts = $versionText.Trim().Split('.')
    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
        throw "Python 3.11+ is required. Found $versionText using $Exe"
    }
    return $versionText.Trim()
}

Write-Output "PDF Redact portable setup (source layout)"
Write-Output "App folder: $AppRoot"

# If frozen build already present, nothing to do
if (Test-Path -LiteralPath (Join-Path $AppRoot 'PDF-Redact\PDF-Redact.exe')) {
    Write-Output "Frozen build found — no setup needed. Double-click Start-PDF-Redact.bat"
    return
}

$pythonVersion = Test-PythonVersion -Exe $PythonExe
Write-Output "Using Python $pythonVersion from $PythonExe"

if (-not (Test-Path -LiteralPath $requirements)) {
    throw "requirements.txt not found in $AppRoot"
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Output "Creating virtual environment..."
    & $PythonExe -m venv $venvPath
}

Write-Output "Installing dependencies..."
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r $requirements
& $venvPython -m pip install -e .

Write-Output ""
Write-Output "Setup complete. Launch with Start-PDF-Redact.bat or Run-PDF-Redact.ps1"
Write-Output "Optional OCR: place Tesseract in tesseract\ next to this folder, or install system-wide."
