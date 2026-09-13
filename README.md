# Metadata Writer Pro v1.0.0

Batch metadata editor for images and video on Windows. Select a CSV + media folder,
validate, preview, and apply title/description/keywords — with optional SEO-friendly
rename, backups, background processing, reports, and versioned updates.

## Features

- CSV import (UTF-8 / UTF-8-SIG, case-insensitive headers, Bengali Unicode)
- Images: JPG, JPEG, PNG via pyexiv2 (XMP/IPTC/EXIF, preserves unrelated tags)
- Video: MP4, MOV via bundled FFmpeg remux (`-c copy`, no re-encode, faststart for MP4)
- SEO rename with Windows-safe slugs + dedup (`my-video.mp4`, `my-video-1.mp4`),
  reserved device names (`CON`, `PRN`, …) neutralised, collisions never overwrite
- Optional timestamped backups (byte-identical copies in `%APPDATA%`), pause/cancel
  (cancel finishes the current file, then stops), per-file friendly errors
- Validation panel + 100-row preview, progress, counts, elapsed time
- `logs/app.log` + per-run `logs/processing-*.log`, Open Log Folder, CSV/JSON report export
  (report distinguishes `metadata` / `metadata+rename` / `rename` / `verify` / `match` operations)
- Settings with schema migration (corrupt files are backed up, never crash), light/dark/system themes
- Update service: checks releases API, shows notes, downloads Setup.exe,
  **requires SHA-256 verification before install** — refuses otherwise

## Supported formats

| Format | Title | Description | Keywords | Author | Copyright | Notes |
|--------|-------|-------------|----------|--------|-----------|-------|
| JPG/JPEG | ✓ | ✓ | ✓ | — | — | XMP/IPTC/EXIF, rating 5 |
| PNG | ✓ | ✓ | ✓ | — | — | Written correctly; Windows Explorer usually doesn't display PNG metadata |
| MP4 | ✓ | ✓ (+comment mirror) | ✓ | ✓ (author+artist) | ✓ | Stream copy, faststart |
| MOV | ✓ | ✓ (stored as `comment`) | ✕ container limitation | ✓ (artist) | ✓ | QuickTime udta drops `description`/`keywords` keys; app reports this in results |

New formats plug in via `MetadataProcessor.supports()` + `write_metadata()` in
`metadata_writer_pro/app/metadata/` (see `base.py`).

## Development

```bat
pip install -r requirements.txt
python -m metadata_writer_pro
```

Headless pipeline check (no GUI):

```bat
python -m metadata_writer_pro --self-test C:\Temp\mwpro_selftest.json
```

Legacy single-file app is preserved as `app.py` (reference only).

## Tests

```bat
python -m pytest tests -q
```

Covers CSV edges, Bengali, filename safety, media routing, real MP4/MOV/PNG
round-trips, failure recovery, pause/cancel, 300-file batch, settings migration,
update security.

## Build .exe

```bat
build_app.bat
```

Bundles the `imageio-ffmpeg` binary as `ffmpeg.exe` plus the app icon, and produces
`dist/MetadataWriterPro.exe` (~200 MB: pandas + Tk + pyexiv2 + FFmpeg).
No Python/FFmpeg needed on target machines. Verify with:

```bat
dist\MetadataWriterPro.exe --self-test C:\Temp\mwpro_selftest.json
```

## Build installer

```bat
build_installer.bat
```

Requires Inno Setup 6. Produces `MetadataWriterPro-Setup.exe` (Start Menu shortcut,
optional desktop icon, uninstaller, stable AppId for clean upgrades).
`%APPDATA%\Metadata Writer Pro` (settings, history, logs, backups) is left untouched
by install AND uninstall.

## Updates

`About → Check for Updates` (or silent auto-check) queries the releases endpoint,
compares semantic versions, shows release notes, and (on user confirmation) downloads
the new Setup.exe, verifies SHA-256, then launches it. Without a trusted hash,
installation is **refused** with a clear error. No downloaded code is ever executed.

Endpoint is **not configured** in this build (`UPDATE_CHECK_URL = ""` in
`metadata_writer_pro/app/__init__.py`) — the UI says so instead of pointing at a
fake repository. Publisher: set it to your real releases API, e.g.
`https://api.github.com/repos/YOUR_USERNAME/YOUR_REPO/releases/latest`.

## Architecture

```
metadata_writer_pro/app/
  main.py  selftest.py  ui/main_window.py
  core/ (csv_manager, media_manager, processing_engine)
  metadata/ (base registry, image pyexiv2, video ffmpeg)
  services/ (settings, logger, backup, updater)
  utils/ (paths, filenames, validation)
```

## Licensing notes (redistribution)

- App code: your own license applies.
- Bundled `ffmpeg.exe` (via `imageio-ffmpeg`) is an FFmpeg binary — FFmpeg is
  LGPL/GPL licensed. Redistribution requires honoring those terms (attribute
  FFmpeg, link `https://ffmpeg.org`, and provide the corresponding source offer
  for the exact binary shipped). Replace/upgrade the binary only with builds
  whose license terms you have reviewed.
- `pyexiv2`/Exiv2, Tk/tcl, pandas/numpy carry their own licenses — include their
  notices when distributing.

## Known limitations

- PNG metadata is written correctly but Windows Explorer often doesn't display it
- MOV cannot store `keywords` (QuickTime container limitation — reported per file, not silent)
- Cancel finishes the current file first (never interrupts a file mid-write)
- Drag-and-drop needs optional `tkinterdnd2`, otherwise Browse buttons are used
- Video write requires FFmpeg (bundled in the .exe; dev mode uses `imageio-ffmpeg` or system ffmpeg)
