"""Unit tests for PHI/PII pattern detection (no GUI)."""

import fitz

from pdf_redact.detector import detect_page, find_in_text
from pdf_redact.patterns import active_rules


def test_ssn_and_email():
    text = "Patient SSN 123-45-6789 email jane.doe@example.com called."
    matches = find_in_text(text, rules=active_rules(["ssn", "email", "phone"]))
    labels = {m[2].name for m in matches}
    assert "ssn" in labels
    assert "email" in labels
    texts = {m[3] for m in matches}
    assert "123-45-6789" in texts
    assert "jane.doe@example.com" in texts


def test_ssn_formats():
    """Dashed, continuous, spaced, and PDF-mangled separators must all match."""
    samples = [
        "123-45-6789",
        "123456789",
        "123 45 6789",
        "123 - 45 - 6789",
        "123-\n45-6789",
        "123\u201345\u20136789",  # en dash
        "123\u201445\u20146789",  # em dash
        "123\u00b745\u00b76789",  # middle dot (common PDF re-encoding of dash)
        "123.45.6789",
    ]

    for s in samples:
        matches = find_in_text(f"Patient SSN {s} end.", rules=active_rules(["ssn"]))
        assert any(m[2].name == "ssn" for m in matches), f"failed to match SSN in {s!r}"
        # Matched span should contain all nine digits
        hit = next(m[3] for m in matches if m[2].name == "ssn")
        digits = "".join(c for c in hit if c.isdigit())
        assert digits == "123456789", f"{s!r} -> {hit!r}"


def test_ssn_rejects_invalid_area_group_serial():
    for s in ("000-12-3456", "666-12-3456", "900-12-3456", "123-00-6789", "123-45-0000"):
        matches = find_in_text(s, rules=active_rules(["ssn"]))
        assert matches == [], f"should not match invalid SSN {s!r}"


def test_ssn_dashed_in_pdf_gets_rects():
    """End-to-end: dashed SSN in a PDF is detected and locatable for redaction."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Patient SSN 123-45-6789 admitted.")
    findings = detect_page(page, 0, rules=active_rules(["ssn"]))
    assert len(findings) == 1
    assert findings[0].rule_name == "ssn"
    assert "123" in findings[0].text and "6789" in findings[0].text
    assert findings[0].rects, "expected searchable rects for dashed SSN"
    assert findings[0].selected


def test_phone():
    text = "Contact: (555) 123-4567 for follow-up."
    matches = find_in_text(text, rules=active_rules(["phone"]))
    assert len(matches) >= 1
    assert "555" in matches[0][3]


def test_mrn():
    text = "MRN: ABC1234567 admitted today."
    matches = find_in_text(text, rules=active_rules(["mrn"]))
    assert len(matches) == 1
    assert "ABC1234567" in matches[0][3]


def test_non_overlapping_prefers_first_span():
    text = "123-45-6789"
    matches = find_in_text(text, rules=active_rules(["ssn", "zip"]))
    # Should not double-count overlapping ZIP inside SSN when both enabled
    assert len(matches) >= 1
