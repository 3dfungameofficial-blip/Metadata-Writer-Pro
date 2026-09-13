# -*- coding: utf-8 -*-
"""Production QA regression tests: filename safety, settings, updater, engine."""
import hashlib
import json
import threading
import time
from pathlib import Path
from unittest import mock

import pytest

from metadata_writer_pro.app.core.csv_manager import MetadataModel, load_csv
from metadata_writer_pro.app.core.processing_engine import ProcessingEngine
from metadata_writer_pro.app.metadata.base import MetadataProcessor, ProcessorRegistry
from metadata_writer_pro.app.services import settings as settings_mod
from metadata_writer_pro.app.services import updater as updater_mod
from metadata_writer_pro.app.services.logger import start_processing_log
from metadata_writer_pro.app.ui.main_window import excess_line_count
from metadata_writer_pro.app.utils import paths as paths_mod
from metadata_writer_pro.app.utils.filenames import slugify_title


# -- filename safety -----------------------------------------------------
@pytest.mark.parametrize("title,expected", [
    ("CON", "_con"),
    ("prn", "_prn"),
    ("COM1", "_com1"),
    ("lpt9", "_lpt9"),
    ("aux", "_aux"),
    ("NUL", "_nul"),
    ("normal title", "normal-title"),
    ("trailing. ", "trailing"),
    ("বাংলাদেশ রাজনীতি", "বাংলাদেশ-রাজনীতি"),
    ("", ""),
])
def test_slug_reserved_and_safe(title, expected):
    assert slugify_title(title) == expected


def test_slug_long_title_capped():
    assert len(slugify_title("a" * 500)) <= 150


def test_slug_emoji_survives():
    assert "🎬" in slugify_title("My 🎬 Video")


# -- paths ----------------------------------------------------------------
def test_base_dir_resolves_project_root():
    base = paths_mod.base_dir()
    assert (base / "pyproject.toml").is_file()
    assert paths_mod.resource_path("assets/icon.ico").is_file()


# -- settings --------------------------------------------------------------
def test_corrupt_settings_backed_up_and_defaults_used(tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "user_data_dir", lambda: tmp_path)
    bad = tmp_path / "settings.json"
    bad.write_text("{not valid json", encoding="utf-8")
    s = settings_mod.load_settings()
    assert s.get("theme") == settings_mod.DEFAULTS["theme"]
    backups = list(tmp_path.glob("settings.corrupt.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{not valid json"


def test_unknown_future_fields_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(paths_mod, "user_data_dir", lambda: tmp_path)
    (tmp_path / "settings.json").write_text(
        json.dumps({"theme": "dark", "future_flag_xyz": True}), encoding="utf-8")
    s = settings_mod.load_settings()
    assert s.get("theme") == "dark"
    assert s.get("future_flag_xyz") is True
    assert s.get("settings_version") == settings_mod.DEFAULTS["settings_version"]


# -- updater ----------------------------------------------------------------
def test_update_endpoint_configured_to_official_repo():
    assert updater_mod.updates_configured() is True
    assert updater_mod.UPDATE_CHECK_URL == (
        "https://api.github.com/repos/3dfungameofficial-blip/Metadata-Writer-Pro/releases/latest")
    with pytest.raises((updater_mod.UpdateNotConfigured, updater_mod.UpdateError)):
        updater_mod.check_for_updates(url="http://insecure.example/updates")


def test_install_refused_without_hash(tmp_path):
    fake = tmp_path / "Setup.exe"
    fake.write_bytes(b"x")
    with pytest.raises(Exception, match="[Hh]ash|verif"):
        updater_mod.install_artifact(fake, "")


def test_sha256_mismatch_refuses(tmp_path):
    fake = tmp_path / "Setup.exe"
    fake.write_bytes(b"abc")
    with pytest.raises(Exception, match="[Cc]hecksum|verification"):
        updater_mod.verify_sha256(fake, "0" * 64)


# -- logging -----------------------------------------------------------------
def test_processing_log_handlers_do_not_accumulate(tmp_path, monkeypatch):
    import logging
    monkeypatch.setattr(paths_mod, "logs_dir", lambda: tmp_path)
    start_processing_log()
    start_processing_log()
    handlers = [h for h in logging.getLogger("processing").handlers
                if isinstance(h, logging.FileHandler)]
    assert len(handlers) == 1


def test_excess_line_count():
    assert excess_line_count(100) == 0
    assert excess_line_count(2500) == 500


# -- engine with stub processors ----------------------------------------------
class StubProcessor(MetadataProcessor):
    name = "stub"

    def __init__(self, fail_on=(), delay=0.0):
        self.fail_on = set(fail_on)
        self.delay = delay
        self.written = []

    def supports(self, file_path):
        return Path(file_path).suffix.lower() == ".jpg"

    def write_metadata(self, file_path, metadata, *, overwrite=True):
        if self.delay:
            time.sleep(self.delay)
        if Path(file_path).name in self.fail_on:
            raise PermissionError(13, "denied")
        self.written.append(Path(file_path).name)


def _rows(names):
    from metadata_writer_pro.app.core.csv_manager import CsvRow
    return [CsvRow(lineno=i + 2, filename=n, metadata=MetadataModel(title=f"Title {i}"))
            for i, n in enumerate(names)]


def test_engine_continues_after_locked_file_and_reports(tmp_path):
    for n in ("a.jpg", "b.jpg", "c.jpg"):
        (tmp_path / n).write_bytes(b"x")
    stub = StubProcessor(fail_on={"b.jpg"})
    reg = ProcessorRegistry()
    reg.register(stub)
    eng = ProcessingEngine(registry=reg)
    events = []
    t = eng.run_async(_rows(["a.jpg", "b.jpg", "c.jpg"]), tmp_path,
                      {"rename_enabled": False}, lambda k, p: events.append((k, p)))
    t.join(timeout=60)
    by_name = {r.filename: r for r in eng.results}
    assert by_name["a.jpg"].status == "success"
    assert by_name["b.jpg"].status == "failed"
    assert "another" in by_name["b.jpg"].detail.lower() or "locked" in by_name["b.jpg"].detail.lower() \
        or "open" in by_name["b.jpg"].detail.lower()
    assert by_name["c.jpg"].status == "success"
    kinds = {k for k, _ in events}
    assert {"started", "progress", "finished"} <= kinds


def test_engine_rename_failure_reported_accurately(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    stub = StubProcessor()
    reg = ProcessorRegistry()
    reg.register(stub)
    eng = ProcessingEngine(registry=reg)
    with mock.patch("metadata_writer_pro.app.core.processing_engine.fn.seo_target_path",
                    return_value=tmp_path / "no-such-dir" / "x.jpg"):
        events = []
        t = eng.run_async(_rows(["a.jpg"]), tmp_path,
                          {"rename_enabled": True}, lambda k, p: events.append((k, p)))
        t.join(timeout=60)
    assert eng.results[0].status == "failed"
    assert eng.results[0].operation == "rename"
    assert "Metadata was applied" in eng.results[0].detail
    assert (tmp_path / "a.jpg").is_file()  # original intact


def test_engine_pause_resume_cancel(tmp_path):
    names = [f"f{i:03d}.jpg" for i in range(12)]
    for n in names:
        (tmp_path / n).write_bytes(b"x")
    stub = StubProcessor(delay=0.05)
    reg = ProcessorRegistry()
    reg.register(stub)
    eng = ProcessingEngine(registry=reg)
    events = []
    t = eng.run_async(_rows(names), tmp_path, {"rename_enabled": False},
                      lambda k, p: events.append((k, p)))
    time.sleep(0.15)
    eng.pause()
    assert eng.paused
    paused_count = len(stub.written)
    time.sleep(0.2)
    # No file is touched halfway: written count may grow by at most the in-flight file.
    assert len(stub.written) <= paused_count + 1
    eng.resume()
    time.sleep(0.1)
    eng.cancel()
    t.join(timeout=60)
    assert not eng.running
    statuses = {r.status for r in eng.results}
    assert "success" in statuses  # completed files stay intact
    assert "skipped" in statuses or len(eng.results) == len(names)


def test_large_batch_stub_performance(tmp_path):
    names = [f"img{i:04d}.jpg" for i in range(300)]
    for n in names:
        (tmp_path / n).write_bytes(b"x")
    stub = StubProcessor()
    reg = ProcessorRegistry()
    reg.register(stub)
    eng = ProcessingEngine(registry=reg)
    events = []
    start = time.time()
    t = eng.run_async(_rows(names), tmp_path, {"rename_enabled": False},
                      lambda k, p: events.append((k, p)))
    t.join(timeout=120)
    elapsed = time.time() - start
    assert len(eng.results) == 300
    assert all(r.status == "success" for r in eng.results)
    assert elapsed < 60
    done_marks = [p.done for k, p in events if k == "progress"]
    assert done_marks == sorted(done_marks)  # monotonic progress


def test_backup_is_byte_identical(tmp_path, monkeypatch):
    from metadata_writer_pro.app.services import backup as backup_mod
    monkeypatch.setattr(paths_mod, "backup_dir", lambda: tmp_path / "bk")
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"\x00\x01\x02" * 1000)
    digest_before = hashlib.sha256(src.read_bytes()).hexdigest()
    made = backup_mod.create_backup(src)
    assert made is not None and made.is_file()
    assert hashlib.sha256(made.read_bytes()).hexdigest() == digest_before


# -- CSV edges ---------------------------------------------------------------
def _csv(tmp_path, name, text, encoding="utf-8-sig"):
    p = tmp_path / name
    p.write_text(text, encoding=encoding)
    return p


def test_csv_uppercase_headers_and_quotes(tmp_path):
    p = _csv(tmp_path, "u.csv",
             'FILENAME,TITLE,DESCRIPTION,KEYWORDS\n'
             'a.mp4,"Quoted, Title","Say ""hi""","x, y"\n')
    v = load_csv(p)
    assert v.ok
    assert v.rows[0].metadata.title == "Quoted, Title"
    assert v.rows[0].metadata.description == 'Say "hi"'
    assert v.rows[0].metadata.keywords == ["x", "y"]


def test_csv_empty_title_description_keywords(tmp_path):
    p = _csv(tmp_path, "e.csv", "filename,title,description,keywords\na.mp4,,,\n")
    v = load_csv(p)
    assert v.ok and v.total_rows == 1
    assert v.rows[0].metadata.title == ""
    assert v.rows[0].metadata.description == ""
    assert v.rows[0].metadata.keywords == []


def test_csv_utf8_no_bom_and_long_fields(tmp_path):
    long_title = "T" * 2000
    p = _csv(tmp_path, "l.csv",
             f"filename,title,description,keywords\na.mp4,{long_title},desc,k\n",
             encoding="utf-8")
    v = load_csv(p)
    assert v.ok and v.rows[0].metadata.title == long_title


def test_csv_extra_columns_tolerated(tmp_path):
    p = _csv(tmp_path, "x.csv", "filename,title,author,rating\na.mp4,Hello,Jane,5\n")
    v = load_csv(p)
    assert v.ok
    assert v.rows[0].metadata.author == "Jane"
