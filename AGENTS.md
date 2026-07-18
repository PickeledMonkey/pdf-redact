# pdf-redact — Agent Instructions

## Purpose

Desktop GUI for fast PHI/PII redaction of PDFs with optional OCR for scanned documents.

## Stack

- Python 3.11+, CustomTkinter, tkinterdnd2, PyMuPDF, Pillow, regex
- System dependency: `tesseract-ocr` for image PDFs

## Conventions

- Keep detection rules in `pdf_redact/patterns.py`
- Permanent redaction only via PyMuPDF `add_redact_annot` + `apply_redactions` (never paint-over alone)
- GUI must remain usable without Tesseract; OCR is optional with a clear status badge
- Do not log full document text or findings to remote services

## Commands

```bash
cd ~/projects/pdf-redact
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python -m pdf_redact.app
```

## Safety

Treat sample PDFs as potentially sensitive. Prefer synthetic fixtures in tests.
