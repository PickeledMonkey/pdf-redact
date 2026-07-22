"""Thresholds for interactive GUI vs batch/large-document workflows."""

from __future__ import annotations

# GUI: skip auto full-document scan and show large-doc guidance at/above this.
GUI_LARGE_PAGE_THRESHOLD = 500

# GUI: cap findings rows in the scrollable list (all-pages view).
GUI_FINDINGS_LIST_CAP = 200

# GUI: warn before full-document OCR at/above this many pages.
GUI_OCR_WARN_PAGES = 200

# Batch/CLI: soft advisory when page count is extreme (still allowed).
BATCH_ADVISORY_PAGES = 15_000
