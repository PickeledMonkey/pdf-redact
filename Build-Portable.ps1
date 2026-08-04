<#
.SYNOPSIS
    Build a no-install Windows portable package (PyInstaller onedir + optional Tesseract).

.DESCRIPTION
    Produces:
      dist\pdf-redact-portable\
        Start-PDF-Redact.bat
        PDF-Redact-Batch.bat
        PDF-Redact\
          PDF-Redact.exe         (GUI)
          PDF-Redact-Batch.exe   (large-doc CLI)
        tesseract\          (if -BundleTesseract and choco/winget available)
        SETUP.txt
        portable.json

    Zip written to parent folder or -OutputZip.

.PARAMETER BundleTesseract
    Try to install/copy Tesseract into the portable folder for offline OCR.

.PARAMETER SkipZip
    Build the folder only; do not create the zip.
#>

[CmdletBinding()]
param(
    [switch]$BundleTesseract = $true,
    [switch]$SkipZip,
    [string]$OutputZip = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$AppRoot = $PSScriptRoot
Set-Location -LiteralPath $AppRoot

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python must be on PATH to build the portable package."
}

Write-Output "=== PDF Redact — portable Windows build ==="
Write-Output "Root: $AppRoot"

Write-Output "Installing build dependencies..."
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip install "pyinstaller>=6.0.0"

Write-Output "Running PyInstaller..."
if (Test-Path -LiteralPath (Join-Path $AppRoot 'dist\PDF-Redact')) {
    Remove-Item -LiteralPath (Join-Path $AppRoot 'dist\PDF-Redact') -Recurse -Force
}
if (Test-Path -LiteralPath (Join-Path $AppRoot 'build')) {
    Remove-Item -LiteralPath (Join-Path $AppRoot 'build') -Recurse -Force
}

python -m PyInstaller --noconfirm --clean PDF-Redact.spec

$built = Join-Path $AppRoot 'dist\PDF-Redact'
if (-not (Test-Path -LiteralPath (Join-Path $built 'PDF-Redact.exe'))) {
    throw "PyInstaller did not produce PDF-Redact.exe"
}
if (-not (Test-Path -LiteralPath (Join-Path $built 'PDF-Redact-Batch.exe'))) {
    throw "PyInstaller did not produce PDF-Redact-Batch.exe (batch CLI for large PDFs)"
}

$portableRoot = Join-Path $AppRoot 'dist\pdf-redact-portable'
if (Test-Path -LiteralPath $portableRoot) {
    Remove-Item -LiteralPath $portableRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $portableRoot | Out-Null

Write-Output "Assembling portable folder..."
Copy-Item -Path $built -Destination (Join-Path $portableRoot 'PDF-Redact') -Recurse
Copy-Item -Path (Join-Path $AppRoot 'Start-PDF-Redact.bat') -Destination $portableRoot
Copy-Item -Path (Join-Path $AppRoot 'PDF-Redact-Batch.bat') -Destination $portableRoot
Copy-Item -Path (Join-Path $AppRoot 'portable.json') -Destination $portableRoot
Copy-Item -Path (Join-Path $AppRoot 'SETUP.txt') -Destination $portableRoot
Copy-Item -Path (Join-Path $AppRoot 'LICENSE') -Destination $portableRoot -ErrorAction SilentlyContinue
Copy-Item -Path (Join-Path $AppRoot 'README.md') -Destination $portableRoot -ErrorAction SilentlyContinue

# --- Optional Tesseract bundle ---
if ($BundleTesseract) {
    Write-Output "Bundling Tesseract for portable OCR..."
    $tessDest = Join-Path $portableRoot 'tesseract'
    New-Item -ItemType Directory -Path $tessDest -Force | Out-Null

    $bundled = $false

    # Prefer an already-installed system Tesseract (choco / official installer)
    $candidates = @(
        'C:\Program Files\Tesseract-OCR\tesseract.exe',
        'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'
    )
    $chocoTess = 'C:\ProgramData\chocolatey\lib\tesseract\tools\tesseract.exe'
    $candidates += $chocoTess

    $existing = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

    if (-not $existing) {
        $choco = Get-Command choco -ErrorAction SilentlyContinue
        if ($choco) {
            Write-Output "Installing Tesseract via Chocolatey (build machine only)..."
            choco install tesseract -y --no-progress
            $existing = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
            if (-not $existing) {
                $existing = Get-ChildItem -Path 'C:\Program Files*\Tesseract-OCR\tesseract.exe' -ErrorAction SilentlyContinue |
                    Select-Object -First 1 -ExpandProperty FullName
            }
        }
    }

    if ($existing) {
        $srcDir = Split-Path -Parent $existing
        Write-Output "Copying Tesseract from $srcDir"
        Copy-Item -Path (Join-Path $srcDir '*') -Destination $tessDest -Recurse -Force
        $bundled = $true
    }
    else {
        Write-Warning "Tesseract not found — OCR will require a manual tesseract\ folder. Text PDFs still work."
    }

    if ($bundled) {
        Write-Output "Tesseract bundled at tesseract\"
    }
}

# Small launcher note inside package
@"
PDF Redact — Portable (no install) v0.2.1
=========================================
1. Unzip this folder anywhere (USB, Desktop, network share).
2. GUI:   double-click Start-PDF-Redact.bat
3. Batch: PDF-Redact-Batch.bat input.pdf -o out.pdf --pages all --report report.json
4. No Python or installer required.

Large PDFs (500+ pages): prefer the batch CLI, then spot-check in the GUI.

OCR: If a tesseract\ folder is present, scanned PDFs work offline.
     Otherwise only text-layer PDFs auto-detect PHI/PII.
"@ | Set-Content -LiteralPath (Join-Path $portableRoot 'README-PORTABLE.txt') -Encoding UTF8

if (-not $SkipZip) {
    if (-not $OutputZip) {
        $OutputZip = Join-Path (Split-Path $AppRoot -Parent) 'pdf-redact-portable.zip'
    }
    if (Test-Path -LiteralPath $OutputZip) {
        Remove-Item -LiteralPath $OutputZip -Force
    }
    Write-Output "Creating zip: $OutputZip"
    Compress-Archive -Path (Join-Path $portableRoot '*') -DestinationPath $OutputZip -CompressionLevel Optimal
    Write-Output "Zip size: $([math]::Round((Get-Item $OutputZip).Length / 1MB, 1)) MB"
}

Write-Output ""
Write-Output "Done."
Write-Output "  Folder: $portableRoot"
if (-not $SkipZip) {
    Write-Output "  Zip:    $OutputZip"
}
Write-Output "Copy the folder or zip to any Windows 10/11 PC and run Start-PDF-Redact.bat"
