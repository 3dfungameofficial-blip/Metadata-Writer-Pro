"""Media discovery + extension-based classification (extensible)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from metadata_writer_pro.app import IMAGE_EXTENSIONS, SUPPORTED_EXTENSIONS, VIDEO_EXTENSIONS


@dataclass
class MediaFile:
    path: Path
    kind: str  # 'image' | 'video'

    @property
    def name(self) -> str:
        return self.path.name


def classify(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return None


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def scan_folder(folder: Path) -> list[MediaFile]:
    """Non-recursive scan of supported media files (case-insensitive ext)."""
    out: list[MediaFile] = []
    if not folder.is_dir():
        return out
    for entry in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_file():
            kind = classify(entry)
            if kind:
                out.append(MediaFile(path=entry, kind=kind))
    return out


def build_index(folder: Path) -> dict[str, MediaFile]:
    """Map lowercase filename -> MediaFile for O(1) CSV matching."""
    return {m.name.lower(): m for m in scan_folder(folder)}


def supported_label() -> str:
    return "Images: JPG, JPEG, PNG   •   Video: MP4, MOV"
