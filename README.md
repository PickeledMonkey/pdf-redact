# PDF Redact

Desktop **GUI** for interactive PHI/PII redaction of PDF files, plus a **batch CLI** for large documents (up to ~15 000 pages), with **OCR** for scanned/image PDFs.

Drag and drop a PDF, auto-detect sensitive spans (SSN, phone, email, DOB, MRN, payment cards, addresses, and more), review findings, draw manual boxes, and export a permanently redacted PDF. For bulk jobs use `pdf-redact-batch`.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Drag-and-drop** PDF loading
- **Automatic PHI/PII detection** via practical regex rules (toggle per category)
- **OCR** for image-only / scanned pages (Tesseract via PyMuPDF)
- **Preview** with red (selected) / blue (unselected) highlights
- **Manual redaction boxes** — drag on the page
- **Permanent redaction** using PyMuPDF (content removed, not just covered)
- **Metadata scrub** on export (title/author/etc. cleared)
- **Large-document GUI guardrails** (500+ pages): no auto full-scan, Scan Page / Scan All, jump-to-page, page-scoped findings list
- **Batch CLI** (`pdf-redact-batch`) for headless full-document redaction with page ranges and JSON audit reports

### Detected categories

| Rule | Description | Default |
|------|-------------|---------|
| SSN | US Social Security Numbers | On |
| Credit Card | Common card number patterns | On |
| Email | Email addresses | On |
| Phone | US/Canada phone numbers | On |
| DOB/Date | Common date formats | On |
| MRN/ID | Medical record / patient ID labels | On |
| Address | Street address lines | On |
| IP Address | IPv4 | On |
| ZIP | US ZIP codes | Off (noisy) |
| DEA | Labeled DEA numbers (`DEA: AB1234563`) | On |
| NPI | Provider NPI | Off (noisy) |

> **Note:** Pattern detection is a high-recall assistant, not a compliance guarantee. Always review findings before export. This tool does not replace a formal HIPAA de-identification process.

## Portable Windows package (no install)

**Preferred for workstations:** unzip and run — no Python, no installer, no admin rights.

1. Download **`pdf-redact-portable.zip`** from [GitHub Releases](https://github.com/PickeledMonkey/pdf-redact/releases) or the latest **Actions** artifact (`Build Windows portable`).
2. Unzip anywhere (USB, Desktop, `C:\Tools\pdf-redact\`).
3. Double-click **`Start-PDF-Redact.bat`** for the GUI, or use **`PDF-Redact-Batch.bat`** for large/headless jobs.
4. Large PDFs: `PDF-Redact-Batch.bat big.pdf -o out.pdf --pages all --report report.json` then open `out.pdf` in the GUI to spot-check.

OCR for scanned PDFs is included when the package contains a `tesseract\` folder (CI builds try to bundle it).

### Build the portable zip on Windows

```powershell
cd pdf-redact
powershell -ExecutionPolicy Bypass -File .\Build-Portable.ps1
# → dist\pdf-redact-portable\  and  ..\pdf-redact-portable.zip
```

## Development install (Linux / macOS / Windows)

- **Python 3.11+**
- **Tesseract OCR** (optional, required for scanned PDFs)

```bash
# Debian / Ubuntu
sudo apt install tesseract-ocr

# Fedora
sudo dnf install tesseract

# macOS
brew install tesseract
```

```bash
cd ~/projects/pdf-redact
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -e .
```

### Run from source

```bash
source .venv/bin/activate
pdf-redact
# or:
python -m pdf_redact.app
# Windows portable source fallback:
#   .\Start-PDF-Redact.bat
```

### Batch CLI (large PDFs)

```bash
source .venv/bin/activate
pdf-redact-batch --list-rules
pdf-redact-batch big.pdf -o big_redacted.pdf --pages all --report report.json
pdf-redact-batch big.pdf -o out.pdf --pages 1-500 --ocr auto --rules ssn,email,phone
```

- Processes page ranges (1-based: `1-100,250` or `all`)
- Optional OCR: `never` (default) | `auto` | `always`
- JSON report includes counts and **masked** samples (not full PHI)
- Advisory note at 15 000+ pages; still allowed

### Workflow (GUI)

1. **Open** or drag-and-drop a PDF.
2. For normal sizes, the app auto-scans the text layer. At **500+ pages**, auto full-scan is skipped — use **Scan Page** / **Scan All**, or the batch CLI.
3. For scans: **Run OCR** (needs Tesseract). On large docs, prefer current-page OCR or `pdf-redact-batch --ocr auto`.
4. Toggle categories or individual findings; draw **Manual** boxes if needed. Use **Go** to jump pages.
5. **Export Redacted** — saves a new PDF with content permanently removed.

## Project layout

```
pdf-redact/
├── pdf_redact/
│   ├── app.py              # CustomTkinter GUI (+ large-doc guardrails)
│   ├── batch.py            # CLI batch redaction for large PDFs
│   ├── detector.py         # PHI/PII span detection + PDF coords
│   ├── limits.py           # GUI / batch page thresholds
│   ├── ocr.py              # Tesseract / PyMuPDF OCR
│   ├── page_ranges.py      # --pages parser
│   ├── paths.py            # Portable / frozen path helpers
│   ├── patterns.py         # Regex rules
│   └── redactor.py         # Apply redactions + page render
├── Build-Portable.ps1      # Windows no-install package builder
├── Start-PDF-Redact.bat    # Double-click launcher
├── PDF-Redact.spec         # PyInstaller spec
├── SETUP.txt               # End-user portable guide
├── tests/
├── pyproject.toml
└── requirements.txt
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Stack

- [PyMuPDF](https://pymupdf.readthedocs.io/) — PDF open, search, OCR hook, redaction
- [CustomTkinter](https://customtkinter.tomschimansky.com/) + [tkinterdnd2](https://github.com/pmgagne/tkinterdnd2) — modern GUI + drag-and-drop
- [Tesseract](https://github.com/tesseract-ocr/tesseract) — OCR engine
- Pillow — page preview images

## License

MIT

## Author

GitHub: [PickeledMonkey](https://github.com/PickeledMonkey)
