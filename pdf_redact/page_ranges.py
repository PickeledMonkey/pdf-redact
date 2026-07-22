"""Parse page-range strings like ``1-10,15,20-`` (1-based, inclusive)."""

from __future__ import annotations

from typing import Iterable


def parse_page_range(spec: str | None, page_count: int) -> list[int]:
    """Return sorted unique 0-based page indices.

    ``spec`` examples (1-based for users):
      None / "" / "all"  → every page
      "1-10"             → pages 1..10
      "1,3,5-7"          → 1,3,5,6,7
      "100-"             → from 100 through end
      "-50"              → from 1 through 50
    """
    if page_count <= 0:
        return []

    if spec is None or not str(spec).strip() or str(spec).strip().lower() == "all":
        return list(range(page_count))

    selected: set[int] = set()
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            left, right = part.split("-", 1)
            left = left.strip()
            right = right.strip()
            start = 1 if not left else int(left)
            end = page_count if not right else int(right)
            if start < 1 or end < 1:
                raise ValueError(f"Page numbers must be >= 1 (got {part!r})")
            if start > end:
                raise ValueError(f"Invalid range {part!r}: start > end")
            for n in range(start, end + 1):
                if 1 <= n <= page_count:
                    selected.add(n - 1)
        else:
            n = int(part)
            if n < 1 or n > page_count:
                raise ValueError(f"Page {n} out of range 1..{page_count}")
            selected.add(n - 1)

    return sorted(selected)


def pages_label(indices: Iterable[int], page_count: int) -> str:
    """Short human label for a page index set."""
    idx = list(indices)
    if not idx:
        return "none"
    if len(idx) == page_count:
        return f"all {page_count}"
    return f"{len(idx)} of {page_count}"
