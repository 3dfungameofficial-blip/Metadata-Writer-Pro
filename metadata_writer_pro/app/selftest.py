"""Headless self-test: exercises the real pipeline without a GUI.

Used for clean-machine verification of the packaged .exe::

    MetadataWriterPro.exe --self-test "C:\\Temp\\mwpro_selftest.json"

Generates JPG (via bundled FFmpeg), MP4 and MOV, writes Bengali + ASCII
metadata through the real processors, verifies read-back, runs the batch
engine (rename + backup + report), and returns a JSON-serialisable report.
Exit code 0 only when every check passes.
"""
from __future__ import annotations

import datetime as _dt
import json
import subprocess
import tempfile
from pathlib import Path

from metadata_writer_pro.app import APP_VERSION


def _ffmpeg() -> Path:
    from metadata_writer_pro.app.utils import paths as paths_mod

    exe = paths_mod.ffmpeg_exe()
    if exe is None:
        raise RuntimeError("self-test: no FFmpeg binary found (bundled or system)")
    return exe


def _gen(ff: Path, dest: Path, fmt: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "jpg":
        args = [str(ff), "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10",
                "-frames:v", "1", "-q:v", "3", str(dest)]
    else:
        args = [str(ff), "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10",
                "-pix_fmt", "yuv420p", "-c:v", "libx264", str(dest)]
    r = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=120)
    if r.returncode != 0 or not dest.is_file():
        raise RuntimeError(f"self-test: could not generate {dest.name}: {(r.stderr or '')[:300]}")


def run_self_test(out_path: str | Path | None = None) -> dict:
    checks: dict[str, bool | str] = {}
    work = Path(tempfile.mkdtemp(prefix="mwpro_selftest_"))
    try:
        from metadata_writer_pro.app.core.csv_manager import MetadataModel, load_csv
        from metadata_writer_pro.app.core.processing_engine import ProcessingEngine
        from metadata_writer_pro.app.metadata.base import build_default_registry

        ff = _ffmpeg()
        checks["ffmpeg_found"] = str(ff)

        reg = build_default_registry()
        checks["registry_image"] = reg.for_file(work / "a.jpg") is not None
        checks["registry_video_mp4"] = reg.for_file(work / "a.mp4") is not None
        checks["registry_video_mov"] = reg.for_file(work / "a.mov") is not None
        checks["registry_rejects_avi"] = reg.for_file(work / "a.avi") is None

        _gen(ff, work / "photo.jpg", "jpg")
        _gen(ff, work / "clip.mp4", "mp4")
        _gen(ff, work / "clip.mov", "mov")

        (work / "meta.csv").write_text(
            "filename,title,description,keywords\n"
            'photo.jpg,ঢাকা শহর,রাজধানীর ছবি,"ঢাকা, বাংলাদেশ"\n'
            'clip.mp4,Test Clip,Test description,"alpha, beta"\n'
            'clip.mov,Mov Clip,Mov description,"gamma, delta"\n',
            encoding="utf-8-sig",
        )
        v = load_csv(work / "meta.csv")
        checks["csv_ok"] = v.ok and v.total_rows == 3
        checks["csv_bengali"] = v.rows[0].metadata.title == "ঢাকা শহর" if v.rows else False

        engine = ProcessingEngine(registry=reg)
        events: list = []
        thread = engine.run_async(
            v.rows, work,
            {"rename_enabled": True, "create_backup": True, "continue_on_error": True,
             "overwrite": True, "write_fields": ["title", "description", "keywords"]},
            lambda k, p: events.append((k, p)),
        )
        thread.join(timeout=300)
        by_name = {r.filename: r for r in engine.results}
        checks["engine_success_count"] = sum(1 for r in engine.results if r.status == "success")
        checks["jpg_renamed"] = (by_name.get("photo.jpg") is not None
                                 and by_name["photo.jpg"].final_name == "ঢাকা-শহর.jpg"
                                 and by_name["photo.jpg"].status == "success")
        checks["mp4_renamed"] = (by_name.get("clip.mp4") is not None
                                 and by_name["clip.mp4"].final_name == "test-clip.mp4"
                                 and by_name["clip.mp4"].status == "success")
        checks["mov_renamed"] = (by_name.get("clip.mov") is not None
                                 and by_name["clip.mov"].final_name == "mov-clip.mov"
                                 and by_name["clip.mov"].status == "success")
        img_proc = reg.for_file(work / "ঢাকা-শহর.jpg")
        checks["jpg_verify"] = bool(img_proc and img_proc.verify(
            work / "ঢাকা-শহর.jpg",
            MetadataModel(title="ঢাকা শহর", description="রাজধানীর ছবি",
                          keywords=["ঢাকা", "বাংলাদেশ"])))
        vid_proc = reg.for_file(work / "test-clip.mp4")
        checks["mp4_verify"] = bool(vid_proc and vid_proc.verify(
            work / "test-clip.mp4",
            MetadataModel(title="Test Clip", description="Test description",
                          keywords=["alpha", "beta"])))
        mov_proc = reg.for_file(work / "mov-clip.mov")
        checks["mov_verify"] = bool(mov_proc and mov_proc.verify(
            work / "mov-clip.mov",
            MetadataModel(title="Mov Clip", description="Mov description")))
        rep = engine.export_report(work / "report.csv")
        checks["report_written"] = rep.is_file()

        failures = [k for k, val in checks.items() if val is False]
        report = {"ok": not failures, "app_version": APP_VERSION,
                  "finished_at": _dt.datetime.now().isoformat(timespec="seconds"),
                  "work_dir": str(work), "checks": checks, "failures": failures}
    except Exception as exc:  # self-test must always produce a report, never a traceback exit
        report = {"ok": False, "app_version": APP_VERSION,
                  "finished_at": _dt.datetime.now().isoformat(timespec="seconds"),
                  "work_dir": str(work), "checks": checks, "error": str(exc)[:500]}
    if out_path:
        try:
            p = Path(out_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            report["report_path"] = str(p)
        except Exception as exc:
            report["report_write_error"] = str(exc)[:200]
    return report
