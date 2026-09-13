"""File safety: optional backups into a dedicated user-data directory."""
from __future__ import annotations

import datetime as _dt
import shutil
from pathlib import Path

from metadata_writer_pro.app.services.logger import get_logger
from metadata_writer_pro.app.utils import paths as paths_mod

log = get_logger("backup")


def create_backup(source: Path) -> Path | None:
    """Copy *source* into a timestamped backup folder. Returns backup path."""
    try:
        stamp = _dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        dest_dir = paths_mod.backup_dir() / stamp
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / source.name
        # Avoid collision inside the backup dir itself
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{source.stem}-{counter}{source.suffix}"
            counter += 1
        shutil.copy2(source, dest)
        return dest
    except Exception as exc:
        log.error("Backup failed for %s: %s", source, exc)
        return None
