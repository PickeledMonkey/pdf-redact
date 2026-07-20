"""Detect PHI/PII spans in page text and map them to PDF coordinates."""

from __future__ import annotations

from collections import defaultdict
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

    # Continuous digits last — often matches multiple unrelated numbers on a page
    continuous = re.sub(r"\D+", "", snippet)
    if continuous and continuous != digits_hyphen:
        add(continuous)

    # Common PDF/OCR separator swaps (exact group structure preserved)
    if digits_hyphen.count("-") >= 1:
        parts = digits_hyphen.split("-")
        for sep in ("-", "\u00b7", "\u2013", "\u2014", " ", " - "):
            add(sep.join(parts))

    return variants


def _pick_occurrence(
    rects: list[fitz.Rect],
    *,
    full_text: str,
    start: int,
    candidate: str,
) -> list[fitz.Rect]:
    """When search_for hits multiple places, pick the occurrence matching this span."""
    if not rects:
        return []
    if len(rects) == 1:
        return [rects[0]]

    # Count how many times `candidate` appears before this match in extracted text.
    # Prefer that index into search_for results (same reading order as get_text).
    occurrence = full_text[:start].count(candidate)
    if 0 <= occurrence < len(rects):
        return [rects[occurrence]]

    # Fallback: first hit only (avoid redacting every similar number on the page)
    return [rects[0]]


def _rects_from_words(page: fitz.Page, snippet: str) -> list[fitz.Rect]:
    """Locate multi-token snippets via page word list (e.g. '123 - 45 - 6789')."""
    tokens = [t for t in re.split(r"\s+", snippet.strip()) if t]
    if not tokens:
        return []

    words = page.get_text("words") or []
    if not words:
        return []

    # Group by (block, line) so we only join tokens on the same line
    lines: dict[tuple[int, int], list[tuple]] = defaultdict(list)
    for w in words:
        # w: x0, y0, x1, y1, word, block_no, line_no, word_no
        lines[(int(w[5]), int(w[6]))].append(w)

    n = len(tokens)
    for line_words in lines.values():
        line_words = sorted(line_words, key=lambda w: int(w[7]))
        texts = [str(w[4]) for w in line_words]
        for i in range(0, len(texts) - n + 1):
            if texts[i : i + n] == tokens:
                rect = fitz.Rect(line_words[i][:4])
                for w in line_words[i + 1 : i + n]:
                    rect |= fitz.Rect(w[:4])
                return [rect]

    # Digit-group fallback: find area/group/serial (or similar) in order on one line
    groups = re.findall(r"\d+", snippet)
    if len(groups) < 2:
        return []

    for line_words in lines.values():
        line_words = sorted(line_words, key=lambda w: int(w[7]))
        # Flatten digits in reading order, tracking rects per digit-run word
        found_rects: list[fitz.Rect] = []
        gi = 0
        for w in line_words:
            wt = str(w[4])
            # Word may be "123-45-6789" or a single group "123"
            parts = re.findall(r"\d+", wt)
            if not parts:
                continue
            for part in parts:
                if gi < len(groups) and part == groups[gi]:
                    found_rects.append(fitz.Rect(w[:4]))
                    gi += 1
                    if gi == len(groups):
                        union = found_rects[0]
                        for r in found_rects[1:]:
                            union |= r
                        return [union]
                elif gi > 0 and (gi < len(groups) and part != groups[gi]):
                    # broken sequence — reset and maybe restart on this part
                    found_rects = []
                    gi = 0
                    if part == groups[0]:
                        found_rects = [fitz.Rect(w[:4])]
                        gi = 1
    return []


def _rects_for_span(page: fitz.Page, start: int, end: int, full_text: str) -> list[fitz.Rect]:
    """Map character offsets from page.get_text('text') into quads/rects.

    PyMuPDF does not always give perfect char-index maps for plain text, so we
    fall back to searching for the exact substring, separator variants, then
    word-sequence geometry (important for spaced SSNs like '123 - 45 - 6789').
    """
    snippet = full_text[start:end]
    if not snippet.strip():
        return []

    # 1) search_for with exact + separator variants; disambiguate multi-hits
    for candidate in _search_variants(snippet):
        hits = page.search_for(candidate, quads=False) or []
        if not hits:
            continue
        rects = [fitz.Rect(r) for r in hits]
        # Exact / near-exact candidates: use occurrence index
        if candidate == snippet or candidate == " ".join(snippet.split()):
            return _pick_occurrence(rects, full_text=full_text, start=start, candidate=candidate)
        # Variant hit: only trust a unique match (avoid wrong line for '123-45-6789'
        # when the real hit was '123 - 45 - 6789' on another line)
        if len(rects) == 1:
            return rects

    # 2) Word-list geometry for spaced / multi-token values
    word_rects = _rects_from_words(page, snippet)
    if word_rects:
        return word_rects

    # 3) Last resort: continuous digits only if unique on page
    continuous = re.sub(r"\D+", "", snippet)
    if continuous and len(continuous) >= 4:
        hits = page.search_for(continuous, quads=False) or []
        if len(hits) == 1:
            return [fitz.Rect(hits[0])]
        if hits:
            return _pick_occurrence(
                [fitz.Rect(r) for r in hits],
                full_text=full_text,
                start=start,
                candidate=continuous,
            )

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
