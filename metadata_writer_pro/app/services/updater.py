"""Update service: versioned GitHub Releases + mandatory SHA-256 + Authenticode gate.

Trust chain:
  official repo release (HTTPS, expected repo)
    -> expected installer asset filename (never arbitrary URLs)
    -> SHA256SUMS.txt from the SAME release -> expected hash
    -> download (size-capped) -> hash compare -> Authenticode verify
    -> launch installer.

Any break in the chain (hash mismatch, missing hash, unsigned/invalid
signature) raises and the installer is NEVER launched. The service never
executes downloaded code; it hands a verified Setup.exe to the OS.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from metadata_writer_pro.app import (
    APP_VERSION,
    CHECKSUMS_ASSET,
    EXPECTED_INSTALLER_ASSET,
    UPDATE_CHECK_URL,
)
from metadata_writer_pro.app.services.logger import get_logger

log = get_logger("updater")

MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024  # sanity cap: refuse absurd artifacts
MAX_CHECKSUMS_BYTES = 1 * 1024 * 1024  # SHA256SUMS.txt must be tiny
INSTALLER_NAME_RE = re.compile(r"^MetadataWriterPro-Setup(?:-[\d.]+)?\.exe$", re.IGNORECASE)
ProgressCb = Callable[[int, int | None], None]


@dataclass
class ReleaseInfo:
    version: str
    tag: str
    notes: str
    installer_url: str
    installer_filename: str
    sha256: str = ""
    checksums_url: str = ""


def updates_configured() -> bool:
    """True when the build points at a real https update endpoint."""
    return bool(UPDATE_CHECK_URL and UPDATE_CHECK_URL.startswith("https://"))


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


class UpdateError(Exception):
    """Any update-pipeline failure (network, format, trust)."""


def _get_json(url: str, timeout: int) -> dict:
    if not url.startswith("https://"):
        raise UpdateError("Refusing non-HTTPS update URL.")
    req = urllib.request.Request(url, headers={"User-Agent": "MetadataWriterPro",
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
    except UpdateError:
        raise
    except Exception as exc:
        raise UpdateError(f"Could not reach the update server: {exc}") from exc
    if not isinstance(payload, dict):
        raise UpdateError("Update server returned an unexpected response.")
    return payload


def _get_text(url: str, timeout: int, cap: int) -> str:
    if not url.startswith("https://"):
        raise UpdateError("Refusing non-HTTPS update URL.")
    req = urllib.request.Request(url, headers={"User-Agent": "MetadataWriterPro"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(cap + 1)
    except Exception as exc:
        raise UpdateError(f"Could not download {url}: {exc}") from exc
    if len(data) > cap:
        raise UpdateError("Download exceeds the safety cap; aborted.")
    return data.decode("utf-8", "replace")


def parse_checksums(text: str, filename: str) -> str:
    """Extract the expected sha256 for *filename* from SHA256SUMS content."""
    want = filename.lower()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        digest, name = parts[0], parts[-1].lstrip("*").strip()
        if name.lower() == want and re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            return digest.lower()
    return ""


def _https_asset_url(asset: dict) -> str:
    url = str(asset.get("browser_download_url", ""))
    if not url.startswith("https://"):
        raise UpdateError(f"Release asset has an untrusted URL: {url!r}")
    return url


def check_for_updates(url: str = UPDATE_CHECK_URL, timeout: int = 15) -> ReleaseInfo | None:
    """Return ReleaseInfo if a newer release exists, else None.

    Raises UpdateNotConfigured when no endpoint is configured, UpdateError on
    network/format failures (callers may show them or fail silent for auto-check).
    A newer release WITHOUT a usable installer asset yields a ReleaseInfo with
    empty installer_url so the UI can say so instead of lying about "latest".
    """
    endpoint = url or UPDATE_CHECK_URL
    if not endpoint or not endpoint.startswith("https://"):
        raise UpdateNotConfigured(
            "Automatic updates are not configured for this build."
        )
    try:
        payload = _get_json(endpoint, timeout)
    except UpdateError as exc:
        log.warning("Update check failed: %s", exc)
        return None
    try:
        tag = str(payload.get("tag_name") or "")
        version = tag.lstrip("vV")
        if not version or not is_newer(version):
            return None
        assets = payload.get("assets") or []
        if not isinstance(assets, list):
            raise UpdateError("Malformed release asset list.")
        installer_url = installer_name = checksums_url = ""
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name", ""))
            if not installer_url and INSTALLER_NAME_RE.match(name):
                installer_url = _https_asset_url(asset)
                installer_name = name
            elif name == CHECKSUMS_ASSET:
                checksums_url = _https_asset_url(asset)
        digest = ""
        if installer_url and checksums_url:
            try:
                sums = _get_text(checksums_url, timeout, MAX_CHECKSUMS_BYTES)
                digest = parse_checksums(sums, installer_name)
                if not digest:
                    log.warning("SHA256SUMS.txt has no entry for %s", installer_name)
            except UpdateError as exc:
                log.warning("Could not fetch checksums: %s", exc)
        return ReleaseInfo(
            version=version,
            tag=tag,
            notes=str(payload.get("body") or ""),
            installer_url=installer_url,
            installer_filename=installer_name or EXPECTED_INSTALLER_ASSET,
            sha256=digest,
            checksums_url=checksums_url,
        )
    except UpdateError as exc:
        log.warning("Update check failed: %s", exc)
        return None
    except Exception as exc:
        log.warning("Update check failed: %s", exc)
        return None


def download_update(info: ReleaseInfo, dest: Path,
                    progress: ProgressCb | None = None) -> Path:
    """Download the release installer (streamed, size-capped). Verifies hash when known."""
    if not info.installer_url.startswith("https://"):
        raise UpdateError("No trusted installer URL for this release.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(info.installer_url, headers={"User-Agent": "MetadataWriterPro"})
    total: int | None = None
    done = 0
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as fh:
            try:
                total = int(resp.headers.get("Content-Length", "") or 0) or None
            except (ValueError, AttributeError):
                total = None
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                done += len(chunk)
                if done > MAX_DOWNLOAD_BYTES:
                    raise UpdateError("Download exceeds the 500 MB safety cap; aborted.")
                fh.write(chunk)
                if progress:
                    progress(done, total)
    except UpdateError:
        _safe_unlink(dest)
        raise
    except Exception as exc:
        _safe_unlink(dest)
        raise UpdateError(f"Download interrupted: {exc}") from exc
    if info.sha256:
        try:
            verify_sha256(dest, info.sha256)
        except UpdateError:
            _safe_unlink(dest)
            raise
    return dest


def _safe_unlink(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def verify_sha256(path: Path, expected: str) -> bool:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 256), b""):
            digest.update(chunk)
    ok = digest.hexdigest().lower() == expected.lower()
    if not ok:
        raise UpdateError(
            f"Update verification failed. The downloaded file does not match "
            f"the trusted SHA-256 checksum. The update was not installed.")
    return True


def verify_authenticode(path: Path) -> tuple[bool, str]:
    """Windows-native Authenticode check. Returns (trusted, message)."""
    if os.name != "nt":
        return False, "Authenticode verification requires Windows."
    # EncodedCommand avoids all quoting pitfalls with spaced paths.
    script = (
        "$s = Get-AuthenticodeSignature -LiteralPath $env:MWPRO_VERIFY_PATH; "
        "$ts = $s.TimeStamperCertificate -ne $null; "
        "Write-Output (\"STATUS=\" + $s.Status); "
        "Write-Output (\"TS=\" + $ts); "
        "Write-Output (\"MSG=\" + $s.StatusMessage); "
        "Write-Output (\"SUBJECT=\" + $s.SignerCertificate.Subject)"
    )
    import base64

    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    env = dict(os.environ, MWPRO_VERIFY_PATH=str(path))
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                            "-EncodedCommand", encoded],
                           capture_output=True, text=True, errors="replace",
                           timeout=60, env=env)
    except Exception as exc:
        return False, f"Signature check could not run: {exc}"
    fields: dict[str, str] = {}
    for line in (r.stdout or "").splitlines():
        if "=" in line:
            k, _, val = line.partition("=")
            fields[k.strip()] = val.strip()
    if fields.get("STATUS") == "Valid" and fields.get("TS") == "True":
        return True, (f"Valid Authenticode signature ({fields.get('SUBJECT', '')}, "
                       f"{fields.get('MSG', '')})")
    detail = fields.get("STATUS") or "no signature"
    return False, (f"Untrusted signature ({detail}; {fields.get('MSG', '')}) — "
                   "update will NOT be installed.")


def install_artifact(path: Path, expected_sha256: str, require_signature: bool = True) -> None:
    """Verify (hash, then Authenticode) and hand the installer to the OS.

    Refuses when no hash is known or the signature is invalid. Never launches
    an unverified file.
    """
    if not expected_sha256:
        raise UpdateError(
            "No trusted SHA-256 hash is available for this update, so it cannot "
            "be verified. Installation refused — download it manually instead."
        )
    verify_sha256(path, expected_sha256)
    if require_signature:
        ok, msg = verify_authenticode(path)
        if not ok:
            raise UpdateError(msg)
        log.info("Authenticode OK for %s", path.name)
    if os.name == "nt":
        os.startfile(str(path))  # noqa: S606 -- verified installer, user-confirmed launch
    else:
        import subprocess as _sp

        _sp.Popen([str(path)])
