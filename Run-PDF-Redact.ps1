<#
.SYNOPSIS
    Launch PDF Redact from a portable folder (source + venv fallback).
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$AppRoot = $PSScriptRoot

# Frozen one-folder build
$frozen = Join-Path $AppRoot 'PDF-Redact\PDF-Redact.exe'
$frozenFlat = Join-Path $AppRoot 'PDF-Redact.exe'
if (Test-Path -LiteralPath $frozen) {
    Start-Process -FilePath $frozen
    return
}
if (Test-Path -LiteralPath $frozenFlat) {
    Start-Process -FilePath $frozenFlat
    return
}

$venvPython = Join-Path $AppRoot '.venv\Scripts\python.exe'
$mainScript = Join-Path $AppRoot 'run_app.py'

if (-not (Test-Path -LiteralPath $mainScript)) {
    throw "run_app.py not found in $AppRoot"
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Output "Portable environment not set up yet. Running Setup-Portable.ps1..."
    & (Join-Path $AppRoot 'Setup-Portable.ps1')
}

$env:PDF_REDACT_PORTABLE = '1'
Set-Location -LiteralPath $AppRoot
& $venvPython $mainScript
