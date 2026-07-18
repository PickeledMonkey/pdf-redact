"""Portable path helpers — frozen (PyInstaller) and source layouts."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Directory containing the executable (frozen) or project root (source)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    # pdf_redact/paths.py → project root
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """Bundled resources (PyInstaller _MEIPASS or package dir)."""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def portable_tesseract_candidates() -> list[Path]:
    """Likely locations for a no-install Tesseract bundle next to the app."""
    root = app_dir()
    names = (
        root / "tesseract" / "tesseract.exe",
        root / "tesseract" / "tesseract",
        root / "Tesseract-OCR" / "tesseract.exe",
        root / "bin" / "tesseract.exe",
        root / "tesseract.exe",
    )
    return list(names)


def resolve_tesseract() -> Path | None:
    """Find tesseract: portable bundle first, then PATH."""
    for candidate in portable_tesseract_candidates():
        if candidate.is_file():
            return candidate

    which = _which("tesseract") or _which("tesseract.exe")
    if which:
        return Path(which)
    return None


def configure_tesseract_env() -> Path | None:
    """Point PATH / TESSDATA_PREFIX at a portable Tesseract if present.

    Returns the tesseract executable path when found.
    """
    exe = resolve_tesseract()
    if exe is None:
        return None

    tess_dir = exe.parent
    tessdata = tess_dir / "tessdata"
    if not tessdata.is_dir():
        # Common layout: tesseract/tessdata next to exe, or parent/tessdata
        alt = tess_dir.parent / "tessdata"
        if alt.is_dir():
            tessdata = alt

    # Prepend so PyMuPDF / subprocess find our binary first
    path_prefix = str(tess_dir)
    current = os.environ.get("PATH", "")
    if path_prefix not in current.split(os.pathsep):
        os.environ["PATH"] = path_prefix + os.pathsep + current

    if tessdata.is_dir():
        os.environ.setdefault("TESSDATA_PREFIX", str(tessdata.parent if tessdata.name == "tessdata" else tessdata))
        # Tesseract expects TESSDATA_PREFIX to be the parent of tessdata/ OR the tessdata dir
        # depending on version; set both conventions safely:
        os.environ["TESSDATA_PREFIX"] = str(tessdata if tessdata.name != "tessdata" else tessdata.parent)

    return exe


def _which(name: str) -> str | None:
    from shutil import which

    return which(name)
