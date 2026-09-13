# -*- coding: utf-8 -*-
"""Real-media verification: MP4/MOV tag round-trip, stream preservation, PNG read-back.

Skipped automatically when no FFmpeg binary is available.
"""
import re
import subprocess

import pytest

from metadata_writer_pro.app.core.csv_manager import MetadataModel
from metadata_writer_pro.app.utils import paths as paths_mod

needs_ffmpeg = pytest.mark.skipif(paths_mod.ffmpeg_exe() is None, reason="no ffmpeg binary")


def _gen(dest, fmt):
    ff = str(paths_mod.ffmpeg_exe())
    if fmt == "jpg":
        args = [ff, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10",
                "-frames:v", "1", "-q:v", "3", str(dest)]
    else:
        args = [ff, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac",
                "-shortest", str(dest)]
    r = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=120)
    assert r.returncode == 0, r.stderr


def _probe(path):
    ff = str(paths_mod.ffmpeg_exe())
    r = subprocess.run([ff, "-hide_banner", "-i", str(path)],
                       capture_output=True, text=True, errors="replace", timeout=60)
    return r.stderr


@needs_ffmpeg
def test_mp4_full_tag_roundtrip_and_streams_preserved(tmp_path):
    from metadata_writer_pro.app.metadata.video import VideoMetadataProcessor
    p = tmp_path / "t.mp4"
    _gen(p, "mp4")
    before_v = re.search(r"Video:\s*(\w+).*?(\d+x\d+)", _probe(p))
    before_a = re.search(r"Audio:\s*(\w+)", _probe(p))
    assert before_v and before_a
    m = MetadataModel(title="T", description="D", keywords=["a", "b"],
                      author="Au", copyright="C")
    VideoMetadataProcessor().write_metadata(p, m)
    assert VideoMetadataProcessor().verify(p, m)
    after_v = re.search(r"Video:\s*(\w+).*?(\d+x\d+)", _probe(p))
    after_a = re.search(r"Audio:\s*(\w+)", _probe(p))
    assert (after_v.groups(), after_a.group(1)) == (before_v.groups(), before_a.group(1))


@needs_ffmpeg
def test_mov_subset_roundtrip_keywords_unsupported(tmp_path):
    from metadata_writer_pro.app.metadata.video import VideoMetadataProcessor
    p = tmp_path / "t.mov"
    _gen(p, "mov")
    proc = VideoMetadataProcessor()
    m = MetadataModel(title="T", description="D", keywords=["a", "b"], author="Au")
    proc.write_metadata(p, m)
    assert proc.verify(p, m)  # supported subset present
    assert proc.unsupported_notes(p, m)  # ...but keywords honestly flagged


@needs_ffmpeg
def test_empty_title_does_not_erase_existing_mp4_title(tmp_path):
    from metadata_writer_pro.app.metadata.video import VideoMetadataProcessor
    p = tmp_path / "t.mp4"
    _gen(p, "mp4")
    proc = VideoMetadataProcessor()
    proc.write_metadata(p, MetadataModel(title="Keep Me"))
    assert proc.read_tags(p).get("title") == "Keep Me"
    proc.write_metadata(p, MetadataModel(title="", description="New desc"))
    assert proc.read_tags(p).get("title") == "Keep Me"


@needs_ffmpeg
def test_png_metadata_read_back(tmp_path):
    pyexiv2 = pytest.importorskip("pyexiv2")
    from metadata_writer_pro.app.metadata.image import ImageMetadataProcessor
    p = tmp_path / "t.png"
    jpg = tmp_path / "src.jpg"
    _gen(jpg, "jpg")
    ff = str(paths_mod.ffmpeg_exe())
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(jpg),
                    str(p)], check=True, timeout=60)
    m = MetadataModel(title="PNG Title", description="PNG Desc", keywords=["k1"])
    ImageMetadataProcessor().write_metadata(p, m)
    img = pyexiv2.Image(str(p))
    try:
        xmp = img.read_xmp() or {}
    finally:
        img.close()
    title = xmp.get("Xmp.dc.title")
    if isinstance(title, dict):
        title = next(iter(title.values()), "")
    assert title == "PNG Title"
