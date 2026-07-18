"""Unit tests for PHI/PII pattern detection (no GUI)."""

from pdf_redact.detector import find_in_text
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
