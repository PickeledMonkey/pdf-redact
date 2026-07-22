# pdf-redact — Agent Instructions

## Purpose

Desktop GUI for interactive PHI/PII redaction of PDFs with optional OCR, plus a
**batch CLI** for large documents (up to ~15 000 pages).

## Stack

- Python 3.11+, CustomTkinter, tkinterdnd2, PyMuPDF, Pillow, regex
- System dependency: `tesseract-ocr` for image PDFs

## Modes

| Mode | Entry | Use when |
|------|--------|----------|
| GUI | `pdf-redact` / `python -m pdf_redact.app` | Review, manual boxes, normal page counts |
| Batch | `pdf-redact-batch` / `python -m pdf_redact.batch` | Full-doc jobs, page ranges, headless |

GUI large-doc guardrails kick in at `GUI_LARGE_PAGE_THRESHOLD` (500) in
`pdf_redact/limits.py`: no auto full-scan, Scan Page / Scan All, jump-to-page,
findings list scoped to page + capped.

## Conventions

- Keep detection rules in `pdf_redact/patterns.py`
- Permanent redaction only via PyMuPDF `add_redact_annot` + `apply_redactions` (never paint-over alone)
- GUI must remain usable without Tesseract; OCR is optional with a clear status badge
- Portable Windows = PyInstaller onedir + optional bundled `tesseract\`; resolve via `pdf_redact/paths.py`
- Do not log full document text or findings to remote services
- Batch `--report` uses masked previews only (no full PHI dump)

## Commands

```bash
cd ~/projects/pdf-redact
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python -m pdf_redact.app
pdf-redact-batch input.pdf -o out.pdf --pages 1-100 --report report.json
pdf-redact-batch --list-rules
```

### Windows portable (no install)

```powershell
powershell -ExecutionPolicy Bypass -File .\Build-Portable.ps1
# CI: .github/workflows/build-windows-portable.yml → artifact pdf-redact-portable.zip
```

## Safety

Treat sample PDFs as potentially sensitive. Prefer synthetic fixtures in tests.
