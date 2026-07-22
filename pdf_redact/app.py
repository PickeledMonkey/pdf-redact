"""pdf-redact GUI — drag-and-drop PHI/PII PDF redaction with OCR."""

from __future__ import annotations

import logging
import sys
import threading
import tkinter as tk
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
from pathlib import Path
from typing import Callable

import customtkinter as ctk
import fitz
from PIL import Image, ImageTk

from pdf_redact import __version__
from pdf_redact.detector import Finding, detect_document, findings_for_page
from pdf_redact.limits import (
    GUI_FINDINGS_LIST_CAP,
    GUI_LARGE_PAGE_THRESHOLD,
    GUI_OCR_WARN_PAGES,
)
from pdf_redact.ocr import document_needs_ocr, ocr_document, tesseract_available
from pdf_redact.paths import configure_tesseract_env
from pdf_redact.patterns import DEFAULT_DISABLED, RULES
from pdf_redact.redactor import apply_redactions, render_page_image

log = logging.getLogger(__name__)

# Prefer portable Tesseract next to the exe before any OCR checks
configure_tesseract_env()

# Drag-and-drop (optional if tkinterdnd2 missing)
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _HAS_DND = True
except ImportError:  # pragma: no cover
    DND_FILES = None  # type: ignore[assignment]
    TkinterDnD = None  # type: ignore[assignment,misc]
    _HAS_DND = False


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class PdfRedactApp:
    """Main application controller + window."""

    def __init__(self) -> None:
        if _HAS_DND:
            self.root = TkinterDnD.Tk()
        else:
            self.root = ctk.CTk()  # type: ignore[assignment]

        self.root.title(f"PDF Redact — PHI/PII Redaction  v{__version__}")
        self.root.geometry("1280x820")
        self.root.minsize(960, 640)

        # Wrap root styling when using TkinterDnD (classic Tk)
        if _HAS_DND:
            self.root.configure(bg="#1a1a1a")

        self.doc: fitz.Document | None = None
        self.source_path: Path | None = None
        self.findings: list[Finding] = []
        self.page_texts: dict[int, str] = {}
        self.current_page = 0
        self.zoom = 1.4
        self._photo: ImageTk.PhotoImage | None = None
        self._busy = False
        self._rule_vars: dict[str, ctk.BooleanVar] = {}
        self._draw_start: tuple[float, float] | None = None
        self._draw_rect_id: int | None = None
        self._manual_mode = False
        # Findings list: "page" = current page only; "all" = full list (capped)
        self._findings_scope = "page"
        self._large_doc = False

        self._build_ui()
        self._update_ocr_badge()
        self._set_status("Drop a PDF here, or click Open.")

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        # Outer frame using CTk when possible
        if _HAS_DND:
            outer = ctk.CTkFrame(self.root, fg_color="#1a1a1a")
            outer.pack(fill="both", expand=True)
            host = outer
        else:
            host = self.root

        # Toolbar
        toolbar = ctk.CTkFrame(host, corner_radius=0, fg_color="#222222")
        toolbar.pack(fill="x", padx=0, pady=0)

        ctk.CTkButton(toolbar, text="Open PDF", width=100, command=self.open_file).pack(
            side="left", padx=(12, 6), pady=10
        )
        ctk.CTkButton(
            toolbar, text="Scan Page", width=90, command=self.scan_current_page
        ).pack(side="left", padx=6, pady=10)
        ctk.CTkButton(
            toolbar, text="Scan All", width=90, command=self.scan_document
        ).pack(side="left", padx=6, pady=10)
        ctk.CTkButton(
            toolbar, text="Run OCR", width=90, command=self.run_ocr, fg_color="#3d5a80"
        ).pack(side="left", padx=6, pady=10)
        ctk.CTkButton(
            toolbar,
            text="Export Redacted",
            width=130,
            command=self.export_redacted,
            fg_color="#8b1e1e",
            hover_color="#a32828",
        ).pack(side="left", padx=6, pady=10)

        self.manual_btn = ctk.CTkButton(
            toolbar,
            text="Manual Box: Off",
            width=120,
            command=self.toggle_manual,
            fg_color="#444",
        )
        self.manual_btn.pack(side="left", padx=6, pady=10)

        self.ocr_badge = ctk.CTkLabel(toolbar, text="", font=ctk.CTkFont(size=12))
        self.ocr_badge.pack(side="right", padx=12)

        # Body: left preview | right findings
        body = ctk.CTkFrame(host, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        # Preview panel
        left = ctk.CTkFrame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        nav = ctk.CTkFrame(left, fg_color="transparent")
        nav.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        ctk.CTkButton(nav, text="◀", width=40, command=self.prev_page).pack(side="left")
        self.page_label = ctk.CTkLabel(nav, text="Page — / —")
        self.page_label.pack(side="left", padx=10)
        ctk.CTkButton(nav, text="▶", width=40, command=self.next_page).pack(side="left")
        ctk.CTkLabel(nav, text="Go", font=ctk.CTkFont(size=12)).pack(side="left", padx=(12, 4))
        self.page_jump = ctk.CTkEntry(nav, width=56, placeholder_text="#")
        self.page_jump.pack(side="left")
        self.page_jump.bind("<Return>", lambda _e: self.jump_to_page())
        ctk.CTkButton(nav, text="Go", width=40, command=self.jump_to_page).pack(
            side="left", padx=(4, 0)
        )
        ctk.CTkButton(nav, text="−", width=36, command=lambda: self.adjust_zoom(-0.15)).pack(
            side="right", padx=(4, 0)
        )
        ctk.CTkButton(nav, text="+", width=36, command=lambda: self.adjust_zoom(0.15)).pack(
            side="right"
        )

        # Canvas for page image (classic tk for scroll + drag draw)
        canvas_frame = ctk.CTkFrame(left)
        canvas_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(canvas_frame, bg="#2b2b2b", highlightthickness=0)
        yscroll = tk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        xscroll = tk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")

        self.drop_hint = ctk.CTkLabel(
            left,
            text="Drag & drop a PDF here\n\nDetects SSN, phone, email, DOB, MRN, cards, addresses…\nOCR for scanned pages (requires Tesseract)",
            font=ctk.CTkFont(size=15),
            text_color="#aaaaaa",
        )
        self.drop_hint.place(relx=0.5, rely=0.5, anchor="center")

        if _HAS_DND:
            self.canvas.drop_target_register(DND_FILES)
            self.canvas.dnd_bind("<<Drop>>", self._on_drop)
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)

        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))

        # Right panel
        right = ctk.CTkFrame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right.grid_rowconfigure(2, weight=1)
        right.grid_columnconfigure(0, weight=1)
        # findings panel owns row 2 of right

        ctk.CTkLabel(
            right, text="Detection rules", font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))

        rules_frame = ctk.CTkScrollableFrame(right, height=140)
        rules_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        for rule in RULES:
            var = ctk.BooleanVar(value=rule.name not in DEFAULT_DISABLED)
            self._rule_vars[rule.name] = var
            ctk.CTkCheckBox(
                rules_frame,
                text=f"{rule.label}  ({rule.name})",
                variable=var,
                font=ctk.CTkFont(size=12),
            ).pack(anchor="w", pady=2)

        findings_header = ctk.CTkFrame(right, fg_color="transparent")
        findings_header.grid(row=2, column=0, sticky="nsew", padx=8, pady=(8, 4))
        findings_header.grid_rowconfigure(2, weight=1)
        findings_header.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(findings_header, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            hdr, text="Findings", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left")
        ctk.CTkButton(
            hdr, text="This page", width=72, command=lambda: self._set_findings_scope("page")
        ).pack(side="right", padx=2)
        ctk.CTkButton(
            hdr, text="All", width=44, command=lambda: self._set_findings_scope("all")
        ).pack(side="right", padx=2)
        ctk.CTkButton(
            hdr, text="✓", width=32, command=lambda: self._select_all(True)
        ).pack(side="right", padx=2)
        ctk.CTkButton(
            hdr, text="✗", width=32, command=lambda: self._select_all(False)
        ).pack(side="right", padx=2)
        self.findings_meta = ctk.CTkLabel(
            findings_header, text="", anchor="w", font=ctk.CTkFont(size=11), text_color="#888"
        )
        self.findings_meta.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        self.findings_list = ctk.CTkScrollableFrame(findings_header)
        self.findings_list.grid(row=2, column=0, sticky="nsew", pady=(6, 0))
        # Parallel to displayed rows: indices into self.findings
        self._finding_vars: list[ctk.BooleanVar] = []
        self._finding_row_indices: list[int] = []

        # Status bar
        self.status = ctk.CTkLabel(host, text="", anchor="w", font=ctk.CTkFont(size=12))
        self.status.pack(fill="x", padx=12, pady=(0, 8))

        self.progress = ctk.CTkProgressBar(host, height=6)
        self.progress.pack(fill="x", padx=12, pady=(0, 10))
        self.progress.set(0)

    # -------------------------------------------------------------- helpers
    def _set_status(self, msg: str) -> None:
        self.status.configure(text=msg)
        log.info(msg)

    def _update_ocr_badge(self) -> None:
        st = tesseract_available()
        if st.available:
            self.ocr_badge.configure(text="OCR: ready (Tesseract)", text_color="#6fcf97")
        else:
            self.ocr_badge.configure(text="OCR: Tesseract missing", text_color="#f2c94c")

    def _enabled_rules(self) -> list[str]:
        return [name for name, var in self._rule_vars.items() if var.get()]

    def _run_async(self, work: Callable[[], None], on_done: Callable[[], None] | None = None) -> None:
        if self._busy:
            self._set_status("Busy — please wait…")
            return

        def runner() -> None:
            self._busy = True
            try:
                work()
            except Exception as exc:  # noqa: BLE001
                log.exception("Background task failed")
                self.root.after(0, lambda: messagebox.showerror("Error", str(exc)))
            finally:
                self._busy = False
                if on_done:
                    self.root.after(0, on_done)

        threading.Thread(target=runner, daemon=True).start()

    def _on_drop(self, event) -> None:  # noqa: ANN001
        raw = event.data
        # Tk DnD may wrap paths in braces
        paths = self.root.tk.splitlist(raw)
        for p in paths:
            path = Path(p.strip("{}"))
            if path.suffix.lower() == ".pdf" and path.is_file():
                self.load_pdf(path)
                return
        self._set_status("Drop a .pdf file.")

    def _on_mousewheel(self, event) -> None:  # noqa: ANN001
        delta = -1 if event.delta > 0 else 1
        if sys.platform == "darwin":
            delta = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(delta, "units")

    # -------------------------------------------------------------- document
    def open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Open PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if path:
            self.load_pdf(Path(path))

    def load_pdf(self, path: Path) -> None:
        try:
            if self.doc:
                self.doc.close()
            self.doc = fitz.open(path)
            self.source_path = path
            self.findings = []
            self.page_texts = {}
            self.current_page = 0
            self._large_doc = self.doc.page_count >= GUI_LARGE_PAGE_THRESHOLD
            # Large docs: list current page only by default to keep UI responsive
            self._findings_scope = "page" if self._large_doc else "all"
            self.drop_hint.place_forget()
            self._refresh_findings_panel()
            self.render_current()

            n_pages = self.doc.page_count
            # Sample first pages only for OCR hint on huge files
            sample = 25 if self._large_doc else None
            needs = document_needs_ocr(self.doc, sample_limit=sample)
            hint = " — scanned pages likely; use Run OCR or batch --ocr auto" if needs else ""

            if self._large_doc:
                self._set_status(
                    f"Loaded {path.name} ({n_pages} pages) — large document mode{hint}"
                )
                messagebox.showinfo(
                    "Large PDF",
                    f"This file has {n_pages} pages "
                    f"(threshold {GUI_LARGE_PAGE_THRESHOLD}).\n\n"
                    "Interactive tips:\n"
                    "  • Auto full-scan is skipped\n"
                    "  • Use Scan Page for the current page\n"
                    "  • Use Scan All only if you accept a long wait\n"
                    "  • Jump to a page with Go\n\n"
                    "For full-document jobs (up to ~15 000 pages), prefer the CLI:\n"
                    "  pdf-redact-batch input.pdf -o out.pdf --report report.json\n\n"
                    "Spot-check output pages here after batch.",
                )
            else:
                self._set_status(f"Loaded {path.name} ({n_pages} pages){hint}")
                # Auto-scan text layer for normal-sized docs only
                self.scan_document()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Open failed", str(exc))

    def prev_page(self) -> None:
        if not self.doc:
            return
        if self.current_page > 0:
            self.current_page -= 1
            self.render_current()
            if self._findings_scope == "page":
                self._refresh_findings_panel()

    def next_page(self) -> None:
        if not self.doc:
            return
        if self.current_page < self.doc.page_count - 1:
            self.current_page += 1
            self.render_current()
            if self._findings_scope == "page":
                self._refresh_findings_panel()

    def jump_to_page(self) -> None:
        if not self.doc:
            return
        raw = self.page_jump.get().strip()
        if not raw:
            return
        try:
            n = int(raw)
        except ValueError:
            messagebox.showwarning("Invalid page", "Enter a page number (1-based).")
            return
        if n < 1 or n > self.doc.page_count:
            messagebox.showwarning(
                "Out of range", f"Page must be between 1 and {self.doc.page_count}."
            )
            return
        self.current_page = n - 1
        self.render_current()
        if self._findings_scope == "page":
            self._refresh_findings_panel()

    def adjust_zoom(self, delta: float) -> None:
        self.zoom = max(0.5, min(3.5, self.zoom + delta))
        self.render_current()

    def render_current(self) -> None:
        if not self.doc:
            return
        page_findings = findings_for_page(self.findings, self.current_page)
        img = render_page_image(
            self.doc,
            self.current_page,
            zoom=self.zoom,
            findings=page_findings,
        )
        self._photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo, tags="page")
        self.canvas.configure(scrollregion=(0, 0, img.width, img.height))
        mode = "large-doc" if self._large_doc else "zoom"
        self.page_label.configure(
            text=(
                f"Page {self.current_page + 1} / {self.doc.page_count}  ·  "
                f"{self.zoom:.0%}  ·  {mode}"
            )
        )

    # -------------------------------------------------------------- scan/OCR
    def scan_current_page(self) -> None:
        if not self.doc:
            self._set_status("Open a PDF first.")
            return
        self._scan_pages([self.current_page], replace_other_pages=False)

    def scan_document(self) -> None:
        if not self.doc:
            self._set_status("Open a PDF first.")
            return
        if self._large_doc:
            ok = messagebox.askyesno(
                "Scan entire document?",
                f"This PDF has {self.doc.page_count} pages.\n\n"
                "A full interactive scan may take a long time and use a lot of memory.\n"
                "Prefer: Scan Page, or CLI:\n"
                "  pdf-redact-batch input.pdf -o out.pdf\n\n"
                "Continue with full Scan All?",
            )
            if not ok:
                self._set_status("Full scan cancelled — use Scan Page or pdf-redact-batch.")
                return
        self._scan_pages(list(range(self.doc.page_count)), replace_other_pages=True)

    def _scan_pages(self, page_indices: list[int], *, replace_other_pages: bool) -> None:
        def progress(cur: int, total: int, msg: str) -> None:
            self.root.after(0, lambda: self.progress.set(cur / max(total, 1)))
            self.root.after(0, lambda: self._set_status(msg))

        def work() -> None:
            new_findings = detect_document(
                self.doc,
                page_texts=self.page_texts or None,
                enabled_rules=self._enabled_rules(),
                page_indices=page_indices,
                progress_callback=progress,
            )
            if replace_other_pages:
                self.findings = new_findings
            else:
                # Replace findings only for scanned pages; keep others
                keep = [f for f in self.findings if f.page_index not in set(page_indices)]
                self.findings = keep + new_findings

        def done() -> None:
            selected = sum(1 for f in self.findings if f.selected)
            self._refresh_findings_panel()
            self.render_current()
            self._set_status(
                f"Found {len(self.findings)} items ({selected} selected for redaction)."
            )
            self.progress.set(0)

        self._run_async(work, done)

    def run_ocr(self) -> None:
        if not self.doc:
            self._set_status("Open a PDF first.")
            return
        st = tesseract_available()
        if not st.available:
            messagebox.showwarning(
                "OCR unavailable",
                st.detail
                + "\n\nDebian/Ubuntu:  sudo apt install tesseract-ocr\n"
                "Fedora:          sudo dnf install tesseract\n"
                "macOS:           brew install tesseract",
            )
            return

        page_indices: list[int]
        if self.doc.page_count >= GUI_OCR_WARN_PAGES:
            choice = messagebox.askyesnocancel(
                "OCR scope",
                f"This PDF has {self.doc.page_count} pages.\n\n"
                "Yes = OCR current page only (recommended)\n"
                "No = OCR entire document (slow / heavy)\n"
                "Cancel = abort\n\n"
                "For bulk OCR + redact, use:\n"
                "  pdf-redact-batch input.pdf -o out.pdf --ocr auto",
            )
            if choice is None:
                return
            if choice:
                page_indices = [self.current_page]
            else:
                page_indices = list(range(self.doc.page_count))
        else:
            page_indices = list(range(self.doc.page_count))

        def progress(cur: int, total: int, msg: str) -> None:
            self.root.after(0, lambda: self.progress.set(cur / max(total, 1)))
            self.root.after(0, lambda: self._set_status(msg))

        def work() -> None:
            texts = ocr_document(
                self.doc,
                only_if_needed=True,
                page_indices=page_indices,
                progress_callback=progress,
            )
            self.page_texts.update(texts)
            new_findings = detect_document(
                self.doc,
                page_texts=self.page_texts,
                enabled_rules=self._enabled_rules(),
                page_indices=page_indices,
                progress_callback=progress,
            )
            keep = [f for f in self.findings if f.page_index not in set(page_indices)]
            self.findings = keep + new_findings

        def done() -> None:
            self._refresh_findings_panel()
            self.render_current()
            self._set_status(
                f"OCR complete. {len(self.findings)} findings "
                f"({sum(1 for f in self.findings if f.selected)} selected)."
            )
            self.progress.set(0)

        self._run_async(work, done)

    # -------------------------------------------------------------- findings
    def _set_findings_scope(self, scope: str) -> None:
        self._findings_scope = scope if scope in {"page", "all"} else "page"
        self._refresh_findings_panel()

    def _refresh_findings_panel(self) -> None:
        for child in self.findings_list.winfo_children():
            child.destroy()
        self._finding_vars.clear()
        self._finding_row_indices.clear()

        if not self.findings:
            if hasattr(self, "findings_meta"):
                self.findings_meta.configure(text="")
            ctk.CTkLabel(
                self.findings_list,
                text="No findings yet.",
                text_color="#888",
            ).pack(anchor="w", padx=4, pady=8)
            return

        if self._findings_scope == "page":
            pairs = [
                (i, f)
                for i, f in enumerate(self.findings)
                if f.page_index == self.current_page
            ]
            scope_note = f"page {self.current_page + 1}"
        else:
            pairs = list(enumerate(self.findings))
            scope_note = "all pages"

        total_shown_source = len(pairs)
        capped = False
        if self._findings_scope == "all" and len(pairs) > GUI_FINDINGS_LIST_CAP:
            pairs = pairs[:GUI_FINDINGS_LIST_CAP]
            capped = True

        if hasattr(self, "findings_meta"):
            cap_msg = f" · showing first {GUI_FINDINGS_LIST_CAP}" if capped else ""
            self.findings_meta.configure(
                text=f"{len(self.findings)} total · list: {scope_note} "
                f"({total_shown_source}{cap_msg})"
            )

        if not pairs:
            ctk.CTkLabel(
                self.findings_list,
                text="No findings on this page.",
                text_color="#888",
            ).pack(anchor="w", padx=4, pady=8)
            return

        for idx, finding in pairs:
            var = ctk.BooleanVar(value=finding.selected)
            self._finding_vars.append(var)
            self._finding_row_indices.append(idx)

            row = ctk.CTkFrame(self.findings_list, fg_color=("gray90", "gray20"))
            row.pack(fill="x", pady=2, padx=2)

            def make_toggle(i: int, v: ctk.BooleanVar) -> Callable[[], None]:
                def toggle() -> None:
                    self.findings[i].selected = bool(v.get())
                    self.render_current()

                return toggle

            cb = ctk.CTkCheckBox(
                row,
                text="",
                variable=var,
                width=24,
                command=make_toggle(idx, var),
            )
            cb.pack(side="left", padx=(6, 2), pady=6)

            preview = finding.text.replace("\n", " ")
            if len(preview) > 48:
                preview = preview[:45] + "…"
            label = f"p{finding.page_index + 1}  [{finding.label}]  {preview}"
            if not finding.rects:
                label += "  (no coords)"

            def make_jump(page: int) -> Callable[[], None]:
                def jump() -> None:
                    self.current_page = page
                    self.render_current()
                    if self._findings_scope == "page":
                        self._refresh_findings_panel()

                return jump

            btn = ctk.CTkButton(
                row,
                text=label,
                anchor="w",
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray80", "gray30"),
                command=make_jump(finding.page_index),
            )
            btn.pack(side="left", fill="x", expand=True, padx=4, pady=4)

    def _select_all(self, value: bool) -> None:
        # Scope-aware: only toggle visible rows' findings when page-scoped
        if self._findings_scope == "page" and self._finding_row_indices:
            for i in self._finding_row_indices:
                self.findings[i].selected = value
        else:
            for f in self.findings:
                f.selected = value
        self._refresh_findings_panel()
        self.render_current()

    # -------------------------------------------------------------- manual boxes
    def toggle_manual(self) -> None:
        self._manual_mode = not self._manual_mode
        if self._manual_mode:
            self.manual_btn.configure(text="Manual Box: On", fg_color="#3d5a80")
            self._set_status("Manual mode: drag on the page to draw a redaction box.")
        else:
            self.manual_btn.configure(text="Manual Box: Off", fg_color="#444")
            self._set_status("Manual mode off.")

    def _canvas_to_pdf(self, x: float, y: float) -> tuple[float, float]:
        # Account for scroll offset
        cx = self.canvas.canvasx(x)
        cy = self.canvas.canvasy(y)
        return cx / self.zoom, cy / self.zoom

    def _on_canvas_press(self, event) -> None:  # noqa: ANN001
        if not self._manual_mode or not self.doc:
            return
        self._draw_start = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        if self._draw_rect_id is not None:
            self.canvas.delete(self._draw_rect_id)
        self._draw_rect_id = self.canvas.create_rectangle(
            *self._draw_start, *self._draw_start, outline="#ff5555", width=2, dash=(4, 2)
        )

    def _on_canvas_drag(self, event) -> None:  # noqa: ANN001
        if not self._manual_mode or self._draw_start is None or self._draw_rect_id is None:
            return
        x1, y1 = self._draw_start
        x2, y2 = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self.canvas.coords(self._draw_rect_id, x1, y1, x2, y2)

    def _on_canvas_release(self, event) -> None:  # noqa: ANN001
        if not self._manual_mode or self._draw_start is None or not self.doc:
            return
        x1, y1 = self._draw_start
        x2, y2 = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self._draw_start = None
        if self._draw_rect_id is not None:
            self.canvas.delete(self._draw_rect_id)
            self._draw_rect_id = None

        if abs(x2 - x1) < 4 or abs(y2 - y1) < 4:
            return

        px0, py0 = min(x1, x2) / self.zoom, min(y1, y2) / self.zoom
        px1, py1 = max(x1, x2) / self.zoom, max(y1, y2) / self.zoom
        rect = fitz.Rect(px0, py0, px1, py1)
        finding = Finding(
            page_index=self.current_page,
            label="Manual",
            rule_name="manual",
            text="(manual redaction)",
            rects=[rect],
            selected=True,
            manual=True,
        )
        self.findings.append(finding)
        self._refresh_findings_panel()
        self.render_current()
        self._set_status(f"Added manual redaction on page {self.current_page + 1}.")

    # -------------------------------------------------------------- export
    def export_redacted(self) -> None:
        if not self.doc or not self.source_path:
            self._set_status("Open a PDF first.")
            return
        selected = [f for f in self.findings if f.selected and f.rects]
        if not selected:
            messagebox.showinfo(
                "Nothing to redact",
                "No selected findings with coordinates.\n"
                "Run Scan / OCR, enable findings, or draw manual boxes.",
            )
            return

        default_name = self.source_path.stem + "_redacted.pdf"
        out = filedialog.asksaveasfilename(
            title="Save redacted PDF",
            defaultextension=".pdf",
            initialfile=default_name,
            filetypes=[("PDF files", "*.pdf")],
        )
        if not out:
            return

        def progress(cur: int, total: int, msg: str) -> None:
            self.root.after(0, lambda: self.progress.set(cur / max(total, 1)))
            self.root.after(0, lambda: self._set_status(msg))

        def work() -> None:
            self.root.after(0, lambda: self._set_status("Applying redactions…"))
            # Work on a fresh open so in-memory preview stays intact
            apply_redactions(
                self.source_path,
                self.findings,
                out,
                only_selected=True,
                progress_callback=progress,
                large_document=self._large_doc,
            )

        def done() -> None:
            self.progress.set(0)
            self._set_status(f"Saved redacted PDF → {out}")
            messagebox.showinfo("Export complete", f"Redacted PDF saved:\n{out}")

        self._run_async(work, done)

    def run(self) -> None:
        self.root.mainloop()
        if self.doc:
            self.doc.close()


def main(argv: list[str] | None = None) -> None:
    """GUI entry. For batch/large PDFs use ``pdf-redact-batch``."""
    # Allow `pdf-redact --help` without requiring a display
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] in {"-h", "--help"}:
        print(
            "pdf-redact — interactive PHI/PII PDF redaction GUI\n\n"
            "  pdf-redact              Start the GUI\n"
            "  pdf-redact-batch …      Batch mode for large PDFs (see --help)\n",
            file=sys.stdout,
        )
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # On Linux, ensure Tk can find display; fail gracefully
    try:
        app = PdfRedactApp()
    except tk.TclError as exc:
        print(
            "Could not start GUI (is a display available?)\n"
            f"{exc}\n"
            "On headless systems use X11 forwarding or a desktop session.\n"
            "For large PDFs without a GUI: pdf-redact-batch --help",
            file=sys.stderr,
        )
        sys.exit(1)
    app.run()


if __name__ == "__main__":
    main()
