# -*- coding: utf-8 -*-
"""Release-pipeline updater tests: API parsing, checksums chain, failures.

All network access is mocked — no live GitHub calls.
"""
import hashlib
import io
import json
import urllib.error

import pytest

from metadata_writer_pro.app.services import updater as U

EXE = "https://github.com/3dfungameofficial-blip/Metadata-Writer-Pro/releases/download/v1.1.0/MetadataWriterPro-Setup.exe"
SUMS = "https://github.com/3dfungameofficial-blip/Metadata-Writer-Pro/releases/download/v1.1.0/SHA256SUMS.txt"
PAYLOAD = hashlib.sha256(b"installer-bytes").hexdigest()


def _release(tag="v1.1.0", assets=("exe", "sums")):
    items = []
    if "exe" in assets:
        items.append({"name": "MetadataWriterPro-Setup.exe", "browser_download_url": EXE})
    if "sums" in assets:
        items.append({"name": "SHA256SUMS.txt", "browser_download_url": SUMS})
    return {"tag_name": tag, "body": "• fix\n• feat", "assets": items}


class FakeResp:
    def __init__(self, data: bytes, headers=None):
        self._buf = io.BytesIO(data)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self._buf.read(n)


def _fake_urlopen(mapping):
    def _open(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url not in mapping:
            raise AssertionError(f"unexpected URL: {url}")
        item = mapping[url]
        if isinstance(item, Exception):
            raise item
        return item
    return _open


def _api(body: bytes):
    return {U.UPDATE_CHECK_URL: FakeResp(body)}


def test_update_available_with_hash_chain(monkeypatch):
    sums = f"{PAYLOAD}  MetadataWriterPro-Setup.exe\n".encode()
    m = _api(json.dumps(_release()).encode())
    m[SUMS] = FakeResp(sums)
    monkeypatch.setattr(U.urllib.request, "urlopen", _fake_urlopen(m))
    info = U.check_for_updates()
    assert info is not None
    assert info.version == "1.1.0" and info.tag == "v1.1.0"
    assert info.installer_url == EXE
    assert info.sha256 == PAYLOAD
    assert "fix" in info.notes


def test_no_update_when_same_version(monkeypatch):
    m = _api(json.dumps(_release(tag="v1.0.0")).encode())
    monkeypatch.setattr(U.urllib.request, "urlopen", _fake_urlopen(m))
    assert U.check_for_updates() is None


def test_missing_installer_asset_yields_unusable_release(monkeypatch):
    m = _api(json.dumps(_release(assets=("sums",))).encode())
    monkeypatch.setattr(U.urllib.request, "urlopen", _fake_urlopen(m))
    info = U.check_for_updates()
    assert info is not None and info.installer_url == ""
    with pytest.raises(U.UpdateError):
        U.download_update(info, __import__("pathlib").Path("x.exe"))


def test_missing_checksums_means_no_hash(monkeypatch):
    m = _api(json.dumps(_release(assets=("exe",))).encode())
    monkeypatch.setattr(U.urllib.request, "urlopen", _fake_urlopen(m))
    info = U.check_for_updates()
    assert info is not None and info.sha256 == ""


def test_malformed_and_network_failures_return_none(monkeypatch):
    monkeypatch.setattr(U.urllib.request, "urlopen", _fake_urlopen(
        {U.UPDATE_CHECK_URL: FakeResp(b"not json")}))
    assert U.check_for_updates() is None
    monkeypatch.setattr(U.urllib.request, "urlopen", _fake_urlopen(
        {U.UPDATE_CHECK_URL: urllib.error.URLError("offline")}))
    assert U.check_for_updates() is None
    monkeypatch.setattr(U.urllib.request, "urlopen", _fake_urlopen(
        {U.UPDATE_CHECK_URL: FakeResp(json.dumps({"no": "tag"}).encode())}))
    assert U.check_for_updates() is None


def test_non_https_asset_rejected(monkeypatch):
    bad = _release()
    bad["assets"][0]["browser_download_url"] = "http://evil.example/x.exe"
    m = _api(json.dumps(bad).encode())
    monkeypatch.setattr(U.urllib.request, "urlopen", _fake_urlopen(m))
    assert U.check_for_updates() is None


def _info():
    return U.ReleaseInfo(version="1.1.0", tag="v1.1.0", notes="n",
                         installer_url=EXE, installer_filename="MetadataWriterPro-Setup.exe",
                         sha256=PAYLOAD)


def test_download_verifies_and_reports_progress(monkeypatch, tmp_path):
    data = b"installer-bytes"
    seen = []
    m = {EXE: FakeResp(data, headers={"Content-Length": str(len(data))})}
    monkeypatch.setattr(U.urllib.request, "urlopen", _fake_urlopen(m))
    dest = tmp_path / "Setup.exe"
    U.download_update(_info(), dest, progress=lambda d, t: seen.append((d, t)))
    assert dest.read_bytes() == data
    assert seen and seen[-1][0] == len(data)


def test_hash_mismatch_deletes_and_refuses(monkeypatch, tmp_path):
    m = {EXE: FakeResp(b"tampered-bytes")}
    monkeypatch.setattr(U.urllib.request, "urlopen", _fake_urlopen(m))
    dest = tmp_path / "Setup.exe"
    with pytest.raises(U.UpdateError, match="verification failed"):
        U.download_update(_info(), dest)
    assert not dest.exists()


def test_oversized_download_aborted(monkeypatch, tmp_path):
    class Big(FakeResp):
        def read(self, n=-1):
            return b"z" * (U.MAX_DOWNLOAD_BYTES + 1)
    m = {EXE: Big(b"")}
    monkeypatch.setattr(U.urllib.request, "urlopen", _fake_urlopen(m))
    with pytest.raises(U.UpdateError, match="[Ss]afety cap"):
        U.download_update(_info(), tmp_path / "Setup.exe")


def test_interrupted_download_reports(monkeypatch, tmp_path):
    m = {EXE: urllib.error.URLError("connection reset")}
    monkeypatch.setattr(U.urllib.request, "urlopen", _fake_urlopen(m))
    with pytest.raises(U.UpdateError, match="[Ii]nterrupted"):
        U.download_update(_info(), tmp_path / "Setup.exe")


def test_unsigned_installer_never_launches(tmp_path, monkeypatch):
    fake = tmp_path / "Setup.exe"
    fake.write_bytes(b"MZ-unsigned")
    monkeypatch.setattr(U, "verify_sha256", lambda p, h: True)
    monkeypatch.setattr(U, "verify_authenticode", lambda p: (False, "NotSigned"))
    launched = []
    monkeypatch.setattr(U.os, "startfile", lambda p: launched.append(p), raising=False)
    with pytest.raises(U.UpdateError, match="[Ss]ign"):
        U.install_artifact(fake, "ab" * 32)
    assert launched == []


def test_parse_checksums_variants():
    text = "# comment\n" + "AB" * 32 + " *MetadataWriterPro-Setup.exe\n" + "cd" * 32 + "  other.zip\n"
    assert U.parse_checksums(text, "metadatawriterpro-setup.exe") == ("ab" * 32)
    assert U.parse_checksums(text, "missing.exe") == ""
    assert U.parse_checksums("notahash  MetadataWriterPro-Setup.exe\n", "MetadataWriterPro-Setup.exe") == ""


import os as _os

needs_windows = pytest.mark.skipif(_os.name != "nt", reason="Authenticode is Windows-only")


@needs_windows
def test_authenticode_trusts_platform_signed_binary():
    ok, msg = U.verify_authenticode(__import__("pathlib").Path(r"C:\Windows\System32\notepad.exe"))
    assert ok, msg


@needs_windows
def test_authenticode_rejects_unsigned_file(tmp_path):
    fake = tmp_path / "unsigned.exe"
    fake.write_bytes(b"MZ" + b"\x00" * 64)
    ok, msg = U.verify_authenticode(fake)
    assert not ok
    assert "NOT be installed" in msg
