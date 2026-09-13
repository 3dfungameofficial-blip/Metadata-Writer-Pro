"""Failure-case tests: missing files, bad CSV, unfriendly-error mapping."""
from pathlib import Path

from metadata_writer_pro.app.core.csv_manager import load_csv
from metadata_writer_pro.app.metadata.base import build_default_registry
from metadata_writer_pro.app.utils.validation import friendly_error


def test_load_csv_missing_file(tmp_path):
    v = load_csv(tmp_path / "nope.csv")
    assert not v.ok


def test_processor_missing_file_raises(tmp_path):
    reg = build_default_registry()
    proc = reg.for_file(Path("ghost.mp4"))
    assert proc is not None
    try:
        from metadata_writer_pro.app.core.csv_manager import MetadataModel
        proc.write_metadata(tmp_path / "ghost.mp4", MetadataModel(title="x"))
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("expected FileNotFoundError")


def test_friendly_error_locked_file():
    msg = friendly_error(PermissionError(13, "denied"), "video01.mp4")
    assert "another" in msg.lower() or "locked" in msg.lower() or "open" in msg.lower()


def test_friendly_error_no_traceback():
    msg = friendly_error(KeyError("'filename'"))
    assert "Traceback" not in msg
