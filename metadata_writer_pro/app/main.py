"""Application entry point (development mode: python -m metadata_writer_pro).

CLI (also works in the packaged .exe for headless verification):
  --version     print version and exit
  --self-test   headless end-to-end check (JPG + MP4 + MOV + CSV + rename),
                writes JSON result, exits 0 on success / 1 on failure.
"""
from __future__ import annotations

import json
import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--version" in args or "-V" in args:
        from metadata_writer_pro.app import APP_NAME, APP_VERSION

        print(f"{APP_NAME} {APP_VERSION}")
        return 0
    if "--help" in args or "-h" in args:
        print("Metadata Writer Pro\n\n"
              "  python -m metadata_writer_pro [--version] [--self-test [output.json]]\n")
        return 0
    if "--self-test" in args:
        from metadata_writer_pro.app.selftest import run_self_test

        out = None
        try:
            idx = args.index("--self-test")
            nxt = args[idx + 1] if idx + 1 < len(args) else None
            if nxt and not nxt.startswith("-"):
                out = nxt
        except Exception:
            out = None
        report = run_self_test(out)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok") else 1

    from metadata_writer_pro.app.services.logger import setup_logging
    from metadata_writer_pro.app.ui.main_window import run_app

    setup_logging()
    run_app()
    return 0


if __name__ == "__main__":
    sys.exit(main())
