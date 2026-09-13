"""Update service abstraction (versioned releases, no arbitrary code exec).

Design:
  Installed App -> check latest version (GitHub Releases API or custom JSON)
  -> compare semantic versions -> show release notes
  -> download installer asset -> verify sha256 (REQUIRED before install)
  -> user confirms -> launch installer -> restart.

The service never executes downloaded Python code; it only downloads
versioned release artifacts (typically a Setup.exe) and, only after hash
verification, hands the file to the OS. If no trusted sha256 is available
for an asset, installation is REFUSED and the user is pointed at the
manual download page.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from metadata_writer_pro.app import APP_VERSION, UPDATE_CHECK_URL
from metadata_writer_pro.app.services.logger import get_logger

log = get_logger("updater")

MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024  # sanity cap: refuse absurd artifacts


@dataclass
class ReleaseInfo:
    version: str
    notes: str
    download_url: str
    sha256: str = ""


def updates_configured() -> bool:
    """True when the publisher configured a real update endpoint."""
    return bool(UPDATE_CHECK_URL and UPDATE_CHECK_URL.startswith(("http://", "https://")))


def _parse_version(v: str) -> tuple[int, ...]:
    parts = []
    for chunk in str(v).lstrip("vV").split("."):
        num = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts) or (0,)


def is_newer(latest: str, current: str = APP_VERSION) -> bool:
    return _parse_version(latest) > _parse_version(current)


class UpdateNotConfigured(Exception):
    """Raised when the build has no update endpoint configured."""


def check_for_updates(url: str = UPDATE_CHECK_URL, timeout: int = 15) -> ReleaseInfo | None:
    """Return ReleaseInfo if a newer release exists, else None.

    Raises UpdateNotConfigured when the publisher did not configure an endpoint.
    """
    endpoint = url or UPDATE_CHECK_URL
    if not endpoint or not endpoint.startswith(("http://", "https://")):
        raise UpdateNotConfigured(
            "Automatic updates are not configured for this build. "
            "Set UPDATE_CHECK_URL to a release endpoint to enable them."
        )
    try:
        req = urllib.request.Request(endpoint, headers={"User-Agent": "MetadataWriterPro", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
        if not isinstance(payload, dict):
            raise ValueError("unexpected update payload")
        version = str(payload.get("tag_name") or payload.get("version") or "").lstrip("vV")
        if not version or not is_newer(version):
            return None
        assets = payload.get("assets") or []
        dl = ""
        digest = ""
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name", ""))
            if name.lower().endswith(".exe") and "setup" in name.lower():
                dl = str(asset.get("browser_download_url", ""))
                digest = str(asset.get("sha256") or asset.get("digest") or "")
                break
        if not dl and assets and isinstance(assets[0], dict):
            dl = str(assets[0].get("browser_download_url", ""))
        return ReleaseInfo(
            version=version,
            notes=str(payload.get("body") or payload.get("notes") or ""),
            download_url=dl or str(payload.get("html_url", "")),
            sha256=digest,
        )
    except UpdateNotConfigured:
        raise
    except Exception as exc:
        log.warning("Update check failed: %s", exc)
        return None


def download_update(info: ReleaseInfo, dest: Path) -> Path:
    """Download a release artifact to *dest* (streamed, size-capped, no code execution)."""
    if not info.download_url.startswith(("http://", "https://")):
        raise ValueError("Refusing to download from a non-HTTP(S) URL.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(info.download_url, headers={"User-Agent": "MetadataWriterPro"})
    total = 0
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as fh:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                fh.close()
                try:
                    dest.unlink()
                except OSError:
                    pass
                raise ValueError("Download exceeds the 500 MB safety cap; aborted.")
            fh.write(chunk)
    if info.sha256:
        verify_sha256(dest, info.sha256)
    return dest


def verify_sha256(path: Path, expected: str) -> bool:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 256), b""):
            digest.update(chunk)
    ok = digest.hexdigest().lower() == expected.lower()
    if not ok:
        raise ValueError(f"Checksum mismatch for {path.name} — update will NOT be installed.")
    return True


def install_artifact(path: Path, expected_sha256: str) -> None:
    """Verify then hand the installer to the OS. Refuses when no hash is known."""
    if not expected_sha256:
        raise ValueError(
            "No trusted SHA-256 hash is available for this update, so it cannot "
            "be verified. Installation refused — download it manually instead."
        )
    verify_sha256(path, expected_sha256)
    if os.name == "nt":
        os.startfile(str(path))  # noqa: S606 -- user-confirmed installer launch
    else:
        import subprocess

        subprocess.Popen([str(path)])
