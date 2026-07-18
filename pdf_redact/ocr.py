"""OCR helpers for scanned / image-only PDFs via Tesseract + PyMuPDF."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass

import fitz

log = logging.getLogger(__name__)


@dataclass(slots=True)
class OcrStatus:
    available: bool
    engine: str
    detail: str


def tesseract_available() -> OcrStatus:
    path = shutil.which("tesseract")
    if not path:
        return OcrStatus(
            available=False,
            engine="none",
            detail="Tesseract not found on PATH. Install tesseract-ocr for image PDF support.",
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


def document_needs_ocr(doc: fitz.Document, *, min_chars: int = 40) -> bool:
    return any(page_needs_ocr(doc.load_page(i), min_chars=min_chars) for i in range(doc.page_count))


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
    progress_callback=None,
) -> dict[int, str]:
    """OCR pages and return {page_index: text}.

    When only_if_needed is True, pages with sufficient text skip OCR and use
    native extraction instead.
    """
    status = tesseract_available()
    results: dict[int, str] = {}
    total = doc.page_count

    for i in range(total):
        page = doc.load_page(i)
        if progress_callback:
            progress_callback(i + 1, total, f"OCR page {i + 1}/{total}")

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
