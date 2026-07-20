"""Detect PHI/PII spans in page text and map them to PDF coordinates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

import fitz  # PyMuPDF
import regex as re

from pdf_redact.patterns import PatternRule, active_rules


@dataclass(slots=True)
class Finding:
    """A single sensitive span on a page."""

    page_index: int
    label: str
    rule_name: str
    text: str
    # Rectangles in PDF page coordinates (origin top-left for display after convert)
    rects: list[fitz.Rect] = field(default_factory=list)
    selected: bool = True
    manual: bool = False

    def union_rect(self) -> fitz.Rect | None:
        if not self.rects:
            return None
        r = fitz.Rect(self.rects[0])
        for extra in self.rects[1:]:
            r |= extra
        return r


def _non_overlapping(matches: list[tuple[int, int, PatternRule, str]]) -> list[tuple[int, int, PatternRule, str]]:
    """Prefer longer / earlier matches when spans overlap."""
    matches = sorted(matches, key=lambda m: (m[0], -(m[1] - m[0])))
    kept: list[tuple[int, int, PatternRule, str]] = []
    last_end = -1
    for start, end, rule, text in matches:
        if start < last_end:
            continue
        kept.append((start, end, rule, text))
        last_end = end
    return kept


def find_in_text(
    text: str,
    rules: Sequence[PatternRule] | None = None,
) -> list[tuple[int, int, PatternRule, str]]:
    """Return (start, end, rule, matched_text) for non-overlapping matches."""
    rules = list(rules) if rules is not None else active_rules()
    raw: list[tuple[int, int, PatternRule, str]] = []
    for rule in rules:
        for m in rule.pattern.finditer(text):
            span = m.group(0)
            if not span or not span.strip():
                continue
            raw.append((m.start(), m.end(), rule, span))
    return _non_overlapping(raw)


def _search_variants(snippet: str) -> list[str]:
    """Generate alternate spellings for page.search_for when separators differ."""
    variants: list[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        if s and s not in seen:
            seen.add(s)
            variants.append(s)

    add(snippet)
    trimmed = " ".join(snippet.split())
    add(trimmed)

    # Collapse any run of non-digits between digit groups to a single hyphen /
    # nothing — helps when extraction used · or en-dash but the visual text
    # layer still responds to ASCII hyphen search (or vice versa).
    digits_hyphen = re.sub(r"\D+", "-", snippet.strip())
    digits_hyphen = re.sub(r"-+", "-", digits_hyphen).strip("-")
    add(digits_hyphen)
    add(re.sub(r"\D+", "", snippet))  # continuous digits (rarely finds dashed glyphs)

    # Common PDF/OCR separator swaps
    for sep in ("-", "\u00b7", "\u2013", "\u2014", " "):
        if digits_hyphen.count("-") == 2:
            parts = digits_hyphen.split("-")
            add(sep.join(parts))

    return variants


def _rects_for_span(page: fitz.Page, start: int, end: int, full_text: str) -> list[fitz.Rect]:
    """Map character offsets from page.get_text('text') into quads/rects.

    PyMuPDF does not always give perfect char-index maps for plain text, so we
    fall back to searching for the exact substring when needed.
    """
    snippet = full_text[start:end]
    if not snippet.strip():
        return []

    # Prefer search_for — robust across OCR and text PDFs; try separator variants
    for candidate in _search_variants(snippet):
        rects = page.search_for(candidate, quads=False)
        if rects:
            return [fitz.Rect(r) for r in rects]

    return []


def detect_page(
    page: fitz.Page,
    page_index: int,
    *,
    text: str | None = None,
    rules: Sequence[PatternRule] | None = None,
) -> list[Finding]:
    """Detect findings on a single page."""
    if text is None:
        text = page.get_text("text") or ""
    matches = find_in_text(text, rules=rules)
    findings: list[Finding] = []
    for start, end, rule, matched in matches:
        rects = _rects_for_span(page, start, end, text)
        if not rects:
            # Still record finding so user can manually place if needed
            findings.append(
                Finding(
                    page_index=page_index,
                    label=rule.label,
                    rule_name=rule.name,
                    text=matched,
                    rects=[],
                    selected=False,
                )
            )
            continue
        findings.append(
            Finding(
                page_index=page_index,
                label=rule.label,
                rule_name=rule.name,
                text=matched,
                rects=rects,
                selected=True,
            )
        )
    return findings


def detect_document(
    doc: fitz.Document,
    *,
    page_texts: dict[int, str] | None = None,
    enabled_rules: Iterable[str] | None = None,
) -> list[Finding]:
    """Run detection across all pages."""
    rules = active_rules(enabled_rules)
    all_findings: list[Finding] = []
    for i in range(doc.page_count):
        page = doc.load_page(i)
        text = None if page_texts is None else page_texts.get(i)
        all_findings.extend(detect_page(page, i, text=text, rules=rules))
    return all_findings
