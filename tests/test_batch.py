"""Batch pipeline smoke tests (no GUI)."""

from pathlib import Path

import fitz

from pdf_redact.batch import run_batch
from pdf_redact.detector import detect_document
from pdf_redact.limits import GUI_LARGE_PAGE_THRESHOLD


def _make_pdf(path: Path, pages: int = 3) -> Path:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1} SSN 123-45-6789 contact.")
        page.insert_text((72, 100), "email patient@example.com")
    doc.save(path)
    doc.close()
    return path


def test_batch_redacts_and_report(tmp_path: Path):
    src = _make_pdf(tmp_path / "in.pdf", pages=4)
    out = tmp_path / "out.pdf"
    report = tmp_path / "report.json"

    result = run_batch(
        src,
        out,
        pages_spec="1-2",
        rules=["ssn", "email"],
        ocr_mode="never",
        report_path=report,
        quiet=True,
    )

    assert out.is_file()
    assert report.is_file()
    assert result.pages_processed == 2
    assert result.finding_count >= 2
    assert result.selected_count >= 1
    # Report must not embed full SSN as plain matched text field
    text = report.read_text(encoding="utf-8")
    assert "123-45-6789" not in text
    assert "text_preview" in text

    # Pages 1-2 redacted; open and confirm SSN search misses on page 0
    doc = fitz.open(out)
    p0 = doc.load_page(0).get_text("text") or ""
    # Redaction removes text under black boxes; digits should be gone or partial
    assert "123-45-6789" not in p0
    doc.close()


def test_detect_page_indices_only():
    doc = fitz.open()
    for i in range(5):
        page = doc.new_page()
        if i == 2:
            page.insert_text((72, 72), "SSN 123-45-6789")
        else:
            page.insert_text((72, 72), "nothing sensitive here")
    findings = detect_document(doc, enabled_rules=["ssn"], page_indices=[2])
    assert len(findings) == 1
    assert findings[0].page_index == 2
    findings_other = detect_document(doc, enabled_rules=["ssn"], page_indices=[0, 1])
    assert findings_other == []
    doc.close()


def test_large_threshold_constant():
    assert GUI_LARGE_PAGE_THRESHOLD >= 100
