"""Batch processing engine: background thread, pause/cancel, per-file results."""
from __future__ import annotations

import csv
import datetime as _dt
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from metadata_writer_pro.app import APP_VERSION
from metadata_writer_pro.app.core.csv_manager import CsvRow, MetadataModel
from metadata_writer_pro.app.core.media_manager import build_index
from metadata_writer_pro.app.metadata.base import ProcessorRegistry, build_default_registry
from metadata_writer_pro.app.services import backup as backup_svc
from metadata_writer_pro.app.services.logger import get_logger, start_processing_log
from metadata_writer_pro.app.utils import filenames as fn
from metadata_writer_pro.app.utils.validation import friendly_error

log = get_logger("processing")

# Temp files left behind by a crashed run share this infix and are swept at batch start.
STALE_TMP_INFIX = "_mwptmp_"


def sweep_stale_temp_files(folder: Path) -> int:
    """Delete orphaned video temp files from crashed runs. Returns count removed."""
    removed = 0
    try:
        import time as _time

        now = _time.time()
        for entry in folder.iterdir():
            if entry.is_file() and STALE_TMP_INFIX in entry.name:
                try:
                    if now - entry.stat().st_mtime > 3600:
                        entry.unlink()
                        removed += 1
                except OSError:
                    pass
    except OSError:
        pass
    return removed


@dataclass
class FileResult:
    filename: str
    final_name: str
    status: str  # success | failed | skipped
    detail: str = ""
    operation: str = "metadata"
    timestamp: str = field(default_factory=lambda: _dt.datetime.now().isoformat(timespec="seconds"))


@dataclass
class ProgressState:
    total: int = 0
    done: int = 0
    current_file: str = ""
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    started_at: float = 0.0

    @property
    def percent(self) -> float:
        return (self.done / self.total * 100.0) if self.total else 0.0

    @property
    def elapsed(self) -> float:
        return time.time() - self.started_at if self.started_at else 0.0


OnEvent = Callable[[str, object], None]


class ProcessingEngine:
    """Runs the CSV batch on a worker thread; UI stays responsive via callback."""

    def __init__(self, registry: ProcessorRegistry | None = None) -> None:
        self.registry = registry or build_default_registry()
        self._cancel = threading.Event()
        self._pause = threading.Event()
        self._pause.set()  # set == running
        self._thread: threading.Thread | None = None
        self.results: list[FileResult] = []
        self.state = ProgressState()

    # -- control ---------------------------------------------------------
    def cancel(self) -> None:
        self._cancel.set()
        self._pause.set()

    def pause(self) -> None:
        self._pause.clear()

    def resume(self) -> None:
        self._pause.set()

    @property
    def paused(self) -> bool:
        return not self._pause.is_set()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- run -------------------------------------------------------------
    def run_async(self, rows: list[CsvRow], folder: Path, options: dict, on_event: OnEvent) -> threading.Thread:
        self._cancel.clear()
        self._pause.set()
        self.results = []
        self._thread = threading.Thread(
            target=self._work, args=(rows, Path(folder), dict(options), on_event), daemon=True
        )
        self._thread.start()
        return self._thread

    def _work(self, rows: list[CsvRow], folder: Path, options: dict, emit: OnEvent) -> None:
        log_path = start_processing_log()
        emit("logfile", log_path)
        log.info("Metadata Writer Pro v%s batch started: %d rows, folder=%s",
                 APP_VERSION, len(rows), folder)
        swept = sweep_stale_temp_files(Path(folder))
        if swept:
            emit("log", f"Cleaned up {swept} orphaned temp file(s) from a previous run.")
        st = self.state = ProgressState(total=len(rows), started_at=time.time())
        rename_enabled = bool(options.get("rename_enabled", True))
        create_backup = bool(options.get("create_backup", False))
        continue_on_error = bool(options.get("continue_on_error", True))
        overwrite = bool(options.get("overwrite", True))
        write_fields = options.get("write_fields") or ["title", "description", "keywords"]

        index = build_index(folder)
        emit("started", st)

        for i, row in enumerate(rows, start=1):
            if self._cancel.is_set():
                self.results.append(FileResult(row.filename, row.filename, "skipped", "Cancelled by user"))
                emit("log", "Processing cancelled by user.")
                break
            self._pause.wait()  # safe pause point: between files only
            if self._cancel.is_set():
                break

            st.current_file = row.filename
            st.done = i - 1
            emit("progress", st)

            media = index.get(row.filename.strip().lower())
            if media is None:
                msg = f"'{row.filename}' not found in folder or has an unsupported extension."
                self.results.append(FileResult(row.filename, row.filename, "failed", msg, "match"))
                st.failed += 1
                emit("log", f"✕ {msg}")
                st.done = i
                emit("progress", st)
                if not continue_on_error:
                    break
                continue

            processor = self.registry.for_file(media.path)
            if processor is None:
                msg = f"'{row.filename}': unsupported media type."
                self.results.append(FileResult(row.filename, row.filename, "failed", msg, "match"))
                st.failed += 1
                emit("log", f"✕ {msg}")
                st.done = i
                emit("progress", st)
                continue

            try:
                if create_backup:
                    made = backup_svc.create_backup(media.path)
                    if made is None:
                        emit("log", f"⚠ Backup failed for '{media.path.name}'; continuing without backup.")
                active = row.metadata.active_fields(write_fields)
                model = MetadataModel(
                    title=active.get("title", ""),
                    description=active.get("description", ""),
                    keywords=active.get("keywords", []),
                    author=active.get("author", ""),
                    copyright=active.get("copyright", ""),
                    rating=row.metadata.rating,
                )
                processor.write_metadata(media.path, model, overwrite=overwrite)
                if not processor.verify(media.path, model):
                    detail = (f"'{row.filename}': metadata was written but read-back "
                              "verification failed. The file is intact; check the result manually.")
                    self.results.append(FileResult(row.filename, media.path.name, "failed", detail, "verify"))
                    st.failed += 1
                    emit("log", f"✕ {detail}")
                    log.warning("VERIFY-FAIL %s", row.filename)
                    st.done = i
                    emit("progress", st)
                    if not continue_on_error:
                        break
                    continue

                final_name = media.path.name
                current_path = media.path
                rename_failed: str | None = None
                if rename_enabled and row.metadata.title:
                    try:
                        target = fn.seo_target_path(current_path, row.metadata.title)
                        if target is not None:
                            current_path.rename(target)
                            final_name = target.name
                            # keep index consistent for subsequent duplicate titles
                            index.pop(row.filename.strip().lower(), None)
                            index[final_name.lower()] = type(media)(path=target, kind=media.kind)
                    except Exception as exc:
                        rename_failed = friendly_error(exc, row.filename)

                notes: list[str] = []
                unsupported = getattr(processor, "unsupported_notes", None)
                if callable(unsupported):
                    try:
                        notes.extend(unsupported(media.path, model))
                    except Exception:
                        pass
                if media.path.suffix.lower() == ".png":
                    notes.append("Windows Explorer may not show PNG metadata, but it was written.")
                note = (" — " + " ".join(notes)) if notes else ""
                if rename_failed is not None:
                    detail = f"Metadata was applied to '{row.filename}', but rename failed: {rename_failed}"
                    self.results.append(FileResult(row.filename, media.path.name, "failed", detail, "rename"))
                    st.failed += 1
                    emit("log", f"✕ {detail}")
                    log.warning("RENAME-FAIL %s: %s", row.filename, rename_failed)
                else:
                    self.results.append(FileResult(row.filename, final_name, "success",
                                                   f"Metadata applied{note}", "metadata+rename" if final_name != row.filename else "metadata"))
                    st.successful += 1
                    arrow = f"'{row.filename}' → '{final_name}'" if final_name != row.filename else f"'{row.filename}'"
                    emit("log", f"✓ {arrow}{note}")
                    log.info("OK %s -> %s", row.filename, final_name)
            except Exception as exc:  # per-file isolation: never abort the batch silently
                detail = friendly_error(exc, row.filename)
                log.exception("FAILED %s", row.filename)
                self.results.append(FileResult(row.filename, row.filename, "failed", detail, "metadata"))
                st.failed += 1
                emit("log", f"✕ {detail}")
                if not continue_on_error:
                    st.done = i
                    emit("progress", st)
                    break
            st.done = i
            emit("progress", st)

        emit("finished", {"results": list(self.results), "state": st, "logfile": str(log_path)})

    # -- report ----------------------------------------------------------
    def export_report(self, dest: Path, fmt: str = "csv") -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "json":
            import json

            with open(dest, "w", encoding="utf-8") as fh:
                json.dump([r.__dict__ for r in self.results], fh, ensure_ascii=False, indent=2)
        else:
            with open(dest, "w", encoding="utf-8-sig", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["filename", "final_name", "status", "detail", "operation", "timestamp"])
                for r in self.results:
                    w.writerow([r.filename, r.final_name, r.status, r.detail, r.operation, r.timestamp])
        return dest
