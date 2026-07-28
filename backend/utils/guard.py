"""
Helix Core — Crash/diagnostic logging setup.
"""

import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("helix.guard")


# ---------------------------------------------------------------------------
#  App data directory
# ---------------------------------------------------------------------------

def _get_appdata_dir() -> Path:
    """Return a per-user application data directory, creating it if necessary."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / "HelixCore"
    d.mkdir(parents=True, exist_ok=True)
    return d


APPDATA_DIR = _get_appdata_dir()
LOG_DIR = APPDATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
#  Crash logging
# ---------------------------------------------------------------------------

def setup_crash_logging() -> Path:
    """Configure file-based logging to <appdata>/HelixCore/logs/."""
    log_file = LOG_DIR / f"helix_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.DEBUG)
    logger.info("Helix Core starting — log file: %s", log_file)
    return log_file
