"""SEO-friendly filename helpers: safe on Windows, unicode-aware, dedup."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# Windows-invalid chars + control chars
_INVALID_CHARS = re.compile(r'[\\/*?:"<>|\x00-\x1f]')
_WHITESPACE_RUN = re.compile(r"\s+")
_MAX_BASENAME = 150  # keep well under MAX_PATH even with long dirs

# Reserved DOS device names that Windows refuses as file stems (CON.mp4 etc.)
_RESERVED_STEMS = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


def slugify_title(title: str) -> str:
    """Convert a title to an SEO-friendly slug.

    Example: 'My Amazing Video!' -> 'my-amazing-video'
    Unicode letters (e.g. Bengali) are preserved; only filesystem-unsafe
    characters are removed.
    """
    if title is None:
        return ""
    text = str(title).strip()
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = _INVALID_CHARS.sub("", text)
    text = _WHITESPACE_RUN.sub("-", text.strip())
    text = re.sub(r"-{2,}", "-", text)
    text = text.strip("-._ ")
    text = text.lower()
    if len(text) > _MAX_BASENAME:
        text = text[:_MAX_BASENAME].rstrip("-._ ")
    if text in _RESERVED_STEMS:
        # "con" -> "_con": never emit a reserved device name.
        text = f"_{text}"
    return text


def unique_path_in_dir(directory: Path, stem: str, suffix: str, current: Path | None = None) -> Path:
    """Return a non-colliding path: stem.suffix, stem-1.suffix, ..."""
    suffix = suffix.lower() if suffix.lower() in {".jpg", ".jpeg", ".png", ".mp4", ".mov"} else suffix
    candidate = directory / f"{stem}{suffix}"
    if current is not None:
        try:
            if candidate.resolve() == current.resolve():
                return candidate
        except OSError:
            if candidate == current:
                return candidate
    counter = 1
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def seo_target_path(source: Path, title: str) -> Path | None:
    """Compute the SEO rename target for *source*, or None if not renamable."""
    slug = slugify_title(title)
    if not slug:
        return None
    target = unique_path_in_dir(source.parent, slug, source.suffix, current=source)
    try:
        same = target.resolve() == source.resolve()
    except OSError:
        same = target == source
    return None if same else target
