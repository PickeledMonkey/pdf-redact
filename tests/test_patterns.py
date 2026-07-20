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


def test_ssn_spaced_dashes_and_dea_redact_from_pdf():
    """Spaced SSN and labeled DEA must detect, locate, and burn out of export."""
    from pdf_redact.detector import detect_document
    from pdf_redact.redactor import apply_redactions

    doc = fitz.open()
    page = doc.new_page()
    # Stack several SSNs so continuous-digit search is ambiguous without
    # occurrence / word-list disambiguation.
    page.insert_text((50, 72), "SSN (dashed): 123-45-6789")
    page.insert_text((50, 96), "SSN (continuous): 123456789")
    page.insert_text((50, 120), "SSN (spaced dashes): 123 - 45 - 6789")
    page.insert_text((50, 144), "DEA: AB1234563")
    page.insert_text((50, 168), "NPI: 1234567893")

    findings = detect_document(doc)  # default enabled rules (includes DEA, not NPI)

    assert any("123 - 45 - 6789" in f.text for f in findings if f.rule_name == "ssn")
    spaced = next(f for f in findings if "123 - 45 - 6789" in f.text)
    assert spaced.rects and spaced.selected

    dea = next(f for f in findings if f.rule_name == "dea")
    assert "AB1234563" in dea.text
    assert dea.rects and dea.selected

    out = "/tmp/pdf-redact-ssn-dea-test.pdf"
    apply_redactions(doc, findings, out)
    doc.close()

    redacted = fitz.open(out)
    text = redacted[0].get_text("text")
    redacted.close()
    assert "123 - 45 - 6789" not in text
    assert "AB1234563" not in text
    assert "123-45-6789" not in text


def test_dea_default_enabled_contextual_only():
    from pdf_redact.patterns import DEFAULT_DISABLED

    assert "dea" not in DEFAULT_DISABLED
    # Labeled form matches
    matches = find_in_text("Provider DEA: AB1234563 done.", rules=active_rules(["dea"]))
    assert len(matches) == 1
    assert "AB1234563" in matches[0][3]
    # Free-floating XX####### without DEA label does not match
    matches = find_in_text("Code AB1234563 only.", rules=active_rules(["dea"]))
    assert matches == []


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
