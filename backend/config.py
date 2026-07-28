"""
Helix Core v3.0.0 — Backend Configuration
Paths, ports, and tool locations.
"""

import logging
import os
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"


def _exe(name: str) -> str:
    """Append the platform executable suffix."""
    return f"{name}.exe" if IS_WINDOWS else name


# --- Paths ---
# In dev: project root is one level up from backend/
# In prod (PyInstaller): sys._MEIPASS holds the bundle root
def _get_project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _get_project_root()
TOOLS_DIR = Path(os.environ.get("HELIX_TOOLS_DIR", str(PROJECT_ROOT / "tools")))
WORKSPACE_DIR = str(Path(os.environ.get("HELIX_WORKSPACE_DIR", str(PROJECT_ROOT / "workspace"))))

# --- Server ---
HOST = "127.0.0.1"
PORT = int(os.environ.get("HELIX_PORT", "8299"))

# --- Tool Binaries ---
def _find_binary(name: str, subdir: str = "") -> str | None:
    """Locate a binary in the tools directory."""
    search_dir = TOOLS_DIR / subdir if subdir else TOOLS_DIR
    if search_dir.exists():
        for f in search_dir.iterdir():
            if f.stem.lower().startswith(name.lower()) and f.is_file():
                return str(f)
    return None


def find_vina() -> str | None:
    """Locate the AutoDock Vina executable.

    Resolution order: HELIX_VINA override, bundled tools/, the frozen executable
    directory, then PATH. Release packages bundle Vina on Windows and Linux;
    development installs and macOS can resolve an upstream binary from PATH.
    """
    override = os.environ.get("HELIX_VINA")
    if override:
        if os.path.isfile(override):
            return override
        logger.warning("HELIX_VINA is set to %s but no such file exists", override)

    if IS_WINDOWS:
        names = ["vina.exe", "vina_1.2.6_win.exe", "vina_1.2.6_win", "vina"]
    else:
        names = ["vina", "vina_1.2.6_linux_x86_64", "vina_1.2.6_mac_x86_64"]

    search_roots = [TOOLS_DIR]
    if getattr(sys, "frozen", False):
        search_roots.append(Path(sys.executable).parent)
    for root in search_roots:
        for n in names:
            p = root / n
            if p.is_file():
                return str(p)

    on_path = shutil.which("vina")
    if on_path:
        return on_path

    logger.warning("AutoDock Vina not found in %s or on PATH — docking will be unavailable", TOOLS_DIR)
    return None


def get_obabel() -> str:
    """Locate the Open Babel executable.

    Resolution order: HELIX_OBABEL override, bundled tools/OpenBabel/, then PATH.
    Returns the bundled path even when missing so that callers keep reporting a
    concrete location in their error messages.
    """
    override = os.environ.get("HELIX_OBABEL")
    if override:
        if os.path.isfile(override):
            return override
        logger.warning("HELIX_OBABEL is set to %s but no such file exists", override)

    bundled = TOOLS_DIR / "OpenBabel" / _exe("obabel")
    if bundled.is_file():
        return str(bundled)

    on_path = shutil.which("obabel")
    if on_path:
        return on_path

    logger.warning("Open Babel not found at %s or on PATH — format conversion will fail", bundled)
    return str(bundled)


def get_babel_datadir() -> str | None:
    """Return BABEL_DATADIR for the bundled Open Babel, or None.

    The data directory is returned only when the *resolved* executable is the
    bundled one. A PATH-resolved Open Babel (conda-forge, distro package) locates
    its own data relative to its install prefix; pointing it at the bundled data
    of a different major version silently mixes incompatible element and atom-typing
    tables, and pointing it at a missing directory breaks plugin loading.
    """
    datadir = TOOLS_DIR / "OpenBabel" / "data"
    if not datadir.is_dir():
        return None

    try:
        resolved = Path(get_obabel()).resolve()
        bundled_root = (TOOLS_DIR / "OpenBabel").resolve()
        resolved.relative_to(bundled_root)
    except (ValueError, OSError):
        return None

    return str(datadir)


# --- Engine identity ---
# `vina` on PATH is not necessarily the engine the results were produced with: the
# conda-forge package reports "AutoDock Vina f458505-mod", a modified build of
# 1.2.7 whose docking scores are not comparable with the official v1.2.6 release
# assets. These are the versions backend/utils/engine_guard.py enforces against;
# the enforcement itself lives there, not here.
DEFAULT_EXPECTED_VINA = "v1.2.6"
DEFAULT_EXPECTED_OBABEL = "3.1.1"

_EXPECTED_ENGINE_ENV: dict[str, tuple[str, str]] = {
    "vina": ("HELIX_EXPECTED_VINA", DEFAULT_EXPECTED_VINA),
    "openbabel": ("HELIX_EXPECTED_OBABEL", DEFAULT_EXPECTED_OBABEL),
}

# Values that withdraw the expectation rather than override it.
_NO_EXPECTATION = frozenset({"", "any", "*", "none"})

ENGINE_CHECK_ENV = "HELIX_ENGINE_CHECK"
_FALSEY = frozenset({"0", "false", "no", "off", "skip", "disabled"})


def expected_engine_version(engine: str) -> str | None:
    """Return the declared version for ``engine`` ("vina" or "openbabel").

    The environment variable overrides the shipped default. Setting it to an empty
    value, "any", "*" or "none" withdraws the expectation entirely and returns
    None — which silences the startup warning but is *refused* by a measurement
    run, because an unverifiable engine is not a verified one.
    """
    try:
        env_var, default = _EXPECTED_ENGINE_ENV[engine]
    except KeyError:
        raise ValueError(
            f"unknown engine {engine!r}; expected one of {sorted(_EXPECTED_ENGINE_ENV)}"
        ) from None

    raw = os.environ.get(env_var)
    if raw is None:
        return default
    value = raw.strip()
    if value.lower() in _NO_EXPECTATION:
        return None
    return value


def engine_check_enabled() -> bool:
    """Whether the *startup* engine check runs.

    Off via HELIX_ENGINE_CHECK=0 for casual, non-measurement use. Measurement runs
    ignore this deliberately: a guard that one environment variable can disable is
    not a guard.
    """
    raw = os.environ.get(ENGINE_CHECK_ENV)
    if raw is None:
        return True
    return raw.strip().lower() not in _FALSEY


# --- App Version ---
APP_VERSION = "3.0.0"
