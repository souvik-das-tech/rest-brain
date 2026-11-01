"""Filesystem locations. Runtime data (AGY workspace, logs) lives in %LOCALAPPDATA%\\Rest-Brain on
Windows and in $XDG_DATA_HOME/rest-brain (~/.local/share/rest-brain) on Linux/macOS."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Rest-Brain"


def data_dir() -> Path:
    """Override with BRAIN_DATA_DIR (used by tests)."""
    override = os.environ.get("BRAIN_DATA_DIR")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        base = Path(local) / APP_NAME
    else:
        local = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        base = Path(local) / APP_NAME.lower()
    base.mkdir(parents=True, exist_ok=True)
    return base


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
