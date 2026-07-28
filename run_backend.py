"""
Helix Core v3.0 — Backend entry point.

Production entry point for either Nuitka-compiled or development runs.
Configures crash logging before starting the FastAPI server.
"""

import sys
import os

# When frozen (Nuitka --standalone or PyInstaller), add bundle root to sys.path
if getattr(sys, "frozen", False):
    base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    if base not in sys.path:
        sys.path.insert(0, base)

    # Set HELIX_TOOLS_DIR if not already set by Electron
    if "HELIX_TOOLS_DIR" not in os.environ:
        exe_dir = os.path.dirname(sys.executable)
        tools_candidate = os.path.join(exe_dir, "..", "tools")
        if os.path.isdir(tools_candidate):
            os.environ["HELIX_TOOLS_DIR"] = os.path.abspath(tools_candidate)

import uvicorn


def main() -> None:
    """Start the FastAPI server."""
    from backend.utils.guard import setup_crash_logging, logger
    setup_crash_logging()

    from backend.config import HOST, PORT
    host = os.environ.get("HELIX_HOST", HOST)
    port = int(os.environ.get("HELIX_PORT", str(PORT)))
    logger.info("Starting Helix Core backend on %s:%d", host, port)
    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        log_level="info",
    )

if __name__ == "__main__":
    main()
