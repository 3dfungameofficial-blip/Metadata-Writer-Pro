# -*- coding: utf-8 -*-
"""CSV manager tests: headers, BOM, unicode, duplicates, empty rows."""
from pathlib import Path

from metadata_writer_pro.app.core.csv_manager import load_csv


def _write(tmp_path: Path, name: str, text: str, encoding: str = "utf-8-sig") -> Path:
    p = tmp_path / name
    p.write_text(text, encoding=encoding)
    return p


def test_valid_csv_case_insensitive_and_whitespace(tmp_path):
    p = _write(tmp_path, "m.csv",
               " Filename , TITLE , Description , Keywords \n"
               "video01.mp4, My Video , A desc , a, b , c\n")
    v = load_csv(p)
    assert v.ok and v.total_rows == 1
    assert v.rows[0].filename == "video01.mp4"
    assert v.rows[0].metadata.keywords == ["a", "b", "c"]


def test_missing_filename_column(tmp_path):
    p = _write(tmp_path, "m.csv", "title,description\nhello,world\n")
    v = load_csv(p)
    assert not v.ok
    assert any("filename" in e.lower() for e in v.errors)


def test_bengali_unicode_and_bom(tmp_path):
    p = _write(tmp_path, "m.csv",
               "filename,title,description,keywords\n"
               "img01.jpg,বাংলাদেশ,রাজনীতি ডকুমেন্টারি,\"বাংলাদেশ, রাজনীতি, মিডিয়া\"\n")
    v = load_csv(p)
    assert v.ok
    assert v.rows[0].metadata.title == "বাংলাদেশ"
    assert "রাজনীতি" in v.rows[0].metadata.keywords


def test_empty_rows_skipped_and_description_fallback(tmp_path):
    p = _write(tmp_path, "m.csv", "filename,title,description,keywords\n, , ,\nimg.jpg,Hello,,\n")
    v = load_csv(p)
    assert v.ok and v.total_rows == 1
    assert v.rows[0].metadata.description == "Hello"


def test_duplicate_filenames_rejected(tmp_path):
    p = _write(tmp_path, "m.csv", "filename,title\nA.mp4,x\nA.mp4,y\n")
    v = load_csv(p)
    assert not v.ok
    assert any("uplicate" in e for e in v.errors)
