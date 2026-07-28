#!/usr/bin/env python3
"""Fetch and verify the Helix Core Windows tool bundle (AutoDock Vina + Open Babel).

Why this script exists
----------------------
``tools/`` holds ~32 MB of prebuilt Windows executables, one of which (Open Babel)
is GPL-2.0. They are deliberately **not** tracked in git: nothing in CI, Docker,
PyInstaller, or the test suite reads them (the Linux image fetches Vina from
upstream by SHA-256 and takes Open Babel from conda-forge, and
``backend/config.py`` falls back to ``PATH``). Their only consumers are Windows
runtime resolution and the electron-builder ``win.extraResources`` step, which
maps ``../tools`` -> ``tools``.

So the bundle ships as a versioned GitHub Release asset instead, and this script
puts it back on disk for a fresh Windows clone. Every file is checked against a
SHA-256 recorded in ``tools_manifest.json`` **before** anything is written, so a
tampered or truncated asset can never land in the tree.

Guarantees
----------
* **Idempotent** — if ``tools/`` already matches the manifest, this is a no-op.
* **Verify-before-unpack** — each archive member is hashed while streaming from
  the zip; extraction only starts once every entry matches.
* **Fails loudly** — any mismatch, missing entry, or unexpected member aborts
  with a non-zero exit and nothing is written.
* **Stdlib only** — no pip install needed to bootstrap a checkout.
* **No path traversal** — destination paths come from the manifest, never from
  the archive's own member names.

Usage
-----
    python scripts/fetch_tools.py                 # ensure tools/ is present and valid
    python scripts/fetch_tools.py --check         # verify only, never download (CI gate)
    python scripts/fetch_tools.py --force         # re-fetch even if already valid
    python scripts/fetch_tools.py --archive B.zip # install from an already-downloaded asset
    python scripts/fetch_tools.py --url URL       # override the download location
    python scripts/fetch_tools.py --pack B.zip    # build the release asset from tools/
    python scripts/fetch_tools.py --write-manifest  # re-record hashes from tools/ on disk

Environment overrides: ``HELIX_TOOLS_DIR`` (destination, same variable
``backend/config.py`` honours), ``HELIX_TOOLS_ARCHIVE`` (local asset path),
``HELIX_TOOLS_URL`` (download location).

Exit codes: 0 success, 1 verification failed, 2 usage/manifest error,
3 download failed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "tools_manifest.json"
DEFAULT_DEST = REPO_ROOT / "tools"

CHUNK = 1 << 20  # 1 MiB
MAX_ARCHIVE_BYTES = 512 << 20  # refuse absurdly large downloads / zip bombs
USER_AGENT = "helixcore-fetch-tools/1 (+https://github.com/amrmohamed99/HelixCore)"

EXIT_OK = 0
EXIT_VERIFY_FAILED = 1
EXIT_USAGE = 2
EXIT_DOWNLOAD_FAILED = 3


class ToolsError(Exception):
    """Any condition that must abort the fetch."""


class VerificationError(ToolsError):
    """A file did not match its recorded SHA-256, or is missing/unexpected."""


# --------------------------------------------------------------------------- #
# Hashing helpers                                                              #
# --------------------------------------------------------------------------- #


def sha256_file(path: Path) -> tuple[str, int]:
    """Return ``(hexdigest, byte_count)`` for a file on disk."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def sha256_stream(stream, limit: int) -> tuple[str, int]:
    """Hash a stream, refusing to read more than ``limit`` bytes.

    The cap matters for archive members: an attacker-supplied zip can claim a
    small compressed size and expand to gigabytes. We know the expected size
    from the manifest, so anything larger is a failure by definition.
    """
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = stream.read(CHUNK)
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise VerificationError(
                f"archive member expands past its recorded size of {limit} bytes"
            )
        digest.update(chunk)
    return digest.hexdigest(), size


def human_bytes(count: int) -> str:
    value = float(count)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GiB"


# --------------------------------------------------------------------------- #
# Manifest                                                                     #
# --------------------------------------------------------------------------- #


def safe_relpath(rel: str) -> PurePosixPath:
    """Validate a manifest path: relative, POSIX, no traversal, no drive letter."""
    if not rel or rel.startswith("/") or "\\" in rel or ":" in rel:
        raise ToolsError(f"unsafe path in manifest: {rel!r}")
    parts = PurePosixPath(rel).parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ToolsError(f"unsafe path in manifest: {rel!r}")
    return PurePosixPath(rel)


def load_manifest(path: Path) -> dict:
    if not path.is_file():
        raise ToolsError(f"manifest not found: {path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ToolsError(f"manifest is not valid JSON: {exc}") from exc

    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ToolsError(f"manifest has no 'files' section: {path}")

    for rel, meta in files.items():
        safe_relpath(rel)
        digest = (meta or {}).get("sha256", "")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ToolsError(f"manifest entry {rel!r} has no valid sha256")
        if not isinstance((meta or {}).get("bytes"), int):
            raise ToolsError(f"manifest entry {rel!r} has no byte count")
    return manifest


def manifest_entries(manifest: dict) -> list[tuple[str, str, int]]:
    """Return ``[(relpath, sha256, bytes)]`` sorted by path."""
    return sorted(
        (rel, meta["sha256"].lower(), meta["bytes"])
        for rel, meta in manifest["files"].items()
    )


def archive_root(manifest: dict) -> str:
    """Prefix that manifest paths carry inside the archive, e.g. ``tools/``."""
    root = str(manifest.get("bundle", {}).get("archive_root", "") or "")
    if root and not root.endswith("/"):
        root += "/"
    if root.startswith("/") or ".." in root:
        raise ToolsError(f"unsafe archive_root in manifest: {root!r}")
    return root


# --------------------------------------------------------------------------- #
# Verification of an installed tree                                            #
# --------------------------------------------------------------------------- #


def verify_installed(dest: Path, entries: Iterable[tuple[str, str, int]]) -> list[str]:
    """Check ``dest`` against the manifest. Returns a list of human-readable problems.

    Files present in ``dest`` but absent from the manifest are ignored on
    purpose: a developer machine may legitimately keep extra bundles beside the
    managed ones (for example the superseded ``tools/OpenBabel241/``).
    """
    problems: list[str] = []
    for rel, expected_digest, expected_size in entries:
        target = dest.joinpath(*safe_relpath(rel).parts)
        if not target.is_file():
            problems.append(f"missing: {rel}")
            continue
        actual_size = target.stat().st_size
        if actual_size != expected_size:
            problems.append(
                f"size mismatch: {rel} (expected {expected_size} bytes, found {actual_size})"
            )
            continue
        actual_digest, _ = sha256_file(target)
        if actual_digest != expected_digest:
            problems.append(
                f"sha256 mismatch: {rel}\n"
                f"    expected {expected_digest}\n"
                f"    found    {actual_digest}"
            )
    return problems


# --------------------------------------------------------------------------- #
# Archive verification and extraction                                          #
# --------------------------------------------------------------------------- #


def verify_archive(
    zip_path: Path, entries: list[tuple[str, str, int]], root: str
) -> None:
    """Hash every manifest entry inside the archive. Raises on the first problem.

    Nothing is written to disk here. The archive is also rejected if it carries
    members the manifest does not describe, so an asset cannot smuggle in extra
    executables alongside the expected ones.
    """
    expected = {root + rel: (digest, size) for rel, digest, size in entries}
    with zipfile.ZipFile(zip_path) as archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        names = {info.filename for info in members}

        unexpected = sorted(names - set(expected))
        if unexpected:
            preview = "\n    ".join(unexpected[:10])
            more = f"\n    ... and {len(unexpected) - 10} more" if len(unexpected) > 10 else ""
            raise VerificationError(
                f"archive contains {len(unexpected)} file(s) not listed in the manifest:"
                f"\n    {preview}{more}"
            )

        missing = sorted(set(expected) - names)
        if missing:
            preview = "\n    ".join(missing[:10])
            more = f"\n    ... and {len(missing) - 10} more" if len(missing) > 10 else ""
            raise VerificationError(
                f"archive is missing {len(missing)} file(s) the manifest requires:"
                f"\n    {preview}{more}"
            )

        for info in members:
            digest_expected, size_expected = expected[info.filename]
            if info.create_system == 3 and (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise VerificationError(f"archive member is a symlink: {info.filename}")
            with archive.open(info) as member:
                digest_actual, size_actual = sha256_stream(member, size_expected)
            if size_actual != size_expected or digest_actual != digest_expected:
                raise VerificationError(
                    f"archive member does not match the manifest: {info.filename}\n"
                    f"    expected sha256 {digest_expected} ({size_expected} bytes)\n"
                    f"    found    sha256 {digest_actual} ({size_actual} bytes)"
                )


def install_archive(
    zip_path: Path, dest: Path, entries: list[tuple[str, str, int]], root: str
) -> None:
    """Unpack a *already verified* archive into ``dest`` via a staging directory.

    Destination paths are rebuilt from the manifest, never taken from the
    archive, so a crafted member name cannot escape ``dest``.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".helix-tools-", dir=str(dest.parent)))
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for rel, _digest, _size in entries:
                staged = staging.joinpath(*safe_relpath(rel).parts)
                staged.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(root + rel) as member, staged.open("wb") as out:
                    shutil.copyfileobj(member, out, CHUNK)

        for rel, _digest, _size in entries:
            target = dest.joinpath(*safe_relpath(rel).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging.joinpath(*safe_relpath(rel).parts), target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def pack_archive(
    src: Path, out_path: Path, entries: list[tuple[str, str, int]], root: str
) -> None:
    """Build the release asset from a local ``tools/`` directory.

    Deterministic: entries are sorted, timestamps fixed, so two runs over the
    same inputs produce byte-identical archives.
    """
    problems = verify_installed(src, entries)
    if problems:
        raise VerificationError(
            "refusing to pack — the source tree does not match the manifest:\n  "
            + "\n  ".join(problems)
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for rel, _digest, _size in entries:
            info = zipfile.ZipInfo(filename=root + rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0  # FAT/NTFS: no POSIX mode bits to disagree about
            info.external_attr = 0o100644 << 16
            source = src.joinpath(*safe_relpath(rel).parts)
            with source.open("rb") as handle, archive.open(info, "w") as member:
                shutil.copyfileobj(handle, member, CHUNK)


# --------------------------------------------------------------------------- #
# Download                                                                     #
# --------------------------------------------------------------------------- #


def download(url: str, out_path: Path) -> int:
    """Stream ``url`` to ``out_path``. Returns the byte count."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    show_progress = sys.stderr.isatty()
    received = 0
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            total = int(response.headers.get("Content-Length") or 0)
            with out_path.open("wb") as handle:
                while True:
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > MAX_ARCHIVE_BYTES:
                        raise ToolsError(
                            f"download exceeded the {human_bytes(MAX_ARCHIVE_BYTES)} safety cap"
                        )
                    handle.write(chunk)
                    if show_progress:
                        if total:
                            pct = 100.0 * received / total
                            sys.stderr.write(
                                f"\r  downloading  {human_bytes(received)} / "
                                f"{human_bytes(total)}  ({pct:5.1f}%)"
                            )
                        else:
                            sys.stderr.write(f"\r  downloading  {human_bytes(received)}")
                        sys.stderr.flush()
    except urllib.error.HTTPError as exc:
        raise ToolsError(
            f"HTTP {exc.code} fetching {url}\n"
            "  If this is a 404, the release asset for this manifest may not be "
            "published yet.\n"
            "  Options: pass --url for a different location, pass --archive with a "
            "locally\n  downloaded copy, or build the asset from an existing tools/ "
            "directory with --pack."
        ) from exc
    except urllib.error.URLError as exc:
        raise ToolsError(f"network error fetching {url}: {exc.reason}") from exc
    finally:
        if show_progress:
            sys.stderr.write("\n")
            sys.stderr.flush()
    return received


# --------------------------------------------------------------------------- #
# Manifest generation                                                          #
# --------------------------------------------------------------------------- #


def path_matches(rel: str, pattern: str) -> bool:
    """A pattern is a directory prefix (``OpenBabel/``), an exact path, or a glob."""
    if pattern.endswith("/"):
        return rel.startswith(pattern)
    return rel == pattern or PurePosixPath(rel).match(pattern)


def collect_files(src: Path, include: list[str], exclude: list[str]) -> list[str]:
    """Walk ``src`` and return POSIX-relative paths, honouring include/exclude patterns."""
    found: list[str] = []
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src).as_posix()
        if include and not any(path_matches(rel, pat) for pat in include):
            continue
        if any(path_matches(rel, pat) for pat in exclude):
            continue
        found.append(rel)
    return found


def write_manifest(src: Path, manifest_path: Path) -> dict:
    """Re-record every file hash from ``src`` into the manifest, preserving metadata."""
    manifest: dict = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ToolsError(
                f"refusing to overwrite {manifest_path}: it is not valid JSON ({exc})"
            ) from exc

    bundle = manifest.setdefault("bundle", {})
    include = list(bundle.get("include", []))
    exclude = list(bundle.get("exclude", []))

    files: dict[str, dict] = {}
    total = 0
    for rel in collect_files(src, include, exclude):
        digest, size = sha256_file(src.joinpath(*PurePosixPath(rel).parts))
        files[rel] = {"sha256": digest, "bytes": size}
        total += size

    manifest["files"] = dict(sorted(files.items()))
    bundle["file_count"] = len(files)
    bundle["total_bytes"] = total
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fetch_tools.py",
        description=(
            "Fetch and verify the Helix Core Windows tool bundle "
            "(AutoDock Vina + Open Babel) described by tools_manifest.json."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dest", type=Path, default=None, help="destination directory (default: <repo>/tools)")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH, help="manifest to verify against")
    parser.add_argument("--url", default=None, help="download location (overrides the manifest)")
    parser.add_argument("--archive", type=Path, default=None, help="install from this local asset instead of downloading")
    parser.add_argument("--check", action="store_true", help="verify only; never download. Non-zero exit if invalid")
    parser.add_argument("--force", action="store_true", help="re-fetch even if the destination already verifies")
    parser.add_argument("--keep-archive", type=Path, default=None, help="save the downloaded asset to this path")
    parser.add_argument("--pack", type=Path, default=None, help="build the release asset from --dest and exit")
    parser.add_argument("--write-manifest", action="store_true", help="re-record hashes from --dest into the manifest and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Keep progress on stdout interleaved correctly with errors on stderr when
    # the output is piped (stdout would otherwise be block-buffered).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    dest = args.dest or Path(os.environ.get("HELIX_TOOLS_DIR", str(DEFAULT_DEST)))
    dest = dest.resolve()

    if args.write_manifest:
        if not dest.is_dir():
            print(f"error: {dest} does not exist — nothing to hash", file=sys.stderr)
            return EXIT_USAGE
        try:
            manifest = write_manifest(dest, args.manifest)
        except ToolsError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_USAGE
        bundle = manifest.get("bundle", {})
        print(
            f"wrote {args.manifest} — {bundle.get('file_count')} files, "
            f"{human_bytes(bundle.get('total_bytes', 0))}"
        )
        return EXIT_OK

    try:
        manifest = load_manifest(args.manifest)
        entries = manifest_entries(manifest)
        root = archive_root(manifest)
    except ToolsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    bundle = manifest.get("bundle", {})
    total_bytes = sum(size for _rel, _digest, size in entries)

    if args.pack is not None:
        out_path = args.pack.resolve()
        try:
            pack_archive(dest, out_path, entries, root)
        except ToolsError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_VERIFY_FAILED
        digest, size = sha256_file(out_path)
        print(f"packed {len(entries)} files into {out_path}  ({human_bytes(size)})")
        print(f"  sha256 {digest}")
        print("  record this as bundle.archive_sha256 in the manifest once uploaded")
        return EXIT_OK

    # --- Already installed and valid? Then we are done. ---------------------
    if dest.is_dir() and not args.force:
        problems = verify_installed(dest, entries)
        if not problems:
            print(
                f"tools are present and verified: {len(entries)} files, "
                f"{human_bytes(total_bytes)} in {dest}"
            )
            return EXIT_OK
        if args.check:
            print(f"error: {dest} does not match {args.manifest.name}:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            print(
                "\nRun 'python scripts/fetch_tools.py' to restore the bundle.",
                file=sys.stderr,
            )
            return EXIT_VERIFY_FAILED
        print(f"{len(problems)} problem(s) with the existing {dest}; re-fetching:")
        for problem in problems[:5]:
            print(f"  {problem}")
        if len(problems) > 5:
            print(f"  ... and {len(problems) - 5} more")
    elif args.check:
        print(f"error: {dest} does not exist. Run 'python scripts/fetch_tools.py'.", file=sys.stderr)
        return EXIT_VERIFY_FAILED

    # --- Obtain the asset ---------------------------------------------------
    local_archive = args.archive or (
        Path(os.environ["HELIX_TOOLS_ARCHIVE"]) if os.environ.get("HELIX_TOOLS_ARCHIVE") else None
    )
    url = args.url or os.environ.get("HELIX_TOOLS_URL") or bundle.get("url")

    temp_dir: str | None = None
    try:
        if local_archive is not None:
            archive_path = local_archive.resolve()
            if not archive_path.is_file():
                print(f"error: archive not found: {archive_path}", file=sys.stderr)
                return EXIT_USAGE
            print(f"using local archive {archive_path}")
        else:
            if not url:
                print(
                    "error: no download URL. The manifest has no bundle.url — pass --url "
                    "or --archive.",
                    file=sys.stderr,
                )
                return EXIT_USAGE
            temp_dir = tempfile.mkdtemp(prefix="helix-tools-dl-")
            archive_path = Path(temp_dir) / (bundle.get("asset") or "tools.zip")
            print(f"fetching {url}")
            try:
                download(url, archive_path)
            except ToolsError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return EXIT_DOWNLOAD_FAILED

        # Optional whole-archive pin. Absent (null) until the asset is published,
        # at which point the per-file digests below are still the real boundary.
        archive_digest, archive_size = sha256_file(archive_path)
        pinned = bundle.get("archive_sha256")
        if pinned:
            if archive_digest != str(pinned).lower():
                print(
                    "error: archive sha256 does not match the manifest\n"
                    f"    expected {pinned}\n"
                    f"    found    {archive_digest}",
                    file=sys.stderr,
                )
                return EXIT_VERIFY_FAILED
        else:
            print(
                f"note: bundle.archive_sha256 is not pinned; verifying the "
                f"{len(entries)} per-file digests instead"
            )
            print(f"      this archive is sha256 {archive_digest} ({human_bytes(archive_size)})")

        print(f"verifying {len(entries)} files before unpacking")
        try:
            verify_archive(archive_path, entries, root)
        except ToolsError as exc:
            print(f"error: {exc}", file=sys.stderr)
            print("nothing was written.", file=sys.stderr)
            return EXIT_VERIFY_FAILED

        print(f"unpacking into {dest}")
        try:
            install_archive(archive_path, dest, entries, root)
        except OSError as exc:
            print(f"error: could not write into {dest}: {exc}", file=sys.stderr)
            return EXIT_VERIFY_FAILED

        problems = verify_installed(dest, entries)
        if problems:
            print("error: post-install verification failed:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return EXIT_VERIFY_FAILED

        if args.keep_archive is not None:
            args.keep_archive.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(archive_path, args.keep_archive)
            print(f"kept a copy of the asset at {args.keep_archive}")
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)

    print(f"done: {len(entries)} files, {human_bytes(total_bytes)} verified in {dest}")
    for component in manifest.get("components", []):
        notice = component.get("license_file")
        if notice:
            print(
                f"  {component.get('name')} {component.get('version')} "
                f"({component.get('license')}) — see {dest / notice}"
            )
    return EXIT_OK


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        raise SystemExit(130)
