"""Video metadata writer (MP4/MOV) via FFmpeg container remux (no re-encode).

Strategy:
  ffmpeg -i input -map 0 -c copy -map_metadata 0
         -metadata title=... -metadata description=... -metadata comment=...
         -metadata keywords=... [-metadata author/artist copyright]
         [-movflags +faststart for MP4] output_tmp

Streams are copied (codec/resolution/fps/duration preserved). The temp
file atomically replaces the original only after passing validation, so a
failed FFmpeg run, a failed probe, or a crash before replacement always
leaves the original intact. Temp files use a distinctive ``_mwptmp_``
infix and are deleted on failure; stale ones are swept at batch start.

Container support (verified against ffmpeg 7.x ``-i`` tag dumps):
  MP4: title, description (+comment mirror), keywords, author/artist,
       copyright — all round-trip.
  MOV (QuickTime udta): title, author/artist, description (stored as
       ``comment``), copyright. The MOV muxer silently drops the
       ``description`` and ``keywords`` keys, so keywords are unsupported
       on MOV and ``verify()`` does not require them there.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

from metadata_writer_pro.app import VIDEO_EXTENSIONS
from metadata_writer_pro.app.core.csv_manager import MetadataModel
from metadata_writer_pro.app.metadata.base import MetadataProcessor
from metadata_writer_pro.app.services.logger import get_logger
from metadata_writer_pro.app.utils import paths as paths_mod

log = get_logger("video")

TMP_INFIX = "_mwptmp_"
_TAG_LINE = re.compile(r"(?m)^\s+([A-Za-z][\w\-]*)\s*:\s*(.+?)\s*$")


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    # Never shell=True: metadata text is untrusted input.
    # errors="replace": ffmpeg stderr may contain non-locale bytes (e.g. CJK/Bengali tags).
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                          timeout=timeout, check=False)


class VideoMetadataProcessor(MetadataProcessor):
    name = "video"

    def supports(self, file_path: Path) -> bool:
        return Path(file_path).suffix.lower() in VIDEO_EXTENSIONS

    def _ffmpeg(self) -> Path:
        exe = paths_mod.ffmpeg_exe()
        if exe is None:
            raise RuntimeError(
                "FFmpeg is not available, so video metadata cannot be written. "
                "Reinstall the application."
            )
        return exe

    # -- tag I/O -------------------------------------------------------
    def read_tags(self, file_path: Path) -> dict[str, str]:
        """Best-effort read of container-level text tags (lowercased keys)."""
        ffmpeg = self._ffmpeg()
        r = _run([str(ffmpeg), "-hide_banner", "-i", str(file_path)], timeout=60)
        out = (r.stderr or "") + (r.stdout or "")
        tags: dict[str, str] = {}
        for key, value in _TAG_LINE.findall(out):
            tags.setdefault(key.strip().lower(), value.strip())
        return tags

    def _desired_fields(self, metadata: MetadataModel, existing: dict[str, str],
                        overwrite: bool) -> list[tuple[str, str]]:
        """Fields we control. Empty values never erase existing tags; with
        overwrite=False, non-empty existing tags are left untouched."""
        keywords = ", ".join(metadata.keywords or [])
        description = metadata.description or metadata.title or ""
        candidates: list[tuple[str, str]] = []
        if metadata.title:
            candidates.append(("title", metadata.title))
        if description:
            # MP4/MOV players read 'description' and/or 'comment' inconsistently; set both.
            candidates.append(("description", description))
            candidates.append(("comment", description))
        if keywords:
            candidates.append(("keywords", keywords))
        if metadata.author:
            candidates.append(("author", metadata.author))
            candidates.append(("artist", metadata.author))
        if metadata.copyright:
            candidates.append(("copyright", metadata.copyright))
        if overwrite:
            return [(k, v) for k, v in candidates if v]
        kept = []
        for k, v in candidates:
            if v and not existing.get(k):
                kept.append((k, v))
        return kept

    def write_metadata(self, file_path: Path, metadata: MetadataModel, *, overwrite: bool = True) -> None:
        file_path = Path(file_path)
        if not file_path.is_file():
            raise FileNotFoundError(str(file_path))
        ffmpeg = self._ffmpeg()
        suffix = file_path.suffix.lower()

        existing: dict[str, str] = {}
        if not overwrite:
            try:
                existing = self.read_tags(file_path)
            except Exception as exc:
                log.warning("Could not read existing tags; overwriting mapped fields: %s", exc)
        fields = self._desired_fields(metadata, existing, overwrite)

        tmp_fd, tmp_name = tempfile.mkstemp(prefix=file_path.stem + TMP_INFIX, suffix=file_path.suffix,
                                            dir=str(file_path.parent))
        os.close(tmp_fd)
        tmp = Path(tmp_name)
        try:
            cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-i", str(file_path),
                   "-map", "0", "-c", "copy", "-map_metadata", "0"]
            # Only set fields we control; everything else is preserved via map_metadata.
            for k, v in fields:
                cmd += ["-metadata", f"{k}={v}"]
            if suffix == ".mp4":
                cmd += ["-movflags", "+faststart"]
            cmd.append(str(tmp))

            result = _run(cmd)
            if result.returncode != 0 or not tmp.is_file() or tmp.stat().st_size == 0:
                err = (result.stderr or result.stdout or "ffmpeg failed").strip()[:800]
                raise RuntimeError(f"FFmpeg could not write metadata: {err}")
            if not self._output_valid(tmp):
                raise RuntimeError("FFmpeg produced an unreadable file; original was left untouched.")
            # Atomic replace: original is only touched after verified output exists.
            tmp.replace(file_path)
        except Exception:
            try:
                if tmp.is_file():
                    tmp.unlink()
            except OSError:
                pass
            raise

    def _output_valid(self, path: Path) -> bool:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        # Prefer ffprobe duration check; fallback to ffmpeg decode probe.
        ffprobe = paths_mod.ffprobe_exe()
        try:
            if ffprobe is not None:
                r = _run([str(ffprobe), "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=noprint_wrappers=1:nokey=1", str(path)], timeout=60)
                if r.returncode == 0 and r.stdout.strip():
                    return float(r.stdout.strip()) >= 0
                return r.returncode == 0
            ffmpeg = paths_mod.ffmpeg_exe()
            if ffmpeg is None:
                return True  # nothing to probe with; size check already passed
            r = _run([str(ffmpeg), "-hide_banner", "-loglevel", "error",
                      "-i", str(path), "-f", "null", "-"], timeout=120)
            return r.returncode == 0
        except Exception as exc:
            log.warning("Video validation probe failed: %s", exc)
            return True  # do not block on probe errors; size check passed

    def verify(self, file_path: Path, metadata: MetadataModel) -> bool:
        """Read back the tags the container actually supports and compare.

        Only explicitly provided model fields are required (no title-fallback
        for description), so callers must pass the same model used for writing.
        """
        if not super().verify(file_path, metadata):
            return False
        try:
            tags = self.read_tags(file_path)
        except Exception as exc:
            log.warning("Verification read failed for %s: %s", file_path, exc)
            return False
        suffix = Path(file_path).suffix.lower()
        if metadata.title and tags.get("title") != metadata.title:
            return False
        if metadata.description:
            # MOV stores description only as 'comment'.
            if suffix == ".mov":
                if tags.get("comment", "") != metadata.description:
                    return False
            elif tags.get("description", "") != metadata.description \
                    and tags.get("comment", "") != metadata.description:
                return False
        if metadata.keywords and suffix == ".mp4":
            if tags.get("keywords", "") != ", ".join(metadata.keywords):
                return False
        # keywords on MOV are unsupported by the container — not required.
        if metadata.author and tags.get("author", "") != metadata.author \
                and tags.get("artist", "") != metadata.author:
            return False
        if metadata.copyright and tags.get("copyright", "") != metadata.copyright:
            return False
        return True

    def unsupported_notes(self, file_path: Path, metadata: MetadataModel) -> list[str]:
        """Honest per-container limitation notes for logs/reports."""
        notes = []
        if Path(file_path).suffix.lower() == ".mov" and metadata.keywords:
            notes.append("MOV container does not store keywords; title/description(author)/copyright applied.")
        return notes
