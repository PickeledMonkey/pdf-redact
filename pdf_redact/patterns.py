"""PHI/PII detection patterns for healthcare and general sensitive data.

Patterns are intentionally practical (high recall for common formats) rather
than perfect. Users can always add or remove redactions in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import regex as re


@dataclass(frozen=True, slots=True)
class PatternRule:
    """A named regex rule used to find sensitive spans."""

    name: str
    label: str
    pattern: re.Pattern[str]
    description: str


def _compile(pattern: str, flags: int = re.IGNORECASE | re.MULTILINE) -> re.Pattern[str]:
    return re.compile(pattern, flags)


# Separators between SSN groups. PDF text layers and OCR often mangle ASCII
# hyphens into en/em dashes, middle dots, fullwidth hyphens, soft hyphens,
# zero-width glue, or insert spaces around the dash
# (e.g. "123 - 45 - 6789", "123·45·6789", "123\u00ad45\u00ad6789").
_SSN_SEP_CLASS = (
    r"\s.\u00b7\u2022"  # whitespace, period, middle dot, bullet
    r"\u2212\u2010-\u2015\-"  # minus, hyphen/dash range, ASCII hyphen
    r"\u00ad"  # soft hyphen
    r"\u200b-\u200d\u2060\ufeff"  # zero-width space/joiner/BOM/word joiner
    r"\uff0d\ufe63\u2043\ufe58"  # fullwidth/small hyphen, hyphen bullet
)
# Require non-empty separators for dashed/spaced forms so ZIP+4 (10001-1234)
# and similar 5-4 digit runs are not misread as 3+2+4 with an empty middle sep.
_SSN_SEP_REQ = rf"[{_SSN_SEP_CLASS}]+"

# Ordered roughly by priority / uniqueness so overlapping matches can prefer
# more specific labels during non-overlapping resolution.
RULES: list[PatternRule] = [
    PatternRule(
        name="ssn",
        label="SSN",
        # Continuous 9 digits OR area + sep + group + sep + serial.
        # Empty separators are only allowed for the pure continuous form.
        pattern=_compile(
            rf"\b(?!000|666|9\d{{2}})\d{{3}}"
            rf"(?:"
            rf"(?!00)\d{{2}}(?!0000)\d{{4}}"
            rf"|"
            rf"{_SSN_SEP_REQ}(?!00)\d{{2}}{_SSN_SEP_REQ}(?!0000)\d{{4}}"
            rf")\b"
        ),
        description="US Social Security Number",
    ),
    PatternRule(
        name="credit_card",
        label="Credit Card",
        pattern=_compile(
            r"\b(?:4\d{3}|5[1-5]\d{2}|3[47]\d{2}|6(?:011|5\d{2}))[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"
            r"|\b\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}\b"
        ),
        description="Payment card number",
    ),
    PatternRule(
        name="email",
        label="Email",
        pattern=_compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
        description="Email address",
    ),
    PatternRule(
        name="phone",
        label="Phone",
        pattern=_compile(
            r"(?:(?<=\D)|^)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?=\D|$)"
        ),
        description="US/Canada phone number",
    ),
    PatternRule(
        name="dob",
        label="DOB/Date",
        pattern=_compile(
            r"\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b"
            r"|\b(?:19|20)\d{2}[/-](?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])\b"
            r"|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
            r"Dec(?:ember)?)\s+\d{1,2},?\s+(?:19|20)\d{2}\b"
        ),
        description="Date of birth / date formats",
    ),
    PatternRule(
        name="mrn",
        label="MRN/ID",
        pattern=_compile(
            r"\b(?:MRN|Medical\s*Record(?:\s*Number)?|Patient\s*ID|Account\s*#?|"
            r"Member\s*ID|Chart\s*#?)\s*[:#]?\s*[A-Z0-9-]{4,20}\b"
        ),
        description="Medical record / patient identifiers",
    ),
    PatternRule(
        name="npi",
        label="NPI",
        pattern=_compile(r"\b(?:NPI)\s*[:#]?\s*\d{10}\b|\b\d{10}\b(?=\s*(?:NPI)?)"),
        description="National Provider Identifier (contextual)",
    ),
    PatternRule(
        name="dea",
        label="DEA",
        # Contextual only (require DEA label) — free-floating XX####### is too noisy.
        pattern=_compile(r"\bDEA\s*[:#]?\s*[A-Z]{2}\d{7}\b"),
        description="DEA registration number (labeled)",
    ),
    PatternRule(
        name="ip_address",
        label="IP Address",
        pattern=_compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
        ),
        description="IPv4 address",
    ),
    PatternRule(
        name="address_line",
        label="Address",
        pattern=_compile(
            r"\b\d{1,6}\s+(?:[A-Z0-9][A-Z0-9.'-]{0,30}\s+){0,5}"
            r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|"
            r"Court|Ct|Circle|Cir|Way|Place|Pl|Parkway|Pkwy|Highway|Hwy)\.?\b"
        ),
        description="Street address line",
    ),
    PatternRule(
        name="zip",
        label="ZIP",
        pattern=_compile(r"\b\d{5}(?:-\d{4})?\b"),
        description="US ZIP code (higher false-positive rate; optional)",
    ),
]

# Categories that are off by default due to higher false-positive rates.
# DEA is on by default now that the pattern requires a "DEA" label.
DEFAULT_DISABLED: frozenset[str] = frozenset({"zip", "npi"})


def active_rules(enabled: Iterable[str] | None = None) -> list[PatternRule]:
    """Return pattern rules, optionally filtered by enabled names."""
    if enabled is None:
        return [r for r in RULES if r.name not in DEFAULT_DISABLED]
    enabled_set = set(enabled)
    return [r for r in RULES if r.name in enabled_set]


def all_rule_names() -> list[str]:
    return [r.name for r in RULES]
