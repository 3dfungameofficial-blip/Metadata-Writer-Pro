# -*- coding: utf-8 -*-
"""Filename + media-detection tests."""
from pathlib import Path

from metadata_writer_pro.app.core.media_manager import build_index, classify, is_supported
from metadata_writer_pro.app.utils.filenames import seo_target_path, slugify_title, unique_path_in_dir


def test_slug_basic():
    assert slugify_title("My Amazing Video!") == "my-amazing-video!" or slugify_title("My Amazing Video") == "my-amazing-video"


def test_slug_removes_windows_illegal_chars():
    assert slugify_title('a<b>c:d"e/f\\g|h?i*j') == "abcdefghij"


def test_slug_preserves_bengali():
    assert slugify_title("বাংলাদেশ রাজনীতি") == "বাংলাদেশ-রাজনীতি"


def test_slug_empty_title():
    assert slugify_title("   ") == ""
    assert slugify_title("") == ""


def test_unique_path_dedup(tmp_path):
    (tmp_path / "my-video.mp4").write_bytes(b"x")
    p = unique_path_in_dir(tmp_path, "my-video", ".mp4")
    assert p.name == "my-video-1.mp4"


def test_seo_target_none_when_same(tmp_path):
    src = tmp_path / "my-video.mp4"
    src.write_bytes(b"x")
    assert seo_target_path(src, "My Video") is None


def test_media_classification():
    assert classify(Path("a.JPG")) == "image"
    assert classify(Path("b.jpeg")) == "image"
    assert classify(Path("c.PNG")) == "image"
    assert classify(Path("d.mp4")) == "video"
    assert classify(Path("e.MOV")) == "video"
    assert classify(Path("f.avi")) is None
    assert classify(Path("g.MP4")) == "video"


def test_build_index_case_insensitive(tmp_path):
    (tmp_path / "Video01.MP4").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("x")
    index = build_index(tmp_path)
    assert "video01.mp4" in index
    assert "notes.txt" not in index
    assert is_supported(Path("x.MoV"))
