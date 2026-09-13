"""Modern desktop UI (ttkbootstrap): sidebar nav + Dashboard/Process/History/Settings/About.

Framework choice: ttkbootstrap (Tkinter) over PySide6 — MIT-licensed,
~5MB bundle impact vs ~200MB for Qt, no LGPL distribution obligations,
trivial PyInstaller packaging, and fully sufficient for this workflow UI.
The design follows modern product principles (spacious cards, restrained
accent, dark/light themes) without copying any brand.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import ttkbootstrap as ttk
from ttkbootstrap.constants import BOTH, END, EW, WORD, X

from metadata_writer_pro.app import APP_NAME, APP_VERSION
from metadata_writer_pro.app.core.csv_manager import CsvValidation, load_csv
from metadata_writer_pro.app.core.media_manager import scan_folder, supported_label
from metadata_writer_pro.app.core.processing_engine import FileResult, ProcessingEngine
from metadata_writer_pro.app.services import updater as updater_svc
from metadata_writer_pro.app.services.logger import get_logger
from metadata_writer_pro.app.services.settings import get_settings, update_and_save
from metadata_writer_pro.app.utils import paths as paths_mod
from metadata_writer_pro.app.utils.validation import csv_error

log = get_logger("ui")

LIGHT_THEME = "litera"
DARK_THEME = "darkly"
ACCENT = "#4f7cff"

# On-screen log keeps the UI responsive on large batches; full history stays in log files.
LOG_MAX_LINES = 2000


def excess_line_count(total_lines: int, maximum: int = LOG_MAX_LINES) -> int:
    """Lines to drop from the top of the visible log (pure helper, unit-tested)."""
    return max(0, total_lines - maximum)


class MainWindow:
    def __init__(self, root: ttk.Window) -> None:
        self.root = root
        self.settings = get_settings()
        self.engine = ProcessingEngine()
        self.events: queue.Queue = queue.Queue()
        self.validation: CsvValidation | None = None
        self.csv_path = ""
        self.folder_path = ""
        self.logfile: Path | None = None
        self.start_time = 0.0
        self.paused = False

        root.title(f"{APP_NAME} v{APP_VERSION}")
        root.geometry("1080x720")
        root.minsize(960, 640)
        try:
            icon = paths_mod.resource_path("assets/icon.ico")
            if icon.is_file():
                root.iconbitmap(str(icon))
        except Exception as exc:
            log.debug("icon load skipped: %s", exc)

        self._build_layout()
        self._apply_theme(self.settings.get("theme", "system"))
        self._show_page("process")
        self._refresh_dashboard()
        self._try_enable_dnd()
        self.root.after(120, self._pump_events)
        # Auto update check (non-blocking, silent on failure)
        if self.settings.get("auto_check_updates", True):
            threading.Thread(target=self._silent_update_check, daemon=True).start()

    # -- layout ----------------------------------------------------------
    def _build_layout(self) -> None:
        self.shell = ttk.Frame(self.root)
        self.shell.pack(fill=BOTH, expand=True)

        # Sidebar
        self.sidebar = ttk.Frame(self.shell, width=200, padding=12)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        ttk.Label(self.sidebar, text="◈", font=("Segoe UI", 22, "bold"), foreground=ACCENT).pack(anchor="w")
        ttk.Label(self.sidebar, text=APP_NAME, font=("Segoe UI", 13, "bold"), wraplength=170).pack(anchor="w")
        ttk.Label(self.sidebar, text=f"v{APP_VERSION}", font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 14))

        self.nav_buttons: dict[str, ttk.Button] = {}
        for key, label in (("dashboard", "Dashboard"), ("process", "Process"),
                           ("history", "History"), ("settings", "Settings"), ("about", "About")):
            b = ttk.Button(self.sidebar, text=label, bootstyle="secondary", command=lambda k=key: self._show_page(k))
            b.pack(fill=X, pady=3)
            self.nav_buttons[key] = b

        ttk.Label(self.sidebar, text=supported_label(), font=("Segoe UI", 8),
                  wraplength=170, justify="left").pack(side="bottom", anchor="w", pady=6)

        # Content
        self.content = ttk.Frame(self.shell, padding=18)
        self.content.pack(side="left", fill=BOTH, expand=True)
        self.pages: dict[str, ttk.Frame] = {}
        for key in ("dashboard", "process", "history", "settings", "about"):
            page = ttk.Frame(self.content)
            self.pages[key] = page
        self._build_dashboard(self.pages["dashboard"])
        self._build_process(self.pages["process"])
        self._build_history(self.pages["history"])
        self._build_settings(self.pages["settings"])
        self._build_about(self.pages["about"])

    def _show_page(self, key: str) -> None:
        for k, page in self.pages.items():
            page.pack_forget()
            self.nav_buttons[k].configure(bootstyle="secondary")
        self.pages[key].pack(fill=BOTH, expand=True)
        self.nav_buttons[key].configure(bootstyle="primary")
        if key == "dashboard":
            self._refresh_dashboard()
        elif key == "history":
            self._refresh_history()

    # -- dashboard -------------------------------------------------------
    def _build_dashboard(self, page: ttk.Frame) -> None:
        ttk.Label(page, text="Dashboard", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(page, text="Overview of your metadata processing.",
                  font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 14))
        cards = ttk.Frame(page)
        cards.pack(fill=X)
        self.dash_vars: dict[str, Any] = {}
        for title in ("Files Processed", "Successful", "Failed", "Last Session"):
            card = ttk.Labelframe(cards, text=f" {title} ", padding=14)
            card.pack(side="left", fill=X, expand=True, padx=(0, 10))
            var = ttk.StringVar(value="—")
            ttk.Label(card, textvariable=var, font=("Segoe UI", 18, "bold")).pack(anchor="w")
            self.dash_vars[title] = var
        info = ttk.Labelframe(page, text=" Application ", padding=14)
        info.pack(fill=X, pady=14)
        self.dash_info = ttk.StringVar()
        ttk.Label(info, textvariable=self.dash_info, font=("Segoe UI", 10), justify="left").pack(anchor="w")
        ttk.Button(page, text="Start Processing →", bootstyle="success",
                   command=lambda: self._show_page("process")).pack(anchor="w")

    def _refresh_dashboard(self) -> None:
        total = ok = fail = 0
        last = "—"
        try:
            hp = paths_mod.history_path()
            if hp.is_file():
                sessions = json.loads(hp.read_text(encoding="utf-8"))
                if isinstance(sessions, list) and sessions:
                    last_s = sessions[-1]
                    total, ok, fail = last_s.get("total", 0), last_s.get("successful", 0), last_s.get("failed", 0)
                    last = last_s.get("finished_at", "—")
                    total_all = sum(s.get("total", 0) for s in sessions)
                    self.dash_vars["Files Processed"].set(str(total_all))
                    self.dash_vars["Successful"].set(str(sum(s.get("successful", 0) for s in sessions)))
                    self.dash_vars["Failed"].set(str(sum(s.get("failed", 0) for s in sessions)))
                    self.dash_vars["Last Session"].set(str(last))
                    self.dash_info.set(f"{APP_NAME} v{APP_VERSION}\nSupported: {supported_label()}\nSessions: {len(sessions)}")
                    return
        except Exception as exc:
            log.debug("dashboard refresh: %s", exc)
        self.dash_vars["Files Processed"].set(str(total))
        self.dash_vars["Successful"].set(str(ok))
        self.dash_vars["Failed"].set(str(fail))
        self.dash_vars["Last Session"].set(str(last))
        self.dash_info.set(f"{APP_NAME} v{APP_VERSION}\nSupported: {supported_label()}")

    # -- process page ----------------------------------------------------
    def _build_process(self, page: ttk.Frame) -> None:
        ttk.Label(page, text="Metadata Writer", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(page, text="1. Select CSV  →  2. Select media folder  →  3. Validate  →  4. Apply",
                  font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 12))

        # CSV card
        csv_card = ttk.Labelframe(page, text=" CSV File ", padding=12)
        csv_card.pack(fill=X, pady=(0, 10))
        self.csv_var = ttk.StringVar(value="No file selected")
        ttk.Entry(csv_card, textvariable=self.csv_var, state="readonly").pack(side="left", fill=X, expand=True)
        ttk.Button(csv_card, text="Browse", bootstyle="outline", command=self._pick_csv).pack(side="left", padx=(8, 0))

        media_card = ttk.Labelframe(page, text=" Media Folder (JPG • JPEG • PNG • MP4 • MOV) ", padding=12)
        media_card.pack(fill=X, pady=(0, 10))
        self.folder_var = ttk.StringVar(value="No folder selected")
        ttk.Entry(media_card, textvariable=self.folder_var, state="readonly").pack(side="left", fill=X, expand=True)
        ttk.Button(media_card, text="Browse", bootstyle="outline", command=self._pick_folder).pack(side="left", padx=(8, 0))

        opts = ttk.Labelframe(page, text=" Options ", padding=12)
        opts.pack(fill=X, pady=(0, 10))
        self.rename_var = ttk.BooleanVar(value=bool(self.settings.get("rename_enabled", True)))
        self.backup_var = ttk.BooleanVar(value=bool(self.settings.get("create_backup", False)))
        ttk.Checkbutton(opts, text="Rename files using title (SEO-friendly)",
                        variable=self.rename_var, bootstyle="success-round-toggle").pack(side="left", padx=(0, 18))
        ttk.Checkbutton(opts, text="Create backup before modifying",
                        variable=self.backup_var, bootstyle="warning-round-toggle").pack(side="left")

        btns = ttk.Frame(page)
        btns.pack(fill=X, pady=(0, 10))
        ttk.Button(btns, text="Validate CSV", bootstyle="info-outline", command=self._validate).pack(side="left")
        self.apply_btn = ttk.Button(btns, text="Apply Metadata", bootstyle="success", command=self._apply)
        self.apply_btn.pack(side="left", padx=8)
        self.pause_btn = ttk.Button(btns, text="Pause", bootstyle="secondary-outline",
                                    command=self._toggle_pause, state="disabled")
        self.pause_btn.pack(side="left")
        self.cancel_btn = ttk.Button(btns, text="Cancel", bootstyle="danger-outline",
                                     command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=8)

        # Validation + preview
        prev = ttk.Labelframe(page, text=" Validation & Preview (first 100 rows) ", padding=10)
        prev.pack(fill=X, pady=(0, 10))
        self.validation_var = ttk.StringVar(value="No CSV validated yet.")
        ttk.Label(prev, textvariable=self.validation_var, font=("Segoe UI", 9), justify="left").pack(anchor="w")
        cols = ("filename", "title", "description", "keywords")
        self.preview = ttk.Treeview(prev, columns=cols, show="headings", height=5)
        for c in cols:
            self.preview.heading(c, text=c.title())
            self.preview.column(c, width=180 if c != "description" else 260)
        self.preview.pack(fill=X, pady=(8, 0))

        # Progress
        prog = ttk.Labelframe(page, text=" Processing ", padding=12)
        prog.pack(fill=BOTH, expand=True)
        self.progress = ttk.Progressbar(prog, mode="determinate", bootstyle="success")
        self.progress.pack(fill=X)
        self.status_var = ttk.StringVar(value="Ready")
        ttk.Label(prog, textvariable=self.status_var, font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 0))
        self.counts_var = ttk.StringVar(value="")
        ttk.Label(prog, textvariable=self.counts_var, font=("Segoe UI", 9, "bold")).pack(anchor="w")

        logrow = ttk.Frame(prog)
        logrow.pack(fill=BOTH, expand=True, pady=(6, 0))
        from ttkbootstrap.scrolled import ScrolledText
        self.log_box = ScrolledText(logrow, height=6, wrap=WORD, font=("Consolas", 9))
        self.log_box.pack(fill=BOTH, expand=True)
        self.log_box.text.config(state="disabled")
        logbtns = ttk.Frame(prog)
        logbtns.pack(fill=X, pady=(8, 0))
        ttk.Button(logbtns, text="Open Log Folder", bootstyle="secondary-outline",
                   command=self._open_logs).pack(side="left")
        ttk.Button(logbtns, text="Export Report", bootstyle="secondary-outline",
                   command=self._export_report).pack(side="left", padx=8)

    # -- history page ----------------------------------------------------
    def _build_history(self, page: ttk.Frame) -> None:
        ttk.Label(page, text="History", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(page, text="Recent processing sessions.", font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 12))
        self.history_box = ttk.Treeview(page, columns=("when", "total", "ok", "fail"), show="headings", height=15)
        for c, w in (("when", 260), ("total", 90), ("ok", 90), ("fail", 90)):
            self.history_box.heading(c, text=c.title())
            self.history_box.column(c, width=w)
        self.history_box.pack(fill=BOTH, expand=True)

    def _refresh_history(self) -> None:
        for item in self.history_box.get_children():
            self.history_box.delete(item)
        try:
            hp = paths_mod.history_path()
            if hp.is_file():
                for s in json.loads(hp.read_text(encoding="utf-8"))[-50:]:
                    self.history_box.insert("", END, values=(
                        s.get("finished_at", "—"), s.get("total", 0),
                        s.get("successful", 0), s.get("failed", 0)))
        except Exception as exc:
            log.debug("history refresh: %s", exc)

    # -- settings page ---------------------------------------------------
    def _build_settings(self, page: ttk.Frame) -> None:
        ttk.Label(page, text="Settings", font=("Segoe UI", 20, "bold")).pack(anchor="w", pady=(0, 12))
        general = ttk.Labelframe(page, text=" General ", padding=12)
        general.pack(fill=X, pady=(0, 10))
        ttk.Label(general, text="Theme:").pack(side="left")
        self.theme_var = ttk.StringVar(value=str(self.settings.get("theme", "system")))
        ttk.Combobox(general, textvariable=self.theme_var, values=["system", "light", "dark"],
                     state="readonly", width=12).pack(side="left", padx=8)
        ttk.Button(general, text="Apply", bootstyle="outline", command=self._save_theme).pack(side="left")

        proc = ttk.Labelframe(page, text=" Processing ", padding=12)
        proc.pack(fill=X, pady=(0, 10))
        self.s_continue = ttk.BooleanVar(value=bool(self.settings.get("continue_on_error", True)))
        self.s_overwrite = ttk.BooleanVar(value=bool(self.settings.get("overwrite_metadata", True)))
        self.s_preserve = ttk.BooleanVar(value=bool(self.settings.get("preserve_existing", True)))
        ttk.Checkbutton(proc, text="Continue on error", variable=self.s_continue).pack(anchor="w")
        ttk.Checkbutton(proc, text="Overwrite existing metadata values", variable=self.s_overwrite).pack(anchor="w")
        ttk.Checkbutton(proc, text="Preserve unrelated metadata", variable=self.s_preserve).pack(anchor="w")

        upd = ttk.Labelframe(page, text=" Updates ", padding=12)
        upd.pack(fill=X, pady=(0, 10))
        self.s_autoupd = ttk.BooleanVar(value=bool(self.settings.get("auto_check_updates", True)))
        ttk.Checkbutton(upd, text="Automatically check for updates", variable=self.s_autoupd).pack(anchor="w")

        tools = ttk.Labelframe(page, text=" External Tools ", padding=12)
        tools.pack(fill=X, pady=(0, 10))
        ff = paths_mod.ffmpeg_exe()
        status = f"FFmpeg: {ff}" if ff else "FFmpeg: NOT FOUND (video support disabled)"
        ttk.Label(tools, text=status, wraplength=640, justify="left").pack(anchor="w")

        ttk.Button(page, text="Save Settings", bootstyle="success", command=self._save_settings).pack(anchor="w")

    # -- about page ------------------------------------------------------
    def _build_about(self, page: ttk.Frame) -> None:
        ttk.Label(page, text=APP_NAME, font=("Segoe UI", 20, "bold")).pack(anchor="w")
        self.version_var = ttk.StringVar(value=f"Version {APP_VERSION}")
        ttk.Label(page, textvariable=self.version_var, font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 4))
        ttk.Label(page, text=f"Supported: {supported_label()}", font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 12))
        self.update_var = ttk.StringVar(value="")
        ttk.Label(page, textvariable=self.update_var, font=("Segoe UI", 10),
                  wraplength=640, justify="left").pack(anchor="w", pady=(0, 10))
        upd_btns = ttk.Frame(page)
        upd_btns.pack(anchor="w")
        ttk.Button(upd_btns, text="Check for Updates", bootstyle="info-outline",
                   command=self._manual_update_check).pack(side="left")
        self.install_update_btn = ttk.Button(upd_btns, text="Download && Install Update",
                                             bootstyle="success-outline",
                                             command=self._download_and_install_update,
                                             state="disabled")
        self.install_update_btn.pack(side="left", padx=8)
        self._pending_release: Any = None

    # -- actions ---------------------------------------------------------
    def _pick_csv(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.csv_path = path
            self.csv_var.set(path)
            self._ui_log(f"CSV selected: {os.path.basename(path)}")

    def _pick_folder(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.folder_path = path
            self.folder_var.set(path)
            media = scan_folder(Path(path))
            self._ui_log(f"Media folder selected: {path} ({len(media)} supported files)")

    def _validate(self) -> None:
        if not self.csv_path or not self.folder_path:
            messagebox.showerror("Missing input", "Please select both a CSV file and a media folder first.")
            return
        v = load_csv(self.csv_path, default_rating=int(self.settings.get("default_rating", 5) or 5))
        self.validation = v
        lines = [("✓ " if ok else "✕ ") + msg for ok, msg in v.checks]
        if v.errors:
            lines += ["", "Issues:"] + [f"• {e}" for e in v.errors]
        # Cross-check against folder
        from metadata_writer_pro.app.core.media_manager import build_index
        index = build_index(Path(self.folder_path))
        missing = [r.filename for r in v.rows if r.filename.strip().lower() not in index]
        if missing:
            lines += ["", f"⚠ {len(missing)} CSV entries have no matching file in the folder."]
            for m in missing[:5]:
                lines.append(f"• {m}")
        self.validation_var.set("\n".join(lines) if lines else "No data.")
        for item in self.preview.get_children():
            self.preview.delete(item)
        for r in v.rows[:100]:
            self.preview.insert("", END, values=(
                r.filename, r.metadata.title[:60],
                r.metadata.description[:80], ", ".join(r.metadata.keywords)[:80]))
        if not v.ok and v.errors:
            messagebox.showwarning("CSV validation", csv_error(v.errors[0],
                                   "Open the preview, fix the CSV, and validate again."))
        else:
            self.status_var.set(f"Validated: {v.total_rows} rows ready.")

    def _apply(self) -> None:
        if self.engine.running:
            return
        if not self.csv_path or not self.folder_path:
            messagebox.showerror("Missing input", "Please select both a CSV file and a media folder first.")
            return
        v = self.validation
        if v is None or not v.rows:
            v = load_csv(self.csv_path)
            self.validation = v
        if not v.rows:
            messagebox.showerror("Nothing to process", csv_error(
                "No valid rows found in the CSV.", "Check the filename column and try again."))
            return
        # persist quick options
        update_and_save(rename_enabled=bool(self.rename_var.get()), create_backup=bool(self.backup_var.get()))
        self.settings = get_settings()
        self.log_box.text.config(state="normal")
        self.log_box.text.delete("1.0", END)
        self.log_box.text.config(state="disabled")
        self.start_time = time.time()
        self.apply_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal", text="Pause")
        self.cancel_btn.configure(state="normal")
        self.paused = False
        self.progress.configure(maximum=len(v.rows), value=0)
        options = {
            "rename_enabled": bool(self.rename_var.get()),
            "create_backup": bool(self.backup_var.get()),
            "continue_on_error": bool(self.settings.get("continue_on_error", True)),
            "overwrite": bool(self.settings.get("overwrite_metadata", True)),
            "write_fields": self.settings.get("write_fields", ["title", "description", "keywords"]),
        }
        self.engine.run_async(v.rows, Path(self.folder_path), options,
                              lambda kind, payload: self.events.put((kind, payload)))

    def _toggle_pause(self) -> None:
        if not self.engine.running:
            return
        if self.paused:
            self.engine.resume()
            self.paused = False
            self.pause_btn.configure(text="Pause")
        else:
            self.engine.pause()
            self.paused = True
            self.pause_btn.configure(text="Resume")

    def _cancel(self) -> None:
        self.engine.cancel()
        # Honest semantics: the worker finishes the current file (its temp
        # file is discarded, the original untouched), then stops.
        self.status_var.set("Cancelling… (finishes the current file, then stops)")

    # -- background event pump (thread-safe UI updates) ------------------
    def _pump_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self._handle_event(kind, payload)
        except queue.Empty:
            pass
        self.root.after(120, self._pump_events)

    def _handle_event(self, kind: str, payload: Any) -> None:
        if kind == "log":
            self._ui_log(str(payload))
        elif kind == "logfile":
            self.logfile = Path(str(payload))
        elif kind == "started":
            self.status_var.set(f"Processing {payload.total} files…")
        elif kind == "progress":
            self.progress.configure(value=payload.done)
            elapsed = payload.elapsed
            self.status_var.set(f"Processing {min(payload.done + 1, payload.total)} of {payload.total} — {payload.current_file}")
            self.counts_var.set(f"✓ {payload.successful} successful    ✕ {payload.failed} failed    ⏱ {elapsed:.0f}s")
        elif kind == "update-progress":
            done, total = payload
            if total:
                pct = done * 100 // total
                self.update_var.set(f"Downloading update… {pct}% ({done // 1024} KB)")
            else:
                self.update_var.set(f"Downloading update… ({done // 1024} KB)")
        elif kind == "update-done":
            self.update_var.set(str(payload))
            self.install_update_btn.configure(state="disabled")
        elif kind == "finished":
            results: list[FileResult] = payload["results"]
            ok = sum(1 for r in results if r.status == "success")
            fail = sum(1 for r in results if r.status == "failed")
            skipped = sum(1 for r in results if r.status == "skipped")
            dur = time.time() - self.start_time if self.start_time else 0
            self.progress.configure(value=len(results))
            self.counts_var.set(f"✓ {ok} successful    ✕ {fail} failed    ⏱ {dur:.0f}s")
            self.status_var.set(f"Complete: {ok} successful, {fail} failed")
            self._ui_log(f"Processing complete — total {len(results)}, successful {ok}, failed {fail}, skipped {skipped} ({dur:.0f}s)")
            self.apply_btn.configure(state="normal")
            self.pause_btn.configure(state="disabled", text="Pause")
            self.cancel_btn.configure(state="disabled")
            self._record_history(len(results), ok, fail)
            self._refresh_dashboard()
            messagebox.showinfo("Processing complete",
                                f"Total: {len(results)}\nSuccessful: {ok}\nFailed: {fail}\nSkipped: {skipped}\nDuration: {dur:.0f}s")

    def _record_history(self, total: int, ok: int, fail: int) -> None:
        try:
            import datetime as dt
            hp = paths_mod.history_path()
            sessions = []
            if hp.is_file():
                sessions = json.loads(hp.read_text(encoding="utf-8") or "[]")
            sessions.append({"finished_at": dt.datetime.now().isoformat(timespec="seconds"),
                             "total": total, "successful": ok, "failed": fail})
            hp.write_text(json.dumps(sessions[-100:], ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            log.debug("history record: %s", exc)

    # -- misc ------------------------------------------------------------
    def _ui_log(self, message: str) -> None:
        box = self.log_box.text
        box.config(state="normal")
        box.insert(END, message + "\n")
        try:
            total = int(box.index("end-1c").split(".")[0])
            drop = excess_line_count(total)
            if drop:
                box.delete("1.0", f"{drop + 1}.0")
        except Exception:
            pass
        box.see(END)
        box.config(state="disabled")

    def _open_logs(self) -> None:
        folder = paths_mod.logs_dir()
        try:
            if os.name == "nt":
                os.startfile(str(folder))  # noqa: S606
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            messagebox.showinfo("Log folder", f"{folder}\n({exc})")

    def _export_report(self) -> None:
        if not self.engine.results:
            messagebox.showinfo("Export report", "No processing results yet. Run Apply Metadata first.")
            return
        dest = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv"), ("JSON", "*.json")])
        if dest:
            fmt = "json" if dest.lower().endswith(".json") else "csv"
            self.engine.export_report(Path(dest), fmt)
            messagebox.showinfo("Export report", f"Report saved to:\n{dest}")

    def _apply_theme(self, mode: str) -> None:
        mode = (mode or "system").lower()
        try:
            import darkdetect  # type: ignore
            is_dark = darkdetect.isDark() if mode == "system" else mode == "dark"
        except Exception:
            is_dark = mode == "dark"
        try:
            self.root.style.theme_use(DARK_THEME if is_dark else LIGHT_THEME)
        except Exception:
            pass

    def _save_theme(self) -> None:
        update_and_save(theme=self.theme_var.get())
        self.settings = get_settings()
        self._apply_theme(self.settings.get("theme", "system"))

    def _save_settings(self) -> None:
        update_and_save(continue_on_error=bool(self.s_continue.get()),
                        overwrite_metadata=bool(self.s_overwrite.get()),
                        preserve_existing=bool(self.s_preserve.get()),
                        auto_check_updates=bool(self.s_autoupd.get()),
                        theme=self.theme_var.get())
        self.settings = get_settings()
        self._apply_theme(self.settings.get("theme", "system"))
        messagebox.showinfo("Settings", "Settings saved.")

    def _silent_update_check(self) -> None:
        try:
            info = updater_svc.check_for_updates()
            if info:
                self.events.put(("log", f"Update available: v{info.version}. See About → Check for Updates."))
        except updater_svc.UpdateNotConfigured:
            pass
        except Exception:
            pass

    def _manual_update_check(self) -> None:
        self.update_var.set("Checking for updates…")
        self.install_update_btn.configure(state="disabled")
        self._pending_release = None
        threading.Thread(target=self._do_update_check, daemon=True).start()

    def _do_update_check(self) -> None:
        try:
            info = updater_svc.check_for_updates()
        except updater_svc.UpdateNotConfigured as exc:
            self.update_var.set(str(exc))
            return
        if info is None:
            self.update_var.set(f"✓ You're using the latest version (v{APP_VERSION}).")
        elif not info.installer_url:
            self.update_var.set(f"Version {info.version} was found, but it has no Windows "
                                f"installer asset. Please download it manually from the releases page.")
        else:
            self._pending_release = info
            notes = (info.notes or "").strip()[:600]
            hash_note = ("SHA-256 verified." if info.sha256
                         else "No trusted checksum published — automatic install will be refused.")
            self.update_var.set(f"Version {info.version} available.\n\nWhat's new:\n{notes}\n\n"
                                f"{hash_note}\n\n"
                                "Updates are installed via versioned Setup.exe releases — never auto-executed code.")
            self.install_update_btn.configure(state="normal")

    def _download_and_install_update(self) -> None:
        info = self._pending_release
        if info is None:
            return
        if not messagebox.askyesno("Install update",
                                    f"Download and install version {info.version}?\n\n"
                                    "The installer is hash-verified before it is launched."):
            return
        self.update_var.set(f"Downloading version {info.version}…")
        self.install_update_btn.configure(state="disabled")
        threading.Thread(target=self._do_install_update, args=(info,), daemon=True).start()

    def _do_install_update(self, info: Any) -> None:
        try:
            import tempfile as _tf
            dest = Path(_tf.gettempdir()) / f"MetadataWriterPro-Setup-{info.version}.exe"

            def _progress(done: int, total: int | None) -> None:
                self.events.put(("update-progress", (done, total)))

            updater_svc.download_update(info, dest, progress=_progress)
            updater_svc.install_artifact(dest, info.sha256)
            self.events.put(("update-done", "Update verified and launched. Follow the installer, then restart the app."))
        except Exception as exc:
            log.warning("Update install failed: %s", exc)
            self.events.put(("update-done", f"Update could not be installed safely:\n{exc}"))

    def _try_enable_dnd(self) -> None:
        """Optional drag-and-drop; stability first — silently skip if unavailable."""
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
            _ = (DND_FILES, TkinterDnD)
        except Exception:
            return  # tkinterdnd2 not installed: browse buttons remain the path
        try:
            self.root.drop_target_register("DND_FILES")  # type: ignore[attr-defined]
            self.root.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore[attr-defined]
        except Exception as exc:
            log.debug("dnd enable skipped: %s", exc)

    def _on_drop(self, event: Any) -> None:  # pragma: no cover - GUI only
        paths = self.root.tk.splitlist(getattr(event, "data", ""))
        for p in paths:
            pl = str(p)
            if pl.lower().endswith(".csv") and os.path.isfile(pl):
                self.csv_path = pl
                self.csv_var.set(pl)
            elif os.path.isdir(pl):
                self.folder_path = pl
                self.folder_var.set(pl)


def run_app() -> None:
    settings = get_settings()
    theme = str(settings.get("theme", "system")).lower()
    initial = LIGHT_THEME
    if theme == "dark":
        initial = DARK_THEME
    else:
        try:
            import darkdetect  # type: ignore
            initial = DARK_THEME if darkdetect.isDark() else LIGHT_THEME
        except Exception:
            initial = LIGHT_THEME
    root = ttk.Window(themename=initial)
    MainWindow(root)
    root.mainloop()
