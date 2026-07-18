# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — one-folder portable build (no install).
# Build on Windows:  powershell -File Build-Portable.ps1

from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

ctk_datas, ctk_binaries, ctk_hidden = collect_all("customtkinter")
dnd_datas, dnd_binaries, dnd_hidden = collect_all("tkinterdnd2")

try:
    pil_datas = collect_data_files("PIL")
except Exception:
    pil_datas = []

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=ctk_binaries + dnd_binaries,
    datas=ctk_datas + dnd_datas + pil_datas,
    hiddenimports=[
        "PIL._tkinter_finder",
        "tkinter",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "customtkinter",
        "tkinterdnd2",
        "fitz",
        "regex",
        *ctk_hidden,
        *dnd_hidden,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PDF-Redact",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PDF-Redact",
)
