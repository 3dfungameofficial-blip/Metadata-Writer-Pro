"""Central logging: console + rotating app.log + per-run processing logs."""
from __future__ import annotations

import datetime as _dt
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_configured = False
_processing_file: Path | None = None
_processing_handler: logging.Handler | None = None


def setup_logging(level: str = "INFO") -> Path:
    """Configure root logging. Returns the logs directory."""
    global _configured
    from metadata_writer_pro.app.utils import paths as _paths

    logdir = _paths.logs_dir()
    if _configured:
        return logdir
    numeric = getattr(logging, str(level).upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")

    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(numeric)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    fh = RotatingFileHandler(logdir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setLevel(numeric)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    _configured = True
    return logdir


def start_processing_log() -> Path:
    """Create a timestamped processing log file and attach it for this run."""
    global _processing_file, _processing_handler
    from metadata_writer_pro.app.utils import paths as _paths

    setup_logging()
    logger = logging.getLogger("processing")
    # Detach the previous run's handler: no duplicate lines, no FD leak.
    if _processing_handler is not None:
        logger.removeHandler(_processing_handler)
        try:
            _processing_handler.close()
        except Exception:
            pass
        _processing_handler = None
    stamp = _dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    _processing_file = _paths.logs_dir() / f"processing-{stamp}.log"
    _processing_handler = logging.FileHandler(_processing_file, encoding="utf-8")
    _processing_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s"))
    logger.addHandler(_processing_handler)
    logger.setLevel(logging.INFO)
    return _processing_file


def get_logger(name: str) -> logging.Logger:
    if not _configured:
        setup_logging()
    return logging.getLogger(name)
