# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build: python -m PyInstaller MetadataWriterPro.spec"""
import shutil
from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

datas = []
for asset in ("assets/icon.ico", "assets/icon.png"):
    if (root / asset).exists():
        datas.append((str(root / asset), "assets"))

# Bundle FFmpeg so the installed app works with no system FFmpeg / PATH.
# The app looks up the bundled binary as "ffmpeg.exe" (see utils.paths),
# so stage it under that exact name first.
stage = root / "build" / "bundle_bin"
stage.mkdir(parents=True, exist_ok=True)
try:
    import imageio_ffmpeg
    ff = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if ff.is_file():
        shutil.copy2(ff, stage / "ffmpeg.exe")
        datas.append((str(stage / "ffmpeg.exe"), "."))
except Exception as exc:
    print(f"WARNING: could not stage bundled ffmpeg: {exc}")

# ffprobe is optional (only a nicer validator); bundle it when the build
# machine has one, the app falls back to ffmpeg probing otherwise.
_probe = shutil.which("ffprobe")
if _probe:
    shutil.copy2(_probe, stage / "ffprobe.exe")
    datas.append((str(stage / "ffprobe.exe"), "."))

binaries = []
hiddenimports = ["PIL", "pandas", "pyexiv2"]

a = Analysis(
    ["metadata_writer_pro/app/main.py"],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="MetadataWriterPro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico" if (root / "assets/icon.ico").exists() else None,
    version_file=None,
)
