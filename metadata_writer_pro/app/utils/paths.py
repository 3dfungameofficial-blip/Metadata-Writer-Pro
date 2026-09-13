"""Robust path resolution for dev / PyInstaller / installed modes + user dirs."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from metadata_writer_pro.app import APP_NAME


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")


def base_dir() -> Path:
    """Directory containing bundled resources (sys._MEIPASS when frozen)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    # .../metadata_writer_pro/app/utils/paths.py -> parents[3] is the project root
    here = Path(__file__).resolve()
    for depth in (3, 4):
        try:
            cand = here.parents[depth]
        except IndexError:
            continue
        if (cand / "assets").is_dir() or (cand / "pyproject.toml").is_file():
            return cand
    return here.parents[3]


def resource_path(relative: str | os.PathLike) -> Path:
    """Resolve a bundled resource (assets, icon, binaries)."""
    rel = Path(relative)
    if rel.is_absolute() and rel.exists():
        return rel
    candidate = base_dir() / rel
    if candidate.exists():
        return candidate
    # Fallback: alongside the app package
    alt = Path(__file__).resolve().parents[2] / rel
    return alt if alt.exists() else candidate


def _windows_appdata() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata)
    return Path.home() / "AppData" / "Roaming"


def user_data_dir() -> Path:
    """Per-user config/data dir (never inside install dir)."""
    if sys.platform == "win32":
        p = _windows_appdata() / APP_NAME
    elif sys.platform == "darwin":
        p = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        p = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = user_data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def backup_dir() -> Path:
    p = user_data_dir() / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


def settings_path() -> Path:
    return user_data_dir() / "settings.json"


def history_path() -> Path:
    return user_data_dir() / "history.json"


def ffmpeg_exe() -> Path | None:
    """Locate a usable ffmpeg binary: bundled -> imageio-ffmpeg -> system PATH."""
    # 1. Bundled next to resources / install dir
    for name in ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg",
                 "bin/ffmpeg.exe", "bin/ffmpeg", "ffmpeg/ffmpeg.exe"):
        c = resource_path(name)
        if c.is_file():
            return c
    # 2. imageio-ffmpeg wheel (bundles a static ffmpeg, no user install needed)
    try:
        import imageio_ffmpeg  # type: ignore

        exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
        if exe.is_file():
            return exe
    except Exception:
        pass
    # 3. System PATH
    import shutil

    which = shutil.which("ffmpeg")
    return Path(which) if which else None


def ffprobe_exe() -> Path | None:
    import shutil

    # imageio-ffmpeg ships ffmpeg only; look for system ffprobe as a bonus
    which = shutil.which("ffprobe")
    if which:
        return Path(which)
    base = ffmpeg_exe()
    if base is not None:
        sibling = base.parent / ("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
        if sibling.is_file():
            return sibling
    return None
