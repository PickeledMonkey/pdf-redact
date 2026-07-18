#!/usr/bin/env python3
"""Create a source-level portable zip (for machines that will run Build-Portable.ps1).

For the true no-install runtime package, run Build-Portable.ps1 on Windows
(or use the GitHub Actions artifact pdf-redact-portable.zip).
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
OUTPUT = APP_ROOT.parent / "pdf-redact-source-portable.zip"

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".idea",
    ".vscode",
    "build",
    "dist",
    ".pytest_cache",
    "pdf_redact.egg-info",
    "*.egg-info",
}

SKIP_FILE_NAMES = {".DS_Store", "Thumbs.db"}
SKIP_FILE_SUFFIXES = {".pyc", ".pyo", ".log"}


def should_skip(path: Path) -> bool:
    if path.name in SKIP_FILE_NAMES:
        return True
    if path.suffix in SKIP_FILE_SUFFIXES:
        return True
    for part in path.parts:
        if part in SKIP_DIR_NAMES or part.endswith(".egg-info"):
            return True
    return False


def main() -> None:
    files_added = 0
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for dirpath, dirnames, filenames in os.walk(APP_ROOT):
            dirnames[:] = [
                n
                for n in dirnames
                if n not in SKIP_DIR_NAMES and not n.endswith(".egg-info")
            ]
            for filename in sorted(filenames):
                path = Path(dirpath) / filename
                if should_skip(path):
                    continue
                arcname = Path("pdf-redact") / path.relative_to(APP_ROOT)
                archive.write(path, arcname.as_posix())
                files_added += 1
                print(arcname.as_posix())

    print(f"\nCreated {OUTPUT} with {files_added} files.")
    print("On Windows: unzip, then run Build-Portable.ps1 for a no-install package.")


if __name__ == "__main__":
    main()
