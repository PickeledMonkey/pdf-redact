# PDF Redact

Desktop GUI for **fast PHI/PII redaction** of PDF files, with **OCR** for scanned/image PDFs.

Drag and drop a PDF, auto-detect sensitive spans (SSN, phone, email, DOB, MRN, payment cards, addresses, and more), review findings, draw manual boxes, and export a permanently redacted PDF.

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
| NPI / DEA | Provider identifiers | Off (noisy) |

> **Note:** Pattern detection is a high-recall assistant, not a compliance guarantee. Always review findings before export. This tool does not replace a formal HIPAA de-identification process.

## Requirements

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

## Install

```bash
cd ~/projects/pdf-redact
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Or with requirements only:

```bash
pip install -r requirements.txt
```

## Run

```bash
source .venv/bin/activate
pdf-redact
# or:
python -m pdf_redact.app
```

### Workflow

1. **Open** or drag-and-drop a PDF.
2. App auto-scans the text layer for PHI/PII.
3. For scans: click **Run OCR** (needs Tesseract), then review findings.
4. Toggle categories or individual findings; draw **Manual** boxes if needed.
5. **Export Redacted** — saves a new PDF with content permanently removed.

## Project layout

```
pdf-redact/
├── pdf_redact/
│   ├── app.py          # CustomTkinter GUI
│   ├── detector.py     # PHI/PII span detection + PDF coords
│   ├── ocr.py          # Tesseract / PyMuPDF OCR
│   ├── patterns.py     # Regex rules
│   └── redactor.py     # Apply redactions + page render
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
