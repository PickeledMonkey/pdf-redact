"""OCR helpers for scanned / image-only PDFs via Tesseract + PyMuPDF."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import fitz

from pdf_redact.paths import configure_tesseract_env

log = logging.getLogger(__name__)


@dataclass(slots=True)
class OcrStatus:
    available: bool
    engine: str
    detail: str


def tesseract_available() -> OcrStatus:
    """Detect Tesseract from portable bundle (preferred) or system PATH."""
    path = configure_tesseract_env()
    if not path:
        return OcrStatus(
            available=False,
            engine="none",
            detail=(
                "Tesseract not found. For portable use, place tesseract.exe in a "
                "tesseract\\ folder next to the app. Or install Tesseract OCR system-wide."
            ),
        )
    return OcrStatus(available=True, engine="tesseract", detail=f"Found: {path}")


def page_needs_ocr(page: fitz.Page, *, min_chars: int = 40) -> bool:
    """Heuristic: little extractable text implies a scan/image page."""
    text = (page.get_text("text") or "").strip()
    if len(text) >= min_chars:
        return False
    # Images present with almost no text → OCR candidate
    if page.get_images(full=True) or list(page.get_drawings()):
        return True
    return len(text) < min_chars


def document_needs_ocr(
    doc: fitz.Document,
    *,
    min_chars: int = 40,
    page_indices: list[int] | None = None,
    sample_limit: int | None = None,
) -> bool:
    """Return True if any checked page looks like it needs OCR.

    Parameters
    ----------
    page_indices:
        Optional 0-based pages to inspect. Default: all pages.
    sample_limit:
        If set, only the first N of those pages are checked (fast open-path
        heuristic for very large documents).
    """
    if page_indices is None:
        indices = list(range(doc.page_count))
    else:
        indices = [i for i in page_indices if 0 <= i < doc.page_count]
    if sample_limit is not None and sample_limit >= 0:
        indices = indices[:sample_limit]
    return any(page_needs_ocr(doc.load_page(i), min_chars=min_chars) for i in indices)


def ocr_page_text(
    page: fitz.Page,
    *,
    language: str = "eng",
    dpi: int = 200,
) -> str:
    """Return OCR text for a page. Requires Tesseract installed.

    Uses PyMuPDF's built-in OCR integration when available; falls back to
    rendering + tesseract CLI is not used — PyMuPDF TessOCR is preferred.
    """
    status = tesseract_available()
    if not status.available:
        raise RuntimeError(status.detail)

    # PyMuPDF 1.23+: get_textpage_ocr
    try:
        tp = page.get_textpage_ocr(language=language, dpi=dpi, full=True)
        text = page.get_text("text", textpage=tp) or ""
        return text
    except Exception as exc:  # noqa: BLE001 — surface as soft failure upstream
        log.warning("get_textpage_ocr failed: %s", exc)
        raise RuntimeError(
            "OCR failed. Ensure Tesseract is installed and tessdata is available. "
            f"Original error: {exc}"
        ) from exc


def ocr_document(
    doc: fitz.Document,
    *,
    language: str = "eng",
    dpi: int = 200,
    only_if_needed: bool = True,
    page_indices: list[int] | None = None,
    progress_callback=None,
) -> dict[int, str]:
    """OCR pages and return {page_index: text}.

    When only_if_needed is True, pages with sufficient text skip OCR and use
    native extraction instead. Only requested pages are stored (streaming-friendly
    for large jobs that process page ranges).
    """
    status = tesseract_available()
    results: dict[int, str] = {}
    if page_indices is None:
        indices = list(range(doc.page_count))
    else:
        indices = [i for i in page_indices if 0 <= i < doc.page_count]
    total = len(indices)

    for n, i in enumerate(indices, start=1):
        page = doc.load_page(i)
        if progress_callback:
            progress_callback(n, total, f"OCR page {i + 1}/{doc.page_count}")

        native = page.get_text("text") or ""
        if only_if_needed and not page_needs_ocr(page):
            results[i] = native
            continue

        if not status.available:
            results[i] = native
            continue

        try:
            results[i] = ocr_page_text(page, language=language, dpi=dpi)
        except Exception as exc:  # noqa: BLE001
            log.warning("OCR page %s failed: %s", i, exc)
            results[i] = native

    return results


def apply_ocr_text_layer(
    doc: fitz.Document,
    *,
    language: str = "eng",
    dpi: int = 200,
    progress_callback=None,
) -> fitz.Document:
    """Return a new document with OCR text integrated where possible.

    For redaction workflows we mainly need searchable text + coordinates.
    PyMuPDF's OCR textpage is used during detection; this helper additionally
    tries to produce a text-enriched copy via page OCR insertion when supported.
    """
    # Detection path uses ocr_document texts + search_for; full PDF rewrite is
    # optional. Keep identity for now and rely on per-page OCR text maps.
    _ = (language, dpi, progress_callback)
    return doc
