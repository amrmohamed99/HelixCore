"""
Path utilities for locating tools and setting up environment.
"""

import os
from backend.config import TOOLS_DIR, get_obabel, get_babel_datadir


def get_obabel_env() -> dict[str, str]:
    """Return an environment dict for invoking Open Babel.

    BABEL_DATADIR is set only when a bundled data directory exists. A PATH-resolved
    Open Babel resolves its own data relative to its install prefix, and pointing
    BABEL_DATADIR at a missing directory makes it fail to load its plugins.
    """
    env = os.environ.copy()
    datadir = get_babel_datadir()
    if datadir:
        env["BABEL_DATADIR"] = datadir
    else:
        env.pop("BABEL_DATADIR", None)
    return env
