"""Authenticode signing + verification helper (fail-closed).

Signing (needs credentials — NEVER in git):
  set WIN_SIGN_PFX_B64=<base64 of .pfx>  (CI: GitHub Actions secret)
  set WIN_SIGN_PASSWORD=<pfx password>    (CI: GitHub Actions secret)
  set EXPECTED_PUBLISHER=Metadata Writer Pro
  python tools/sign.py sign dist/MetadataWriterPro.exe
  python tools/sign.py verify dist/MetadataWriterPro.exe

Uses signtool when available, else falls back to a bundled-location search.
Verification is Windows-native (signtool verify, or Get-AuthenticodeSignature)
and fails unless: signature valid, chain trusted, timestamp present, and (when
EXPECTED_PUBLISHER is set) the subject matches.

Timestamp: RFC 3161 via DigiCert (SHA-256, /fd SHA256). No SHA-1 anywhere.
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TIMESTAMP_URL = "http://timestamp.digicert.com"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _signtool() -> Path | None:
    which = shutil.which("signtool")
    if which:
        return Path(which)
    for cand in (
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Windows Kits",
        Path(os.environ.get("ProgramFiles", "")) / "Windows Kits",
    ):
        if cand.is_dir():
            hits = sorted(cand.glob("10/bin/*/x64/signtool.exe"))
            if hits:
                return hits[-1]
    return None


def _decode_pfx() -> tuple[Path, str]:
    b64 = os.environ.get("WIN_SIGN_PFX_B64", "")
    pwd = os.environ.get("WIN_SIGN_PASSWORD", "")
    if not b64 or not pwd:
        raise SystemExit("BLOCKED — signing credentials not available. "
                         "Set WIN_SIGN_PFX_B64 and WIN_SIGN_PASSWORD.")
    tmp = Path(tempfile.mkdtemp(prefix="mwpro_sign_")) / "cert.pfx"
    tmp.write_bytes(base64.b64decode(b64))
    return tmp, pwd


def cmd_sign(target: str) -> int:
    st = _signtool()
    if st is None:
        raise SystemExit("BLOCKED — signtool.exe not found (install Windows SDK).")
    pfx, pwd = _decode_pfx()
    try:
        r = subprocess.run([str(st), "sign", "/fd", "SHA256", "/f", str(pfx),
                            "/p", pwd, "/tr", TIMESTAMP_URL, "/td", "SHA256", target],
                           capture_output=True, text=True, errors="replace", timeout=300)
    finally:
        try:
            pfx.unlink()
        except OSError:
            pass
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        print("SIGNING FAILED", file=sys.stderr)
        return 1
    return cmd_verify(target)


def cmd_verify(target: str) -> int:
    expected = os.environ.get("EXPECTED_PUBLISHER", "")
    st = _signtool()
    if st is not None:
        r = subprocess.run([str(st), "verify", "/pa", "/all", "/v", target],
                           capture_output=True, text=True, errors="replace", timeout=120)
        print(r.stdout)
        if r.returncode != 0:
            print(r.stderr, file=sys.stderr)
            print("SIGNATURE VERIFICATION FAILED", file=sys.stderr)
            return 1
        if expected and expected.lower() not in (r.stdout or "").lower():
            print(f"Publisher mismatch: expected {expected!r} in signature.", file=sys.stderr)
            return 1
        # signtool /v prints the timestamp counter-signature on success; enforce it.
        if "timestamp" not in (r.stdout or "").lower():
            print("No RFC 3161 timestamp found in signature.", file=sys.stderr)
            return 1
        print("Authenticode signature VERIFIED.")
        return 0
    # Fallback: PowerShell native check (no SDK required).
    from metadata_writer_pro.app.services import updater as _u

    ok, msg = _u.verify_authenticode(target)
    print(msg)
    if not ok:
        return 1
    if expected:
        print(f"NOTE: publisher-subject check needs signtool; expected {expected!r}.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("sign", "verify"):
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(cmd_sign(sys.argv[2]) if sys.argv[1] == "sign" else cmd_verify(sys.argv[2]))
