#!/usr/bin/env python3
"""
secret_scan.py — pre-publication credential sweep for Helix Core.

Purpose
-------
Helix Core is being published as a fresh public repository with a single clean
commit built from the reviewed tree. Once that commit is public it cannot be
un-published, so every byte that enters it has to be checked first. This script
is that check.

It scans three distinct scopes, because they can and do disagree:

``worktree``
    Every file on disk under the repository root.  Catches secrets that are not
    committed *yet* but sit one ``git add -A`` away from being committed, and
    secrets baked into build artefacts that might be uploaded as release assets.

``index``
    The staged git index — literally the blobs that ``git commit`` would write.
    This is the authoritative answer to "will this leak when I publish?"  A file
    can be sanitised on disk while the index still holds the old, dirty blob;
    ``.gitignore`` does **not** untrack an already-tracked path.

``history``
    Every blob reachable from every ref.  Off by default and slow.  Relevant
    only if history is migrated rather than discarded.

Detection strategy
------------------
1.  If ``gitleaks`` or ``trufflehog`` is on PATH, run it and fold its findings in.
2.  Always run the built-in regex engine as well.  It is not a fallback in the
    "worse but better than nothing" sense — it carries project-specific rules
    (the burned license-server key, ``VITE_`` build-time keys) that no generic
    scanner knows about.

The known-burned credential is matched by **SHA-256 digest, never by literal**.
Embedding the retired key in a scanner that ships in the public repository would
re-publish the very thing the scanner exists to keep out.

Exit codes
----------
0   no findings at or above the ``--fail-on`` severity
1   findings at or above ``--fail-on``
2   scanner error (bad arguments, not a git repository, ...)

Usage
-----
    python scripts/secret_scan.py                     # worktree + index, text report
    python scripts/secret_scan.py --verify-excluded   # + Phase 6.2 index exclusion audit
    python scripts/secret_scan.py --scope all         # add full history sweep
    python scripts/secret_scan.py --json scan.json    # machine-readable output
    python scripts/secret_scan.py --all-files         # do not skip artefact dirs

Stdlib only.  Python 3.8+.  Windows/macOS/Linux.
"""

from __future__ import annotations

import argparse
import bisect
import fnmatch
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- #
# Severity
# --------------------------------------------------------------------------- #

CRITICAL = "CRITICAL"
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"
INFO = "INFO"

SEVERITY_ORDER = {CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1, INFO: 0}


# --------------------------------------------------------------------------- #
# Known-burned credentials, stored as digests only
# --------------------------------------------------------------------------- #
# Phase 6.1 of the publication plan: the shared secret of the retired hosted
# license server is dead code, but it lives in the old private repository's
# history and must never reappear.  We recognise it without carrying it.

KNOWN_BURNED: Dict[str, str] = {
    # sha256 hex digest -> human label
    "462be786089c35f36a64c60fb6c1bea1149d2907949ad11d87425a4bacf6939d":
        "shared API key of the retired hosted license server (owes rotation)",
    "5596bef1bfff0aa9cc90395ac1e16cd79af0f68d6353d2f99901ac537561ba6b":
        "Flask SECRET_KEY of the retired license server",
    "9a4aabf0e5cf71cae2cea646613ce7e2a5919fa758e56819704be25a3a2c1f0b":
        "default license-server admin password shipped in the kit",
}


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()


def known_burned_label(value: str) -> Optional[str]:
    """Return a label if ``value`` is a credential we already know is burned."""
    return KNOWN_BURNED.get(sha256_hex(value.strip()))


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Rule:
    id: str
    description: str
    pattern: "re.Pattern[str]"
    severity: str
    # 1-based group index holding the candidate secret value, or 0 for "whole match"
    value_group: int = 0
    # candidate values shorter than this are dropped as noise
    min_value_len: int = 8
    # candidate values below this Shannon entropy (bits/char) are dropped
    min_entropy: float = 0.0
    # skip the placeholder heuristic (used by rules whose match is structural)
    allow_placeholder: bool = False


def _c(pattern: str, flags: int = 0) -> "re.Pattern[str]":
    return re.compile(pattern, flags)


_SECRETISH_NAME = r"(?:api[_\-]?key|apikey|secret|token|passwd|password|pwd|private[_\-]?key|access[_\-]?key|auth[_\-]?token|client[_\-]?secret|credential)"
_ASSIGN = r"\s*(?::=|=>|[:=])\s*"
_QUOTED = r"[\"'`]([^\"'`\n]{8,200})[\"'`]"

RULES: List[Rule] = [
    # ---------------- project-specific ---------------------------------- #
    Rule(
        # pragma: allowlist secret -- rule definition, not a credential
        id="helixcore-license-api-key",
        description=(
            "License-server shared secret assigned a literal value. This credential is "
            "retired but its old value must never re-enter a repository."
        ),
        # Requires either an assignment/mapping operator, or a comma followed by a
        # *quoted* value -- the os.environ.get('NAME', 'default') shape. A bare
        # identifier in an import list or a mention in prose does not match.
        pattern=_c(r"LICENSE_API_KEY[\"']?\s*"                        # pragma: allowlist secret
                   r"(?:(?::=|=>|[:=])\s*[\"']?|,\s*[\"'])"
                   r"([A-Za-z0-9_\-./+=]{12,200})[\"']?"),
        severity=CRITICAL,
        value_group=1,
        min_value_len=12,
        min_entropy=3.0,
    ),
    Rule(
        id="retired-license-host",
        description=(
            "Reference to the retired hosted license server. Not a secret by itself, "
            "but it marks dead licensing code that must not ship in the MIT release."
        ),
        pattern=_c(r"[A-Za-z0-9_\-]+\.pythonanywhere\.com", re.IGNORECASE),
        severity=LOW,
        min_value_len=8,
        allow_placeholder=True,
    ),
    Rule(
        id="obfuscated-license-constant",
        description=(
            "Obfuscated licensing constant (`*_ENC` literal consumed by decode_secret). "
            "Obfuscation is not redaction: the key material sits beside the ciphertext in "
            "the same tree, so this round-trips back to the retired shared secret. Treat "
            "it exactly like a plaintext credential."
        ),
        # Matches on the *name*, so it fires whatever the ciphertext looks like.
        # The digest path cannot help here: it only ever sees the encoded string,
        # whose hash differs from the plaintext credential's.
        pattern=_c(
            r"\b(?:_?LICENSE_[A-Z0-9_]*_ENC"
            r"|[A-Za-z0-9_]*(?:API_?KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL)[A-Za-z0-9_]*_ENC)"
            r"\s*=\s*[\"']([^\"'\n]{8,400})[\"']",
            re.IGNORECASE,
        ),
        severity=CRITICAL,
        value_group=1,
        min_value_len=8,
        # Mandatory. Ciphertext routinely contains '<', '>', '...' and other
        # PLACEHOLDER_SUBSTRINGS by pure chance; without this the real payload is
        # silently discarded as a placeholder.
        allow_placeholder=True,
    ),
    Rule(
        id="vite-buildtime-secret",
        description=(
            "VITE_-prefixed variable whose name implies a credential. Vite inlines "
            "these into the public bundle, so they are not server secrets, but they "
            "must not enter public git unreviewed."
        ),
        pattern=_c(
            r"\b(VITE_[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASS|PASSWORD|CRED|CREDENTIAL|AUTH|API)[A-Z0-9_]*)"
            r"\s*[:=]\s*[\"']?([^\s\"'`,;]{8,200})[\"']?"
        ),
        severity=MEDIUM,
        value_group=2,
        min_value_len=8,
    ),
    # ---------------- private key material ------------------------------ #
    Rule(
        id="private-key-block",
        description="PEM/OpenSSH private key block.",
        pattern=_c(
            r"-----BEGIN\s+(?:RSA|DSA|EC|OPENSSH|PGP|ENCRYPTED|SSH2\s+ENCRYPTED)?\s*PRIVATE KEY(?:\s+BLOCK)?-----"
        ),
        severity=CRITICAL,
        min_value_len=8,
        allow_placeholder=True,
    ),
    Rule(
        id="putty-private-key",
        description="PuTTY private key header.",
        pattern=_c(r"PuTTY-User-Key-File-\d"),
        severity=CRITICAL,
        min_value_len=8,
        allow_placeholder=True,
    ),
    # ---------------- named cloud/vendor credentials --------------------- #
    Rule(
        id="aws-access-key-id",
        description="AWS access key ID.",
        pattern=_c(r"\b(?:A3T[A-Z0-9]|AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b"),
        severity=CRITICAL,
        min_value_len=20,
        allow_placeholder=True,
    ),
    Rule(
        id="aws-secret-access-key",
        description="AWS secret access key assigned a literal.",
        pattern=_c(
            r"aws_?secret_?access_?key\W{0,6}[\"']?([A-Za-z0-9/+=]{40})[\"']?", re.IGNORECASE
        ),
        severity=CRITICAL,
        value_group=1,
        min_value_len=40,
    ),
    Rule(
        id="github-token",
        description="GitHub personal access / OAuth / app token.",
        pattern=_c(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,255}\b|\bgithub_pat_[A-Za-z0-9_]{50,255}\b"),
        severity=CRITICAL,
        min_value_len=20,
        allow_placeholder=True,
    ),
    Rule(
        id="slack-token",
        description="Slack token or webhook.",
        pattern=_c(
            r"\bxox[abposr]-[A-Za-z0-9\-]{10,}\b"
            r"|https://hooks\.slack\.com/services/[A-Za-z0-9/]{20,}"
        ),
        severity=CRITICAL,
        min_value_len=16,
        allow_placeholder=True,
    ),
    Rule(
        id="stripe-key",
        description="Stripe live secret or restricted key.",
        pattern=_c(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b"),
        severity=CRITICAL,
        min_value_len=20,
        allow_placeholder=True,
    ),
    Rule(
        id="google-api-key",
        description="Google API key.",
        pattern=_c(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
        severity=HIGH,
        min_value_len=39,
        allow_placeholder=True,
    ),
    Rule(
        id="gcp-service-account",
        description="Google service-account JSON private key field.",
        pattern=_c(r"\"type\"\s*:\s*\"service_account\""),
        severity=CRITICAL,
        min_value_len=8,
        allow_placeholder=True,
    ),
    Rule(
        id="openai-key",
        description="OpenAI API key.",
        # The classic form is `sk-` + 48 alphanumerics with no separators. Allowing
        # `_` or `-` in that branch makes the rule match CSS class names such as
        # `sk-toggleable__label-arrow` in bundled scikit-learn assets.
        pattern=_c(r"\b(?:sk-proj-[A-Za-z0-9_\-]{20,}|sk-[A-Za-z0-9]{32,})\b"),
        severity=CRITICAL,
        min_value_len=24,
        min_entropy=3.0,
    ),
    Rule(
        id="anthropic-key",
        description="Anthropic API key.",
        pattern=_c(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"),
        severity=CRITICAL,
        min_value_len=24,
        allow_placeholder=True,
    ),
    Rule(
        id="huggingface-token",
        description="Hugging Face access token.",
        pattern=_c(r"\bhf_[A-Za-z0-9]{34,}\b"),
        severity=HIGH,
        min_value_len=36,
        allow_placeholder=True,
    ),
    Rule(
        id="npm-token",
        description="npm access token.",
        pattern=_c(r"\bnpm_[A-Za-z0-9]{36}\b"),
        severity=CRITICAL,
        min_value_len=40,
        allow_placeholder=True,
    ),
    Rule(
        id="pypi-token",
        description="PyPI upload token.",
        pattern=_c(r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_\-]{20,}"),
        severity=CRITICAL,
        min_value_len=30,
        allow_placeholder=True,
    ),
    Rule(
        id="jwt",
        description="JSON Web Token.",
        pattern=_c(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
        severity=HIGH,
        min_value_len=40,
        allow_placeholder=True,
    ),
    Rule(
        id="basic-auth-url",
        description="Credentials embedded in a URL (scheme://user:secret@host).",  # pragma: allowlist secret
        pattern=_c(r"\b[a-z][a-z0-9+.\-]{1,15}://[^\s:/@\"'`]{1,64}:([^\s:/@\"'`]{3,128})@[^\s/\"'`]+"),
        severity=HIGH,
        value_group=1,
        min_value_len=3,
        min_entropy=2.4,
    ),
    # ---------------- generic assignments -------------------------------- #
    Rule(
        id="generic-api-key-assignment",
        description="Generic credential-shaped identifier assigned a quoted literal.",
        pattern=_c(r"\b[A-Za-z0-9_\-]*" + _SECRETISH_NAME + r"[A-Za-z0-9_\-]*" + _ASSIGN + _QUOTED,
                   re.IGNORECASE),
        severity=HIGH,
        value_group=1,
        min_value_len=12,
        min_entropy=2.6,
    ),
    Rule(
        id="generic-api-key-env-line",
        description="Credential-shaped KEY=value line (dotenv / shell / CI variable).",
        pattern=_c(
            r"^\s*(?:export\s+)?[A-Za-z0-9_]*" + _SECRETISH_NAME +
            r"[A-Za-z0-9_]*\s*=\s*[\"']?([^\s\"'`#]{12,200})[\"']?\s*$",
            re.IGNORECASE | re.MULTILINE,
        ),
        severity=HIGH,
        value_group=1,
        min_value_len=12,
        min_entropy=2.6,
    ),
    Rule(
        id="hardcoded-long-hex-secret",
        description="Credential-shaped identifier assigned a 32+ character hex literal.",
        # Deliberately excludes hash/checksum/digest/integrity/fingerprint/etag
        # identifiers. This repository is full of legitimate SHA-256 values
        # (tools_manifest.json, lockfiles, graph caches) and including them
        # buries the real findings under four figures of noise.
        pattern=_c(
            r"\b(?!(?:[A-Za-z0-9_\-]*(?:hash|checksum|digest|integrity|fingerprint|etag|sha\d*|md5)))"
            r"[A-Za-z0-9_\-]*(?:key|secret|token|passwd|password)[A-Za-z0-9_\-]*"
            r"\W{0,6}[\"']([0-9a-fA-F]{32,128})[\"']",
            re.IGNORECASE,
        ),
        severity=HIGH,
        value_group=1,
        min_value_len=32,
    ),
    Rule(
        id="db-connection-string",
        description="Database connection string carrying an inline password.",
        pattern=_c(
            r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp|mssql)://"
            r"[^\s:/@\"'`]{1,64}:([^\s:/@\"'`]{3,128})@",
            re.IGNORECASE,
        ),
        severity=CRITICAL,
        value_group=1,
        min_value_len=3,
    ),
]


# Path-shaped rules: the *name* of the file is the finding.
@dataclass(frozen=True)
class PathRule:
    id: str
    description: str
    globs: Tuple[str, ...]
    severity: str


PATH_RULES: List[PathRule] = [
    PathRule(
        id="dotenv-file",
        description="Environment file. These carry real values and must never be committed.",
        globs=(".env", ".env.*", "*.env"),
        severity=HIGH,
    ),
    PathRule(
        # `*.pem` and `*.asc` are deliberately absent: CA bundles (certifi's
        # cacert.pem) and detached signatures are public by design and are the
        # single largest source of false positives in a Python distribution.
        # A .pem that really holds a key is caught by the private-key-block
        # content rule instead.
        id="private-key-file",
        description="File extension associated with private key or keystore material.",
        globs=("*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "*.ppk",
               "*.gpg", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"),
        severity=CRITICAL,
    ),
    PathRule(
        id="credential-file",
        description="Well-known credential file name.",
        globs=("credentials.json", "client_secret*.json", "service-account*.json",
               "serviceaccount*.json", ".npmrc", ".pypirc", ".netrc", "_netrc",
               "secrets.json", "secrets.yml", "secrets.yaml", "*.ovpn"),
        severity=HIGH,
    ),
    PathRule(
        id="license-server-kit",
        description=(
            "Private license-server kit. Explicitly must not reach the public repo "
            "(PUBLICATION_PLAN.md 6.2)."
        ),
        globs=("LicenseServerKit/*",),
        severity=CRITICAL,
    ),
]

# File names that are templates, not real secrets.
TEMPLATE_SUFFIXES = (".example", ".sample", ".template", ".dist", ".tmpl", ".default")


# --------------------------------------------------------------------------- #
# Phase 6.2 index exclusion audit
# --------------------------------------------------------------------------- #
# (label, git pathspec) pairs that MUST return zero tracked files.
MUST_BE_ABSENT: List[Tuple[str, str]] = [
    ("Private license-server kit", "LicenseServerKit"),
    ("Manuscript and evidence workspace", "Paper"),
    ("Local test scratch", "AmrTest"),
    ("Local E2E scratch", "E2E"),
    ("Knowledge-graph output", "graphify-out"),
    ("Marketing site (holds VITE_WEB3FORMS_KEY)", "landing"),
    ("Bundled GPL binaries (ship as release asset)", "tools"),
    ("Local audit report", "SCIENTIFIC_AUDIT_REPORT.md"),
    ("Local audit report", "SCIENTIFIC_AUDIT_CURRENT_STATUS.md"),
    ("Local audit report", "PAPER_APP_REVIEW.md"),
    ("Runtime job workspace", "workspace"),
    ("PyInstaller output", "dist"),
    ("PyInstaller output", "build"),
    ("Agent config", ".agents"),
    ("Local skill lock", "skills-lock.json"),
]

# Paths that MUST be present in the commit (GPL-2.0 and OSS obligations).
# ``tools/`` itself is intentionally untracked, so the Open Babel GPL-2.0
# attribution is discharged by THIRD_PARTY_LICENSES.md in-repo plus License.txt
# and SOURCE.md travelling inside the release asset. See the Phase 6 checklist.
MUST_BE_PRESENT: List[Tuple[str, str]] = [
    ("MIT licence", "LICENSE"),
    ("Third-party attribution (carries the Open Babel GPL-2.0 obligation)",
     "THIRD_PARTY_LICENSES.md"),
    ("Citation metadata for Zenodo", "CITATION.cff"),
    ("Contributor guide", "CONTRIBUTING.md"),
    ("Code of conduct", "CODE_OF_CONDUCT.md"),
    ("Readme", "README.md"),
    # THIRD_PARTY_LICENSES.md instructs the reader to run this script to restore
    # tools/ from the release asset. If the script is not in the commit, that
    # instruction is a dead end and the GPL-2.0 discharge route documented in the
    # repository cannot actually be followed from a clean clone.
    ("Release-asset fetcher that restores tools/ (referenced by THIRD_PARTY_LICENSES.md)",
     "scripts/fetch_tools.py"),
]

# Files that must exist inside the tools/ release asset for the GPL-2.0
# obligation to be discharged where the binaries actually ship.
RELEASE_ASSET_LICENSE_FILES: List[str] = [
    "tools/OpenBabel/License.txt",
    "tools/OpenBabel/SOURCE.md",
]


# --------------------------------------------------------------------------- #
# Traversal configuration
# --------------------------------------------------------------------------- #

# Never walked. Vendor code and VCS internals; scanning them yields only noise.
ALWAYS_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".env.d",
    "site-packages", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    ".gradle", ".cache", ".parcel-cache", ".turbo",
}

# Skipped by default (build output / runtime data); included with --all-files.
ARTIFACT_SKIP_DIRS = {
    "dist", "build", "release", "dist-electron", "dist-ssr", ".vite", ".next",
    "coverage", "htmlcov", "out", "win-unpacked", "workspace", "test_walkthrough",
    "_internal",
}

SKIP_FILE_GLOBS = (
    "*.min.js", "*.min.css", "*.map", "package-lock.json", "yarn.lock",
    "pnpm-lock.yaml", "*.lock",
)

BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".icns", ".webp", ".tif", ".tiff",
    ".pdf", ".zip", ".gz", ".bz2", ".xz", ".7z", ".rar", ".tar", ".whl", ".jar",
    ".exe", ".dll", ".so", ".dylib", ".pyd", ".pyc", ".pyo", ".obj", ".o", ".a", ".lib",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".docx", ".xlsx", ".pptx", ".db", ".sqlite", ".sqlite3", ".bin", ".dat", ".npy",
    ".npz", ".h5", ".hdf5", ".pkl", ".pickle", ".msi", ".node", ".wasm",
}

DEFAULT_MAX_BYTES = 5 * 1024 * 1024


# --------------------------------------------------------------------------- #
# Placeholder / false-positive heuristics
# --------------------------------------------------------------------------- #

PLACEHOLDER_SUBSTRINGS = (
    "your_", "your-", "yourkey", "youraccess", "replace", "changeme", "change_me",
    "change-me", "placeholder", "example", "sample", "dummy", "insert", "todo",
    "fixme", "xxxxx", "aaaaa", "<", ">", "{{", "}}", "${", "%s", "%(", "…", "...",
    "notset", "not_set", "not-set", "none", "null", "undefined", "redacted",
    "fake", "mock", "stub", "test_key", "testkey", "dummykey", "abcdef123456",
    "0123456789", "deadbeef", "lorem", "foobar",
)

# Values that are code, not data: env lookups, template refs, imports.
CODE_REFERENCE_RE = re.compile(
    r"(os\.environ|os\.getenv|process\.env|import\.meta\.env|System\.getenv"
    r"|getenv\(|\bENV\[|secrets\.|config\.|settings\.|self\.|this\.)",
    re.IGNORECASE,
)

# Identifiers that look credential-shaped but name public constants. Checked
# against the whole matched line, so the match is dropped wherever it appears.
BENIGN_CONTEXT_RE = re.compile(
    r"(publicKeyToken|keyframes|keyCode|keyPath|keyboard|keyword|monkey|turkey"
    r"|donkey|passwordless|tokenizer|tokenize|subtoken|keychain_stub)",
    re.IGNORECASE,
)


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts: Dict[str, int] = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(value)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def looks_like_placeholder(value: str) -> Optional[str]:
    """Return a reason string if ``value`` is clearly not a live credential."""
    v = value.strip()
    if not v:
        return "empty value"
    low = v.lower()
    for token in PLACEHOLDER_SUBSTRINGS:
        if token in low:
            return "placeholder token %r" % token
    if CODE_REFERENCE_RE.search(v):
        return "environment/config reference, not a literal"
    if len(set(v)) <= 3:
        return "fewer than four distinct characters"
    if re.fullmatch(r"[A-Za-z _\-]+", v) and " " in v:
        return "prose, not a credential"
    if re.fullmatch(r"[a-z]+(?:_[a-z]+)+", v):
        # e.g. "is_member_call" harvested from a JSON AST dump. Digit-free,
        # all-lowercase snake_case is a symbol name, not a credential. Values with
        # any digit or uppercase character are deliberately NOT suppressed here.
        return "bare snake_case identifier, almost certainly a symbol name"
    return None


# --------------------------------------------------------------------------- #
# Findings
# --------------------------------------------------------------------------- #


@dataclass
class Finding:
    scope: str          # worktree | index | history | external
    path: str
    line: int
    rule_id: str
    severity: str
    description: str
    match_preview: str
    value_redacted: str
    known_burned: Optional[str] = None
    detector: str = "builtin"
    extra: Dict[str, str] = field(default_factory=dict)

    def sort_key(self) -> Tuple[int, str, str, int]:
        return (-SEVERITY_ORDER[self.severity], self.scope, self.path, self.line)

    def to_dict(self) -> Dict[str, object]:
        d = {
            "scope": self.scope,
            "path": self.path,
            "line": self.line,
            "rule": self.rule_id,
            "severity": self.severity,
            "description": self.description,
            "match_preview": self.match_preview,
            "value": self.value_redacted,
            "detector": self.detector,
        }
        if self.known_burned:
            d["known_burned_credential"] = self.known_burned
        if self.extra:
            d["extra"] = self.extra
        return d


def redact(value: str, show: bool) -> str:
    v = value.strip()
    if show:
        return v
    if len(v) <= 8:
        return "*" * len(v)
    return "%s%s%s" % (v[:4], "*" * min(len(v) - 8, 24), v[-4:])


def preview(line: str, show: bool, secret: str = "") -> str:
    text = line.strip()
    if not show and secret and len(secret) > 8:
        text = text.replace(secret, redact(secret, False))
    if len(text) > 200:
        text = text[:197] + "..."
    return text


# --------------------------------------------------------------------------- #
# Content scanning
# --------------------------------------------------------------------------- #


def is_probably_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def decode(data: bytes) -> str:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return data.decode("utf-8", "replace")


ALLOWLIST_PRAGMA = re.compile(r"(?:pragma:\s*allowlist\s+secret|secret[_\-]scan:\s*ignore|gitleaks:allow)",
                              re.IGNORECASE)
# Region markers, for blocks that unavoidably contain secret-shaped literals
# (test fixtures, documented example payloads).
ALLOWLIST_BEGIN = re.compile(r"secret[_\-]scan:\s*begin-allowlist", re.IGNORECASE)
ALLOWLIST_END = re.compile(r"secret[_\-]scan:\s*end-allowlist", re.IGNORECASE)


def allowlisted_lines(lines: Sequence[str]) -> set:
    """1-based line numbers inside a begin-allowlist/end-allowlist region."""
    inside = False
    out = set()
    for i, line in enumerate(lines, start=1):
        if ALLOWLIST_BEGIN.search(line):
            inside = True
            out.add(i)
            continue
        if ALLOWLIST_END.search(line):
            inside = False
            out.add(i)
            continue
        if inside:
            out.add(i)
    return out


def is_template_path(path: str) -> bool:
    """True for .env.example / config.sample / settings.template style files."""
    lower = os.path.basename(path).lower()
    return lower.endswith(TEMPLATE_SUFFIXES) or any(
        ("%s." % s.lstrip(".")) in lower for s in TEMPLATE_SUFFIXES
    )


def scan_text(scope: str, path: str, text: str, show_secrets: bool,
              entropy_sweep: bool) -> List[Finding]:
    findings: List[Finding] = []
    lines = text.splitlines()
    template = is_template_path(path)
    skip_lines = allowlisted_lines(lines)

    # Map a match offset to a 1-based line number. Computed from actual newline
    # positions rather than from len(line)+1, which is off by one per line on
    # CRLF files and silently corrupts every line number in the report.
    newline_offsets = [m.start() for m in re.finditer(r"\n", text)]

    def line_of(offset: int) -> int:
        return bisect.bisect_right(newline_offsets, offset) + 1

    for rule in RULES:
        for m in rule.pattern.finditer(text):
            value = m.group(rule.value_group) if rule.value_group else m.group(0)
            if value is None:
                continue
            value = value.strip()
            if len(value) < rule.min_value_len:
                continue

            burned = known_burned_label(value)

            if not burned and not rule.allow_placeholder:
                reason = looks_like_placeholder(value)
                if reason:
                    continue
                if rule.min_entropy and shannon_entropy(value) < rule.min_entropy:
                    continue

            lineno = line_of(m.start())
            if lineno in skip_lines:
                continue
            raw_line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
            if ALLOWLIST_PRAGMA.search(raw_line):
                continue

            if burned:
                severity = CRITICAL
                description = rule.description
            elif template:
                # A committed .env.example is supposed to contain fake values.
                # Report it so a real value pasted into a template is still
                # visible, but do not let it block publication on its own.
                severity = LOW
                description = ("%s  [template file — values here are expected to be "
                               "placeholders; verify by eye]" % rule.description)
            else:
                severity = rule.severity
                description = rule.description

            findings.append(Finding(
                scope=scope,
                path=path,
                line=lineno,
                rule_id=rule.id,
                severity=severity,
                description=description,
                match_preview=preview(raw_line, show_secrets, value),
                value_redacted=redact(value, show_secrets),
                known_burned=burned,
            ))

    if entropy_sweep:
        findings.extend(_entropy_sweep(scope, path, lines, show_secrets))

    return _dedupe(findings)


ENTROPY_CANDIDATE = re.compile(r"[\"'`]([A-Za-z0-9+/=_\-]{32,120})[\"'`]")


def _entropy_sweep(scope: str, path: str, lines: Sequence[str],
                   show_secrets: bool) -> List[Finding]:
    """Opt-in heuristic: long, high-entropy quoted literals. Noisy by nature."""
    out: List[Finding] = []
    skip_lines = allowlisted_lines(lines)
    for i, line in enumerate(lines, start=1):
        if i in skip_lines or ALLOWLIST_PRAGMA.search(line):
            continue
        for m in ENTROPY_CANDIDATE.finditer(line):
            value = m.group(1)
            if looks_like_placeholder(value):
                continue
            ent = shannon_entropy(value)
            if ent < 4.0:
                continue
            burned = known_burned_label(value)
            out.append(Finding(
                scope=scope,
                path=path,
                line=i,
                rule_id="high-entropy-literal",
                severity=CRITICAL if burned else LOW,
                description="High-entropy quoted literal (%.2f bits/char). Review manually; "
                            "checksums, hashes and test vectors trip this legitimately." % ent,
                match_preview=preview(line, show_secrets, value),
                value_redacted=redact(value, show_secrets),
                known_burned=burned,
            ))
    return out


def _dedupe(findings: Iterable[Finding]) -> List[Finding]:
    seen = set()
    out = []
    for f in findings:
        key = (f.scope, f.path, f.line, f.rule_id, f.value_redacted)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def path_findings(scope: str, path: str) -> List[Finding]:
    name = os.path.basename(path)
    lower = name.lower()
    out: List[Finding] = []
    for rule in PATH_RULES:
        matched = False
        for g in rule.globs:
            if "/" in g:
                if fnmatch.fnmatch(path.replace("\\", "/"), g) or \
                   path.replace("\\", "/").startswith(g.rstrip("*")):
                    matched = True
            elif fnmatch.fnmatch(lower, g.lower()):
                matched = True
            if matched:
                break
        if not matched:
            continue
        if lower.endswith(TEMPLATE_SUFFIXES):
            continue
        out.append(Finding(
            scope=scope,
            path=path,
            line=0,
            rule_id=rule.id,
            severity=rule.severity,
            description=rule.description,
            match_preview="(matched by file name)",
            value_redacted="",
        ))
    return out


# --------------------------------------------------------------------------- #
# Scope: working tree
# --------------------------------------------------------------------------- #


def iter_worktree(root: str, all_files: bool) -> Iterator[str]:
    skip_dirs = set(ALWAYS_SKIP_DIRS)
    if not all_files:
        skip_dirs |= ARTIFACT_SKIP_DIRS
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip_dirs)
        for fn in sorted(filenames):
            if any(fnmatch.fnmatch(fn.lower(), g) for g in SKIP_FILE_GLOBS):
                continue
            yield os.path.join(dirpath, fn)


def scan_worktree(root: str, all_files: bool, max_bytes: int, show_secrets: bool,
                  entropy_sweep: bool) -> Tuple[List[Finding], int]:
    findings: List[Finding] = []
    count = 0
    for abspath in iter_worktree(root, all_files):
        rel = os.path.relpath(abspath, root).replace("\\", "/")
        findings.extend(path_findings("worktree", rel))
        ext = os.path.splitext(abspath)[1].lower()
        if ext in BINARY_EXTS:
            continue
        try:
            if os.path.getsize(abspath) > max_bytes:
                continue
            with open(abspath, "rb") as fh:
                data = fh.read(max_bytes)
        except OSError:
            continue
        if is_probably_binary(data):
            continue
        count += 1
        findings.extend(scan_text("worktree", rel, decode(data), show_secrets, entropy_sweep))
    return findings, count


# --------------------------------------------------------------------------- #
# Scope: git index (staged blobs)
# --------------------------------------------------------------------------- #


def git(root: str, *args: str, binary: bool = False):
    proc = subprocess.run(
        ["git", "-C", root] + list(args),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if proc.returncode != 0 and not binary:
        return None
    return proc.stdout if binary else proc.stdout.decode("utf-8", "replace")


def is_git_repo(root: str) -> bool:
    return git(root, "rev-parse", "--git-dir") is not None


def index_entries(root: str) -> List[Tuple[str, str]]:
    """Return (blob_sha, path) for every entry in the staged index."""
    out = git(root, "ls-files", "-s", "-z")
    if out is None:
        return []
    entries = []
    for record in out.split("\0"):
        if not record.strip():
            continue
        # "<mode> <sha> <stage>\t<path>"
        meta, _, path = record.partition("\t")
        parts = meta.split()
        if len(parts) < 3 or not path:
            continue
        entries.append((parts[1], path))
    return entries


def cat_blobs(root: str, shas: Sequence[str]) -> Dict[str, bytes]:
    """Read many blobs with one `git cat-file --batch` process."""
    if not shas:
        return {}
    proc = subprocess.Popen(
        ["git", "-C", root, "cat-file", "--batch"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    payload = ("\n".join(shas) + "\n").encode()
    stdout, _ = proc.communicate(payload)

    blobs: Dict[str, bytes] = {}
    pos = 0
    while pos < len(stdout):
        nl = stdout.find(b"\n", pos)
        if nl == -1:
            break
        header = stdout[pos:nl].decode("utf-8", "replace").split()
        pos = nl + 1
        if len(header) < 3:
            continue
        sha, _kind, size_s = header[0], header[1], header[2]
        try:
            size = int(size_s)
        except ValueError:
            continue
        blobs[sha] = stdout[pos:pos + size]
        pos += size + 1  # trailing newline
    return blobs


def scan_index(root: str, max_bytes: int, show_secrets: bool,
               entropy_sweep: bool) -> Tuple[List[Finding], int]:
    findings: List[Finding] = []
    entries = index_entries(root)
    if not entries:
        return findings, 0

    for _sha, path in entries:
        findings.extend(path_findings("index", path))

    scannable = [(sha, p) for sha, p in entries
                 if os.path.splitext(p)[1].lower() not in BINARY_EXTS
                 and not any(fnmatch.fnmatch(os.path.basename(p).lower(), g)
                             for g in SKIP_FILE_GLOBS)]
    blobs = cat_blobs(root, [sha for sha, _ in scannable])
    count = 0
    for sha, path in scannable:
        data = blobs.get(sha)
        if data is None or len(data) > max_bytes or is_probably_binary(data):
            continue
        count += 1
        findings.extend(scan_text("index", path, decode(data), show_secrets, entropy_sweep))
    return findings, count


# --------------------------------------------------------------------------- #
# Scope: history
# --------------------------------------------------------------------------- #


def scan_history(root: str, max_bytes: int, show_secrets: bool,
                 entropy_sweep: bool, limit: int) -> Tuple[List[Finding], int]:
    """Scan every blob reachable from every ref. Slow; off by default."""
    findings: List[Finding] = []
    out = git(root, "rev-list", "--all")
    if out is None:
        return findings, 0
    commits = [c for c in out.split() if c][:limit] if limit else [c for c in out.split() if c]

    seen_blobs: Dict[str, str] = {}   # sha -> first path seen
    for commit in commits:
        listing = git(root, "ls-tree", "-r", "-z", commit)
        if not listing:
            continue
        for record in listing.split("\0"):
            if not record.strip():
                continue
            meta, _, path = record.partition("\t")
            parts = meta.split()
            if len(parts) < 3 or not path:
                continue
            sha = parts[2]
            if sha in seen_blobs:
                continue
            if os.path.splitext(path)[1].lower() in BINARY_EXTS:
                continue
            seen_blobs[sha] = path

    blobs = cat_blobs(root, list(seen_blobs.keys()))
    count = 0
    for sha, path in seen_blobs.items():
        data = blobs.get(sha)
        if data is None or len(data) > max_bytes or is_probably_binary(data):
            continue
        count += 1
        findings.extend(scan_text("history", "%s (blob %s)" % (path, sha[:8]),
                                  decode(data), show_secrets, entropy_sweep))
    return findings, count


# --------------------------------------------------------------------------- #
# External scanners
# --------------------------------------------------------------------------- #


def run_external(root: str, timeout: int = 900) -> Tuple[List[Finding], List[str]]:
    """Run gitleaks / trufflehog when present. Returns (findings, notes)."""
    findings: List[Finding] = []
    notes: List[str] = []

    gitleaks = shutil.which("gitleaks")
    if gitleaks:
        report = os.path.join(root, ".gitleaks-report.json")
        cmd = [gitleaks, "detect", "--no-git", "--source", root,
               "--report-format", "json", "--report-path", report, "--exit-code", "0"]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout)
            if os.path.exists(report):
                with open(report, "r", encoding="utf-8", errors="replace") as fh:
                    data = json.load(fh) or []
                for item in data:
                    findings.append(Finding(
                        scope="worktree",
                        path=str(item.get("File", "?")).replace("\\", "/"),
                        line=int(item.get("StartLine", 0) or 0),
                        rule_id="gitleaks:%s" % item.get("RuleID", "unknown"),
                        severity=HIGH,
                        description=str(item.get("Description", "gitleaks finding")),
                        match_preview=str(item.get("Match", ""))[:200],
                        value_redacted=redact(str(item.get("Secret", "")), False),
                        detector="gitleaks",
                    ))
                os.remove(report)
            notes.append("gitleaks: ran, %d finding(s)." % len(findings))
        except Exception as exc:                      # noqa: BLE001
            notes.append("gitleaks: present but failed (%s)." % exc)
    else:
        notes.append("gitleaks: not installed — built-in engine used instead.")

    trufflehog = shutil.which("trufflehog")
    if trufflehog:
        before = len(findings)
        cmd = [trufflehog, "filesystem", root, "--json", "--no-update"]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=timeout)
            for raw in proc.stdout.decode("utf-8", "replace").splitlines():
                raw = raw.strip()
                if not raw.startswith("{"):
                    continue
                try:
                    item = json.loads(raw)
                except ValueError:
                    continue
                meta = (item.get("SourceMetadata") or {}).get("Data") or {}
                fsmeta = meta.get("Filesystem") or {}
                findings.append(Finding(
                    scope="worktree",
                    path=str(fsmeta.get("file", "?")).replace("\\", "/"),
                    line=int(fsmeta.get("line", 0) or 0),
                    rule_id="trufflehog:%s" % item.get("DetectorName", "unknown"),
                    severity=CRITICAL if item.get("Verified") else HIGH,
                    description="trufflehog %s (verified=%s)" % (
                        item.get("DetectorName"), item.get("Verified")),
                    match_preview=str(item.get("Raw", ""))[:80],
                    value_redacted=redact(str(item.get("Raw", "")), False),
                    detector="trufflehog",
                ))
            notes.append("trufflehog: ran, %d finding(s)." % (len(findings) - before))
        except Exception as exc:                      # noqa: BLE001
            notes.append("trufflehog: present but failed (%s)." % exc)
    else:
        notes.append("trufflehog: not installed — built-in engine used instead.")

    return findings, notes


# --------------------------------------------------------------------------- #
# Phase 6.2 exclusion / inclusion audit
# --------------------------------------------------------------------------- #


def verify_index_contents(root: str) -> Tuple[List[Dict[str, object]], List[Finding]]:
    rows: List[Dict[str, object]] = []
    findings: List[Finding] = []

    for label, pathspec in MUST_BE_ABSENT:
        out = git(root, "ls-files", "--", pathspec)
        tracked = [p for p in (out or "").splitlines() if p.strip()]
        ok = not tracked
        rows.append({
            "check": "absent",
            "label": label,
            "pathspec": pathspec,
            "ok": ok,
            "tracked_files": len(tracked),
            "examples": tracked[:5],
        })
        if not ok:
            findings.append(Finding(
                scope="index",
                path=pathspec,
                line=0,
                rule_id="phase6-must-be-absent",
                severity=CRITICAL,
                description=("%s is still TRACKED in the git index (%d files). "
                             ".gitignore does not untrack an already-tracked path; "
                             "`git rm -r --cached %s` is required before the publication "
                             "commit." % (label, len(tracked), pathspec)),
                match_preview=", ".join(tracked[:3]) + ("..." if len(tracked) > 3 else ""),
                value_redacted="",
            ))

    for label, pathspec in MUST_BE_PRESENT:
        out = git(root, "ls-files", "--", pathspec)
        tracked = [p for p in (out or "").splitlines() if p.strip()]
        ok = bool(tracked)
        rows.append({
            "check": "present",
            "label": label,
            "pathspec": pathspec,
            "ok": ok,
            "tracked_files": len(tracked),
            "examples": tracked[:5],
        })
        if not ok:
            findings.append(Finding(
                scope="index",
                path=pathspec,
                line=0,
                rule_id="phase6-must-be-present",
                severity=HIGH,
                description="%s is MISSING from the git index; the publication commit "
                            "would not contain it." % label,
                match_preview="(not tracked)",
                value_redacted="",
            ))

    # GPL-2.0 obligation: when tools/ is present, require the attribution files
    # on disk because that tree may become the release asset. In a clean source
    # checkout tools/ is intentionally absent; in that case the checksum
    # manifest must declare both files so fetch_tools.py will require and verify
    # them before unpacking.
    tools_root_exists = os.path.isdir(os.path.join(root, "tools"))
    manifest_entries: set = set()
    manifest_path = os.path.join(root, "tools_manifest.json")
    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        files = manifest.get("files", {})
        if isinstance(files, dict):
            manifest_entries = set(files)
    except (OSError, ValueError, TypeError):
        manifest_entries = set()

    for rel in RELEASE_ASSET_LICENSE_FILES:
        exists = os.path.exists(os.path.join(root, rel))
        manifest_rel = rel[len("tools/"):] if rel.startswith("tools/") else rel
        declared = manifest_rel in manifest_entries
        ok = exists if tools_root_exists else declared
        rows.append({
            "check": "release_asset_file",
            "label": (
                "GPL-2.0 attribution inside the tools/ release asset"
                if tools_root_exists
                else "GPL-2.0 attribution declared in the tool checksum manifest"
            ),
            "pathspec": rel,
            "ok": ok,
            "tracked_files": 0,
            "examples": [],
        })
        if not ok:
            findings.append(Finding(
                scope="worktree" if tools_root_exists else "index",
                path=rel,
                line=0,
                rule_id="phase6-gpl-attribution",
                severity=HIGH,
                description=(
                    "Required GPL-2.0 attribution file is missing from the tools/ "
                    "tree that becomes the release asset."
                    if tools_root_exists
                    else "Required GPL-2.0 attribution file is not declared in "
                         "tools_manifest.json, so a clean clone cannot verify that "
                         "the release asset contains it."
                ),
                match_preview=(
                    "(file not found)"
                    if tools_root_exists
                    else "(manifest entry not found)"
                ),
                value_redacted="",
            ))

    return rows, findings


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def render_report(findings: List[Finding], stats: Dict[str, object],
                  audit_rows: Optional[List[Dict[str, object]]],
                  notes: List[str]) -> str:
    lines: List[str] = []
    w = lines.append

    w("=" * 78)
    w("Helix Core pre-publication secret scan")
    w("=" * 78)
    w("root          : %s" % stats.get("root"))
    w("scopes        : %s" % ", ".join(stats.get("scopes", [])))  # type: ignore[arg-type]
    w("files scanned : worktree=%s  index=%s  history=%s" % (
        stats.get("worktree_files", "-"), stats.get("index_files", "-"),
        stats.get("history_blobs", "-")))
    w("entropy sweep : %s" % ("on" if stats.get("entropy") else "off (use --entropy)"))
    w("artefact dirs : %s" % ("scanned (--all-files)" if stats.get("all_files")
                              else "skipped (%s)" % ", ".join(sorted(ARTIFACT_SKIP_DIRS))))
    for n in notes:
        w("detector      : %s" % n)
    w("")

    if audit_rows is not None:
        w("-" * 78)
        w("Phase 6.2 index audit — what the publication commit would contain")
        w("-" * 78)
        for row in audit_rows:
            mark = "PASS" if row["ok"] else "FAIL"
            if row["check"] == "absent":
                detail = "absent from index" if row["ok"] else \
                    "%d tracked file(s): %s" % (row["tracked_files"],
                                                ", ".join(row["examples"]))  # type: ignore[arg-type]
            elif row["check"] == "present":
                detail = "%d tracked file(s)" % row["tracked_files"] if row["ok"] else "NOT TRACKED"
            else:
                detail = "on disk" if row["ok"] else "MISSING"
            w("  [%s] %-34s %-38s %s" % (mark, row["pathspec"], row["label"], detail))
        w("")

    counts = {s: 0 for s in SEVERITY_ORDER}
    for f in findings:
        counts[f.severity] += 1

    w("-" * 78)
    w("Findings: %d total  (CRITICAL %d, HIGH %d, MEDIUM %d, LOW %d, INFO %d)" % (
        len(findings), counts[CRITICAL], counts[HIGH], counts[MEDIUM],
        counts[LOW], counts[INFO]))
    w("-" * 78)

    if not findings:
        w("  No findings.")
        w("")
        return "\n".join(lines)

    for f in sorted(findings, key=lambda x: x.sort_key()):
        loc = "%s:%d" % (f.path, f.line) if f.line else f.path
        w("")
        w("[%s] %s  (%s, %s)" % (f.severity, f.rule_id, f.scope, f.detector))
        w("  where : %s" % loc)
        w("  what  : %s" % f.description)
        if f.known_burned:
            w("  ALERT : matches a KNOWN BURNED credential — %s" % f.known_burned)
        if f.value_redacted:
            w("  value : %s" % f.value_redacted)
        if f.match_preview:
            w("  line  : %s" % f.match_preview)
    w("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Self-test
# --------------------------------------------------------------------------- #
# A scanner that reports "0 findings" is indistinguishable from a scanner whose
# regexes never compile a useful match. These fixtures prove the engine fires on
# things it must catch and stays quiet on things it must not.

# secret-scan: begin-allowlist
# Everything between this marker and end-allowlist is synthetic. The values below
# are invented for the fixtures and are not credentials for any real system; the
# region marker stops this scanner from reporting its own test data.
_SELFTEST_MUST_HIT: List[Tuple[str, str, str]] = [
    # (rule_id, filename, content)
    ("helixcore-license-api-key", "cfg.py",
     "API_KEY = os.environ.get('LICENSE_API_KEY', "  # pragma: allowlist secret
     "'3f9a1c77b20e4d5586af0c31de7b9204')\n"),
    ("vite-buildtime-secret", "vars.env",
     "VITE_WEB3FORMS_KEY=9d41e8b2-70cc-4f1a-9d0b-6c2f8ab13e57\n"),
    ("vite-buildtime-secret", "vars.env",
     "VITE_SUPABASE_ANON_TOKEN=Zm9vYmF6cXV4MTIzNDU2Nzg5MA\n"),
    # Obfuscated constant. The fixture value deliberately contains '<', '>' and a
    # backtick: real ciphertext does, and each of those used to sink the match --
    # the first two via the placeholder heuristic, the backtick by terminating the
    # generic rule's quoted-value class early.
    ("obfuscated-license-constant", "config.py",
     "_LICENSE_API_KEY_ENC = \"7Qx-Vr^IZ!f`Pc=OT<pm&1+~0y4j{a?SXq>Z@nnLkUMz\"\n"),
    ("private-key-block", "id.txt",
     "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKC\n-----END RSA PRIVATE KEY-----\n"),
    ("aws-access-key-id", "aws.txt", "id = AKIAIOSFODNN7EXAMPLE\n"),
    ("github-token", "ci.yml",
     "token: ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8\n"),
    ("generic-api-key-assignment", "svc.py",
     'client_secret = "7Hq2Lm9Xt4Rv8Nz1Pb6Wd3Yf5Kc0Js"\n'),
    ("generic-api-key-env-line", "deploy.env",
     "export DEPLOY_TOKEN=t0k3n_9f4a2b7c1d8e6031\n"),
    ("db-connection-string", "app.py",
     'DSN = "postgresql://svc:9fA2kQ7zL1@db.internal:5432/prod"\n'),
    ("hardcoded-long-hex-secret", "flask.py",
     "SECRET_KEY = '5b1d9e04a7c23f68d105ba7e39cc4f82'\n"),
    ("basic-auth-url", "fetch.sh",
     "curl https://svcacct:7Kq2Zr9Lm4@artifacts.example.net/x.tar.gz\n"),
]

_SELFTEST_MUST_NOT_HIT: List[Tuple[str, str]] = [
    # (filename, content) -- must produce zero findings
    ("cfg.py", "API_KEY = os.environ.get('LICENSE_API_KEY')\n"),  # pragma: allowlist secret
    ("cfg.py", "SECRET_KEY = os.environ.get('SECRET_KEY')\n"),
    ("vars.env", "VITE_WEB3FORMS_KEY=YOUR_ACCESS_KEY\n"),
    ("vars.env", "VITE_SITE_URL=https://example.org\n"),
    ("main.ts", "const key = import.meta.env.VITE_API_KEY;\n"),
    ("manifest.json", '{"sha256": "9f54c3a1b8e27d604f13ab95cc27e0d3457ab1249fe0c73a1b2c3d4e5f60a1b2"}\n'),
    ("manifest.json", '{"checksum": "3AD8E5D6EF9C9BD0BDD3EDA7DDF127B53C5688C3CD0F59472EF6226D1467EBFE"}\n'),
    ("lock.json", '{"integrity_hash": "d41d8cd98f00b204e9800998ecf8427e"}\n'),
    ("doc.md", "Set `API_KEY` to your own value before running.\n"),
    ("readme.md", 'password = "changeme"\n'),
    ("ast.json", '{"callee": "LICENSE_API_KEY", "is_member_call": false}\n'),  # noqa: E501
    # `_ENC` on a non-credential name must stay quiet: encoding is not secrecy.
    ("codec.py", "CONTENT_ENC = 'gzip'\n"),
]
# secret-scan: end-allowlist


def run_selftest() -> int:
    failures: List[str] = []
    checks = 0

    for rule_id, name, content in _SELFTEST_MUST_HIT:
        checks += 1
        hits = scan_text("selftest", name, content, show_secrets=False, entropy_sweep=False)
        if not any(h.rule_id == rule_id for h in hits):
            failures.append("MISS  %-28s on %-14s -> rules fired: %s"
                            % (rule_id, name, sorted({h.rule_id for h in hits}) or "none"))

    for name, content in _SELFTEST_MUST_NOT_HIT:
        checks += 1
        hits = scan_text("selftest", name, content, show_secrets=False, entropy_sweep=False)
        if hits:
            failures.append("FALSE POSITIVE on %-14s %-40s -> %s"
                            % (name, content.strip()[:40], sorted({h.rule_id for h in hits})))

    # Line numbering must survive CRLF, which is the default on this host.
    checks += 1
    crlf = "a = 1\r\nb = 2\r\nSECRET_KEY = '5b1d9e04a7c23f68d105ba7e39cc4f82'\r\n"  # pragma: allowlist secret
    hits = scan_text("selftest", "crlf.py", crlf, show_secrets=False, entropy_sweep=False)
    if not hits or hits[0].line != 3:
        failures.append("CRLF line numbering wrong: got %s, expected 3"
                        % ([h.line for h in hits] or "no hit"))

    # The known-burned digests must be reachable by the digest path.
    checks += 1
    if len(KNOWN_BURNED) != 3:
        failures.append("KNOWN_BURNED table has %d entries, expected 3" % len(KNOWN_BURNED))

    # Template files must be downgraded rather than dropped.
    checks += 1
    tmpl = scan_text("selftest", ".env.example",
                     "DEPLOY_TOKEN=t0k3n_9f4a2b7c1d8e6031\n", False, False)
    if not tmpl or tmpl[0].severity != LOW:
        failures.append("template downgrade failed: %s"
                        % ([(h.rule_id, h.severity) for h in tmpl] or "no hit"))

    print("secret_scan self-test: %d checks, %d failure(s)" % (checks, len(failures)))
    for f in failures:
        print("  " + f)
    return 1 if failures else 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: Optional[Sequence[str]] = None) -> int:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(
        description="Pre-publication secret scan for the Helix Core repository.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--path", default=here, help="repository root (default: repo containing this script)")
    ap.add_argument("--scope", default="worktree,index",
                    help="comma list of worktree,index,history or 'all' (default: worktree,index)")
    ap.add_argument("--json", dest="json_out", default=None, help="write findings as JSON to this file")
    ap.add_argument("--show-secrets", action="store_true",
                    help="print matched values in full instead of redacting them")
    ap.add_argument("--entropy", action="store_true",
                    help="enable the high-entropy literal heuristic (noisy)")
    ap.add_argument("--all-files", action="store_true",
                    help="also walk build-output and runtime directories (%s)"
                         % ", ".join(sorted(ARTIFACT_SKIP_DIRS)))
    ap.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES,
                    help="skip files larger than this (default: %d)" % DEFAULT_MAX_BYTES)
    ap.add_argument("--history-limit", type=int, default=0,
                    help="scan at most N commits in history scope (0 = all)")
    ap.add_argument("--verify-excluded", action="store_true",
                    help="run the Phase 6.2 index inclusion/exclusion audit")
    ap.add_argument("--no-external", action="store_true",
                    help="do not invoke gitleaks/trufflehog even if installed")
    ap.add_argument("--fail-on", default="MEDIUM",
                    choices=[CRITICAL, HIGH, MEDIUM, LOW, INFO],
                    help="minimum severity that makes the run exit non-zero (default: MEDIUM)")
    ap.add_argument("--selftest", action="store_true",
                    help="run the built-in rule fixtures and exit (no repository scan)")
    args = ap.parse_args(argv)

    if args.selftest:
        return run_selftest()

    root = os.path.abspath(args.path)
    if not os.path.isdir(root):
        print("error: %s is not a directory" % root, file=sys.stderr)
        return 2

    scopes = ["worktree", "index", "history"] if args.scope.strip().lower() == "all" \
        else [s.strip().lower() for s in args.scope.split(",") if s.strip()]
    for s in scopes:
        if s not in ("worktree", "index", "history"):
            print("error: unknown scope %r" % s, file=sys.stderr)
            return 2

    repo = is_git_repo(root)
    if not repo and ("index" in scopes or "history" in scopes or args.verify_excluded):
        print("error: %s is not a git repository; index/history scopes unavailable" % root,
              file=sys.stderr)
        return 2

    findings: List[Finding] = []
    notes: List[str] = []
    stats: Dict[str, object] = {
        "root": root, "scopes": scopes, "entropy": args.entropy, "all_files": args.all_files,
    }

    if not args.no_external:
        ext_findings, ext_notes = run_external(root)
        findings.extend(ext_findings)
        notes.extend(ext_notes)
    else:
        notes.append("external scanners skipped (--no-external).")

    if "worktree" in scopes:
        f, n = scan_worktree(root, args.all_files, args.max_bytes,
                             args.show_secrets, args.entropy)
        findings.extend(f)
        stats["worktree_files"] = n

    if "index" in scopes:
        f, n = scan_index(root, args.max_bytes, args.show_secrets, args.entropy)
        findings.extend(f)
        stats["index_files"] = n

    if "history" in scopes:
        f, n = scan_history(root, args.max_bytes, args.show_secrets,
                            args.entropy, args.history_limit)
        findings.extend(f)
        stats["history_blobs"] = n

    audit_rows = None
    if args.verify_excluded:
        audit_rows, audit_findings = verify_index_contents(root)
        findings.extend(audit_findings)

    findings = _dedupe(findings)
    report = render_report(findings, stats, audit_rows, notes)
    print(report)

    if args.json_out:
        payload = {
            "stats": {k: v for k, v in stats.items()},
            "notes": notes,
            "audit": audit_rows,
            "findings": [f.to_dict() for f in sorted(findings, key=lambda x: x.sort_key())],
        }
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        print("JSON report written to %s" % args.json_out)

    threshold = SEVERITY_ORDER[args.fail_on]
    blocking = [f for f in findings if SEVERITY_ORDER[f.severity] >= threshold]
    if blocking:
        print("\nFAIL: %d finding(s) at or above %s." % (len(blocking), args.fail_on))
        return 1
    print("\nOK: no findings at or above %s." % args.fail_on)
    return 0


if __name__ == "__main__":
    sys.exit(main())
