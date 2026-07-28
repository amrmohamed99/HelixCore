#!/usr/bin/env python3
"""Fetch and verify the Linux tool staged into Helix Core packages.

The AppImage and Debian builds bundle the official AutoDock Vina 1.2.6 Linux
release asset. The binary is intentionally not committed: this script downloads
it to ``linux-tools/`` and verifies the SHA-256 recorded in
``linux_tools_manifest.json`` before atomically installing it.

Usage:
    python scripts/fetch_linux_tools.py
    python scripts/fetch_linux_tools.py --check
    python scripts/fetch_linux_tools.py --force
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "linux_tools_manifest.json"
DEFAULT_DEST = REPO_ROOT / "linux-tools"
CHUNK_SIZE = 1 << 20
MAX_BYTES = 128 << 20
USER_AGENT = "helixcore-linux-packager/1 (+https://github.com/amrmohamed99/HelixCore)"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_tools() -> list[tuple[str, dict[str, str]]]:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != 1:
            raise ValueError("unsupported schema_version")
        tools = manifest["tools"]
        if not isinstance(tools, dict) or not tools:
            raise ValueError("tools must be a non-empty object")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"error: invalid {MANIFEST_PATH.name}: {exc}") from exc

    required = ("version", "filename", "url", "sha256")
    validated: list[tuple[str, dict[str, str]]] = []
    filenames: set[str] = set()
    for name, tool in tools.items():
        if not isinstance(name, str) or not isinstance(tool, dict):
            raise SystemExit("error: every manifest tool must be a named object")
        missing = [key for key in required if not isinstance(tool.get(key), str) or not tool[key]]
        if missing:
            raise SystemExit(f"error: manifest {name} entry is missing: {', '.join(missing)}")

        filename = Path(tool["filename"])
        if filename.name != tool["filename"] or filename.is_absolute():
            raise SystemExit(f"error: manifest filename for {name} must be a plain basename")
        if tool["filename"].casefold() in filenames:
            raise SystemExit(f"error: duplicate manifest filename: {tool['filename']}")
        filenames.add(tool["filename"].casefold())

        expected = tool["sha256"].lower()
        if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
            raise SystemExit(f"error: manifest sha256 for {name} is not hexadecimal")
        validated.append((name, tool))
    return validated


def verify(path: Path, expected: str) -> bool:
    if not path.is_file():
        print(f"missing: {path}")
        return False
    actual = sha256_file(path)
    if actual != expected:
        print(f"mismatch: {path}")
        print(f"  expected {expected}")
        print(f"  actual   {actual}")
        return False
    print(f"verified: {path} ({actual})")
    return True


def download(url: str, target: Path, expected: str, executable: bool) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{target.name}.", suffix=".part",
            dir=target.parent, delete=False,
        ) as output:
            temp_path = Path(output.name)
            digest = hashlib.sha256()
            total = 0
            with urlopen(request, timeout=60) as response:
                while chunk := response.read(CHUNK_SIZE):
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise RuntimeError(f"download exceeds {MAX_BYTES} bytes")
                    digest.update(chunk)
                    output.write(chunk)
            output.flush()
            os.fsync(output.fileno())

        actual = digest.hexdigest()
        if actual != expected:
            raise RuntimeError(f"SHA-256 mismatch: expected {expected}, got {actual}")
        if executable:
            temp_path.chmod(
                temp_path.stat().st_mode
                | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            )
        temp_path.replace(target)
        temp_path = None
        print(f"installed: {target} ({total} bytes, {actual})")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="verify the staged binary without downloading",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="download again even when the staged binary verifies",
    )
    parser.add_argument(
        "--dest", type=Path, default=DEFAULT_DEST,
        help=f"staging directory (default: {DEFAULT_DEST})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tools = load_tools()
    destination = args.dest.resolve()

    if args.check:
        results = [
            verify(destination / tool["filename"], tool["sha256"].lower())
            for _name, tool in tools
        ]
        return 0 if all(results) else 1

    for name, tool in tools:
        target = destination / tool["filename"]
        expected = tool["sha256"].lower()
        if not args.force and verify(target, expected):
            continue

        print(f"downloading {name} {tool['version']} for Linux x64")
        download(tool["url"], target, expected, bool(tool.get("executable", False)))

    results = [
        verify(destination / tool["filename"], tool["sha256"].lower())
        for _name, tool in tools
    ]
    return 0 if all(results) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
