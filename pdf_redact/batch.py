"""Batch / CLI redaction for large PDFs (streaming page workflow).

Designed for documents up to ~15_000 pages. Prefer this over the GUI for
full-document unattended jobs; use the GUI to spot-check report pages.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import fitz

from pdf_redact import __version__
from pdf_redact.detector import Finding, detect_document
from pdf_redact.limits import BATCH_ADVISORY_PAGES
from pdf_redact.ocr import ocr_document, tesseract_available
from pdf_redact.page_ranges import pages_label, parse_page_range
from pdf_redact.patterns import DEFAULT_DISABLED, RULES
from pdf_redact.paths import configure_tesseract_env
from pdf_redact.redactor import apply_redactions

log = logging.getLogger(__name__)


@dataclass
class BatchResult:
    input: str
    output: str
    page_count: int
    pages_processed: int
    pages_with_hits: int
    finding_count: int
    selected_count: int
    rules: list[str]
    ocr_mode: str
    duration_sec: float
    counts_by_rule: dict[str, int]
    pages_with_findings: list[int]
    # Truncated samples only — never dump full PHI into reports by default
    sample_findings: list[dict]


def _default_rules() -> list[str]:
    return [r.name for r in RULES if r.name not in DEFAULT_DISABLED]


def _resolve_rules(names: Sequence[str] | None) -> list[str]:
    if not names:
        return _default_rules()
    known = {r.name for r in RULES}
    bad = [n for n in names if n not in known and n != "manual"]
    if bad:
        raise SystemExit(f"Unknown rule(s): {', '.join(bad)}. Use --list-rules.")
    return list(names)


def _progress_printer(quiet: bool):
    def cb(cur: int, total: int, msg: str) -> None:
        if quiet:
            return
        pct = 100.0 * cur / max(total, 1)
        print(f"\r[{pct:5.1f}%] {msg}          ", end="", file=sys.stderr, flush=True)
        if cur >= total:
            print(file=sys.stderr)

    return cb


def _finding_sample(f: Finding, *, max_chars: int = 24) -> dict:
    """Report-safe sample: rule + page + redacted preview of matched text."""
    raw = (f.text or "").replace("\n", " ").strip()
    if len(raw) <= 4:
        preview = "****"
    else:
        # Keep structure hint only (first/last char) for audit without full PHI
        preview = raw[0] + ("*" * min(len(raw) - 2, max_chars)) + (raw[-1] if len(raw) > 1 else "")
        if len(preview) > max_chars + 2:
            preview = preview[: max_chars + 2]
    return {
        "page": f.page_index + 1,
        "rule": f.rule_name,
        "label": f.label,
        "has_rects": bool(f.rects),
        "selected": f.selected,
        "text_preview": preview,
    }


def run_batch(
    input_path: Path,
    output_path: Path,
    *,
    pages_spec: str | None = None,
    rules: Sequence[str] | None = None,
    ocr_mode: str = "never",
    report_path: Path | None = None,
    quiet: bool = False,
) -> BatchResult:
    """Detect + redact selected pages. ``ocr_mode``: never | auto | always."""
    configure_tesseract_env()
    rule_names = _resolve_rules(rules)
    ocr_mode = ocr_mode.lower().strip()
    if ocr_mode not in {"never", "auto", "always"}:
        raise SystemExit("--ocr must be never, auto, or always")

    t0 = time.perf_counter()
    doc = fitz.open(input_path)
    try:
        page_count = doc.page_count
        if page_count >= BATCH_ADVISORY_PAGES and not quiet:
            print(
                f"Note: {page_count} pages is at/above the {BATCH_ADVISORY_PAGES} advisory "
                "threshold; expect long runtimes (especially with OCR).",
                file=sys.stderr,
            )

        try:
            page_indices = parse_page_range(pages_spec, page_count)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

        if not page_indices:
            raise SystemExit("No pages selected.")

        if not quiet:
            print(
                f"pdf-redact batch v{__version__}: {input_path.name} "
                f"({pages_label(page_indices, page_count)} pages), "
                f"rules={','.join(rule_names)}, ocr={ocr_mode}",
                file=sys.stderr,
            )

        progress = _progress_printer(quiet)
        page_texts: dict[int, str] | None = None

        if ocr_mode != "never":
            st = tesseract_available()
            if not st.available:
                raise SystemExit(f"OCR requested but Tesseract unavailable: {st.detail}")
            only_if_needed = ocr_mode == "auto"
            page_texts = ocr_document(
                doc,
                only_if_needed=only_if_needed,
                page_indices=page_indices,
                progress_callback=progress,
            )

        findings = detect_document(
            doc,
            page_texts=page_texts,
            enabled_rules=rule_names,
            page_indices=page_indices,
            progress_callback=progress,
        )
    finally:
        doc.close()

    # Only redact findings that have coordinates (and selected by default)
    selected = [f for f in findings if f.selected and f.rects]
    apply_redactions(
        input_path,
        findings,
        output_path,
        only_selected=True,
        progress_callback=_progress_printer(quiet),
        large_document=page_count >= 500,
    )

    counts = Counter(f.rule_name for f in findings)
    pages_hit = sorted({f.page_index + 1 for f in findings})
    samples = [_finding_sample(f) for f in findings[:50]]

    result = BatchResult(
        input=str(input_path.resolve()),
        output=str(output_path.resolve()),
        page_count=page_count,
        pages_processed=len(page_indices),
        pages_with_hits=len(pages_hit),
        finding_count=len(findings),
        selected_count=len(selected),
        rules=rule_names,
        ocr_mode=ocr_mode,
        duration_sec=round(time.perf_counter() - t0, 3),
        counts_by_rule=dict(sorted(counts.items())),
        pages_with_findings=pages_hit[:500],  # cap list size in report
        sample_findings=samples,
    )

    if report_path:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tool": "pdf-redact-batch",
            "version": __version__,
            **asdict(result),
        }
        report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        if not quiet:
            print(f"Report → {report_path}", file=sys.stderr)

    if not quiet:
        print(
            f"Done: {result.finding_count} findings "
            f"({result.selected_count} redacted) → {output_path} "
            f"in {result.duration_sec}s",
            file=sys.stderr,
        )
    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pdf-redact-batch",
        description=(
            "Batch PHI/PII redaction for large PDFs (page streaming). "
            "For interactive review of small docs, use: pdf-redact"
        ),
    )
    p.add_argument("input", type=Path, nargs="?", help="Input PDF path")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output redacted PDF (default: <input>_redacted.pdf)",
    )
    p.add_argument(
        "--pages",
        default="all",
        help='Pages to process (1-based), e.g. "1-100,250" or "all" (default: all)',
    )
    p.add_argument(
        "--rules",
        default=None,
        help="Comma-separated rule names (default: GUI defaults). See --list-rules",
    )
    p.add_argument(
        "--ocr",
        choices=("never", "auto", "always"),
        default="never",
        help="OCR mode (default: never). auto=only sparse-text pages",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write JSON audit report (counts + masked samples; not full PHI)",
    )
    p.add_argument("--list-rules", action="store_true", help="List detection rules and exit")
    p.add_argument("-q", "--quiet", action="store_true", help="Minimal stderr output")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_rules:
        for rule in RULES:
            flag = "off" if rule.name in DEFAULT_DISABLED else "on"
            print(f"{rule.name:16}  [{flag:3}]  {rule.label} — {rule.description}")
        return

    if not args.input:
        parser.error("input PDF is required (or use --list-rules)")

    input_path = Path(args.input)
    if not input_path.is_file():
        raise SystemExit(f"Input not found: {input_path}")

    output_path = args.output
    if output_path is None:
        output_path = input_path.with_name(input_path.stem + "_redacted.pdf")

    rule_names = None
    if args.rules:
        rule_names = [r.strip() for r in args.rules.split(",") if r.strip()]

    run_batch(
        input_path,
        output_path,
        pages_spec=args.pages,
        rules=rule_names,
        ocr_mode=args.ocr,
        report_path=args.report,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    main()
