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


# Ordered roughly by priority / uniqueness so overlapping matches can prefer
# more specific labels during non-overlapping resolution.
RULES: list[PatternRule] = [
    PatternRule(
        name="ssn",
        label="SSN",
        pattern=_compile(
            r"\b(?!000|666|9\d{2})\d{3}[-\s]?(?!00)\d{2}[-\s]?(?!0000)\d{4}\b"
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
        pattern=_compile(r"\b(?:DEA)\s*[:#]?\s*[A-Z]{2}\d{7}\b|\b[A-Z]{2}\d{7}\b"),
        description="DEA registration number",
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

# Categories that are off by default due to higher false-positive rates
DEFAULT_DISABLED: frozenset[str] = frozenset({"zip", "npi", "dea"})


def active_rules(enabled: Iterable[str] | None = None) -> list[PatternRule]:
    """Return pattern rules, optionally filtered by enabled names."""
    if enabled is None:
        return [r for r in RULES if r.name not in DEFAULT_DISABLED]
    enabled_set = set(enabled)
    return [r for r in RULES if r.name in enabled_set]


def all_rule_names() -> list[str]:
    return [r.name for r in RULES]
