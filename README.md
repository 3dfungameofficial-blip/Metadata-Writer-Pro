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

## Installation (official releases only)

Download `MetadataWriterPro-Setup.exe` and `SHA256SUMS.txt` from the official
GitHub Releases page:

`https://github.com/3dfungameofficial-blip/Metadata-Writer-Pro/releases`

Optional manual verification (PowerShell):

```powershell
$h = (Get-FileHash MetadataWriterPro-Setup.exe -Algorithm SHA256).Hash.ToLower()
Select-String SHA256SUMS.txt -Pattern $h
```

Run the installer (per-user, no admin rights needed, no Python/FFmpeg required).
User data in `%APPDATA%\Metadata Writer Pro` survives upgrades and uninstalls.

## Updates

`About → Check for Updates` (or the silent auto-check) queries the official
releases API, compares semantic versions, shows release notes, then — only on
your confirmation — downloads the installer with live progress, verifies its
SHA-256 against the release's `SHA256SUMS.txt`, verifies its Authenticode
signature, and only then launches it. If the app is offline, or the check
fails, everything keeps working; you'll just see a friendly message.

## Security

- **Official source only**: updates come exclusively from this repository's
  GitHub Releases over HTTPS; the updater only trusts the expected installer
  filename, never arbitrary URLs, mirrors, or redirects.
- **SHA-256 verification**: every release ships `SHA256SUMS.txt`; a hash
  mismatch deletes the download and refuses installation — tested by an
  automated mismatch test.
- **Authenticode gate**: release binaries are SHA-256 timestamp-signed; the
  updater refuses unsigned or invalidly signed installers (verified by
  `tools/sign.py verify`, used by CI and the app).
- **No code execution from downloads**: installers are launched via the OS
  after verification; metadata/CSV content is never executed (`shell=False`
  everywhere, no `eval`/`pickle`).

## Windows SmartScreen

Release binaries are Authenticode-signed with a trusted certificate and an
RFC 3161 timestamp. Even so, newly released software can initially show a
SmartScreen reputation warning — reputation is controlled by Microsoft and
builds over time with consistent publisher identity, stable assets, and
legitimate distribution. No software can guarantee zero warnings on day one.

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
