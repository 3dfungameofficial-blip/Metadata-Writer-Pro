"""Release version consistency gate (used by CI and locally).

Ensures APP_VERSION == pyproject version == installer MyAppVersion == git tag.
Usage: python tools/check_version.py [v1.2.3]
Exits non-zero on any mismatch.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from metadata_writer_pro.app import APP_VERSION  # noqa: E402


def _fail(msg: str) -> int:
    print(f"VERSION MISMATCH: {msg}", file=sys.stderr)
    return 1


def main(tag: str | None = None) -> int:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproject)
    if not m:
        return _fail("no version in pyproject.toml")
    if m.group(1) != APP_VERSION:
        return _fail(f"pyproject {m.group(1)} != APP_VERSION {APP_VERSION}")

    iss = (ROOT / "installer" / "setup.iss").read_text(encoding="utf-8")
    m2 = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', iss)
    if not m2:
        return _fail("no MyAppVersion in setup.iss")
    if m2.group(1) != APP_VERSION:
        return _fail(f"setup.iss {m2.group(1)} != APP_VERSION {APP_VERSION}")

    tag = tag or os.environ.get("GITHUB_REF_NAME", "")
    if tag:
        if tag.lstrip("vV") != APP_VERSION:
            return _fail(f"git tag {tag} != APP_VERSION {APP_VERSION}")
    print(f"Version consistent: {APP_VERSION}" + (f" (tag {tag})" if tag else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
