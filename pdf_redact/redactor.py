"""Apply redactions to a PDF and save a safe output copy."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import fitz

from pdf_redact.detector import Finding, findings_for_page


def apply_redactions(
    source: fitz.Document | str | Path,
    findings: Sequence[Finding],
    output_path: str | Path,
    *,
    fill: tuple[float, float, float] = (0, 0, 0),
    text_overlay: str = "",
    only_selected: bool = True,
    progress_callback=None,
    large_document: bool | None = None,
) -> Path:
    """Burn in redaction annotations for selected findings and write PDF.

    Returns the output path.

    When ``large_document`` is True (or auto-detected for high page counts),
    save uses slightly lighter garbage collection to reduce peak memory/time.
    """
    output_path = Path(output_path)
    if isinstance(source, (str, Path)):
        doc = fitz.open(source)
        owns_doc = True
    else:
        doc = source
        owns_doc = False

    try:
        # Group rects by page
        by_page: dict[int, list[fitz.Rect]] = {}
        for finding in findings:
            if only_selected and not finding.selected:
                continue
            if not finding.rects:
                continue
            by_page.setdefault(finding.page_index, []).extend(finding.rects)

        pages_with_work = sorted(by_page.keys())
        total = max(len(pages_with_work), 1)
        for n, page_index in enumerate(pages_with_work, start=1):
            if progress_callback:
                progress_callback(n, total, f"Redacting page {page_index + 1}")
            if page_index < 0 or page_index >= doc.page_count:
                continue
            page = doc.load_page(page_index)
            for rect in by_page[page_index]:
                r = fitz.Rect(rect)
                if r.is_empty or r.is_infinite:
                    continue
                # Slight padding so partial glyph edges are covered
                r += (-1, -1, 1, 1)
                page.add_redact_annot(
                    r,
                    text=text_overlay,
                    fill=fill,
                    text_color=(1, 1, 1),
                    cross_out=False,
                )
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_PIXELS,
                graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )

        # Also scrub common metadata that may contain names
        doc.set_metadata(
            {
                "title": "",
                "author": "",
                "subject": "",
                "keywords": "",
                "creator": "pdf-redact",
                "producer": "pdf-redact",
            }
        )
        # Remove XML metadata if present
        try:
            doc.del_xml_metadata()
        except Exception:  # noqa: BLE001
            pass

        if large_document is None:
            large_document = doc.page_count >= 500

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if large_document:
            # Lighter pass: still deflate; avoid heaviest clean/gc for huge files
            doc.save(
                output_path,
                garbage=3,
                deflate=True,
                clean=False,
                encryption=fitz.PDF_ENCRYPT_NONE,
            )
        else:
            doc.save(
                output_path,
                garbage=4,
                deflate=True,
                clean=True,
                encryption=fitz.PDF_ENCRYPT_NONE,
            )
    finally:
        if owns_doc:
            doc.close()

    return output_path


def render_page_image(
    doc: fitz.Document,
    page_index: int,
    *,
    zoom: float = 1.5,
    findings: Sequence[Finding] | None = None,
    show_unselected: bool = True,
) -> "Image.Image":  # type: ignore[name-defined]
    """Render a page to a PIL Image, overlaying finding rectangles.

    Pass only this page's findings when possible (avoids O(all findings) on
    large documents). Full lists are still filtered safely.
    """
    from PIL import Image, ImageDraw

    page = doc.load_page(page_index)
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    draw = ImageDraw.Draw(img, "RGBA")

    if findings:
        page_findings = findings_for_page(findings, page_index)
        for f in page_findings:
            if not f.rects:
                continue
            if f.selected:
                fill = (220, 40, 40, 90)
                outline = (200, 20, 20, 220)
            else:
                if not show_unselected:
                    continue
                fill = (40, 120, 220, 50)
                outline = (30, 90, 200, 180)
            for rect in f.rects:
                x0, y0, x1, y1 = (rect.x0 * zoom, rect.y0 * zoom, rect.x1 * zoom, rect.y1 * zoom)
                draw.rectangle([x0, y0, x1, y1], fill=fill, outline=outline, width=2)

    return img
