"""Friendly error mapping: never show raw tracebacks in the UI."""
from __future__ import annotations

import errno
import os


def friendly_error(exc: BaseException, filename: str = "") -> str:
    prefix = f"'{filename}': " if filename else ""
    if isinstance(exc, FileNotFoundError):
        return f"{prefix}File not found. It may have been moved or renamed after CSV validation."
    if isinstance(exc, PermissionError):
        return (
            f"{prefix}Could not modify the file. It may be open in another "
            "application (Premiere, VLC, Explorer preview). Close it and try again."
        )
    if isinstance(exc, OSError):
        if exc.errno in (errno.EACCES, errno.EBUSY, 32):  # 32 = Windows sharing violation
            return (
                f"{prefix}File is locked by another application. "
                "Close it and try again."
            )
        return f"{prefix}Filesystem error: {exc.strerror or exc}"
    msg = str(exc).strip()
    if "ffmpeg" in msg.lower() and "not found" in msg.lower():
        return (
            "FFmpeg is unavailable, so video metadata cannot be written. "
            "Reinstall the application or place ffmpeg on PATH."
        )
    # Keep technical detail out of the headline; full traceback goes to logs.
    short = (msg.splitlines() or ["Unknown error"])[0][:300]
    return f"{prefix}{short}" if short else f"{prefix}Unexpected error."


def csv_error(message: str, hint: str = "") -> str:
    base = f"CSV validation failed.\n\n{message}"
    if hint:
        base += f"\n\n{hint}"
    return base
