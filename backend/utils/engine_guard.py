"""
Engine identity guard — Helix Core.

Why this module exists
----------------------
:func:`backend.config.find_vina` resolves the first ``vina`` it can find, and on a
Linux host that is normally whatever conda-forge or the distribution installed.
The conda-forge package reports::

    AutoDock Vina f458505-mod

a *modified* build of 1.2.7 carrying no release tag, while every docking number in
the manuscript comes from the official v1.2.6 release assets::

    AutoDock Vina v1.2.6-56-gc28e340    (Windows, bundled under tools/)
    AutoDock Vina v1.2.6-27-gbe1689c    (Linux, upstream linux_x86_64 asset)

Upstream builds the two platform assets from different commits, so the trailing
``git describe`` suffix legitimately differs between them; the *release tag* is what
must agree. Scores from the modified build are not comparable with either.

Benchmark provenance capture records whatever ``vina --version`` prints. Without
this comparison, a substituted engine would be invisible in an evidence bundle;
this module closes that hole.

Two entry points, deliberately different in severity:

``warn_if_unexpected_engines()``
    Never raises. Logs loudly. Safe to call from application startup, so an
    ordinary user who installed a different Vina still gets a working application.

``require_measurement_engines()``
    Raises :class:`EngineMismatchError`. Called by anything that writes a number
    into an evidence bundle.

The check cannot be switched off for a measurement run. ``HELIX_ENGINE_CHECK=0``
silences the *startup warning* only. To measure on a different release you must
*declare* it through ``HELIX_EXPECTED_VINA``, and the declaration is then part of
the report embedded in the bundle — the substitution stays visible either way.

One thing cannot be declared away: a build carrying a modification marker
(``-mod``, ``-dirty``, ``-patched``) is refused unconditionally, before any
comparison happens. There is no upstream artefact a reader could obtain to
reproduce such a run, so no expectation can make it quotable.

Open Babel caveat
-----------------
The bundled Open Babel is conda-forge 3.1.1, but the binary self-reports
``Open Babel 3.1.0``: a known upstream packaging quirk recorded in
``tools/OpenBabel/SOURCE.md``. The comparison carries an explicit, directional
alias for that one pair so the quirk is accepted without weakening the check for
any other version. The alias is reported in the provenance block whenever it is
applied, because 3.1.0 and 3.1.1 are genuinely indistinguishable from the version
string alone.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from backend import config

logger = logging.getLogger(__name__)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

VINA = "vina"
OPENBABEL = "openbabel"
DEFAULT_ENGINES: tuple[str, ...] = (VINA, OPENBABEL)

__all__ = [
    "VINA",
    "OPENBABEL",
    "DEFAULT_ENGINES",
    "EngineStatus",
    "EngineReport",
    "EngineMismatchError",
    "ParsedVersion",
    "parse_version",
    "check_engine",
    "check_engines",
    "warn_if_unexpected_engines",
    "require_measurement_engines",
    "provenance_block",
    "describe",
]


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------

#: ``(returncode, combined_output)``.
ProbeResult = tuple[int, str]

#: A probe runs ``executable version_args`` and returns :data:`ProbeResult`.
#: It may raise; the caller turns any exception into an ``UNREADABLE`` report.
Probe = Callable[[str, Sequence[str], "Mapping[str, str] | None"], ProbeResult]

#: Printing a version banner is instantaneous; anything slower is a hung binary.
_PROBE_TIMEOUT_S = 30.0


def _default_probe(
    executable: str,
    args: Sequence[str],
    env: Mapping[str, str] | None,
) -> ProbeResult:
    """Run ``executable args`` and return its exit code and version banner."""
    completed = subprocess.run(
        [executable, *args],
        capture_output=True,
        text=True,
        timeout=_PROBE_TIMEOUT_S,
        env=dict(env) if env is not None else None,
        creationflags=_NO_WINDOW,
    )
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    return completed.returncode, stdout or stderr


# ---------------------------------------------------------------------------
# Engine specifications
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EngineSpec:
    """Everything version-checking needs to know about one external engine."""

    key: str
    label: str
    version_args: tuple[str, ...]
    #: Product-name prefix, stripped before searching for a version number so a
    #: digit inside the product name can never be read as a version.
    banner: re.Pattern[str]
    #: Directional ``(reported_release, expected_release, why)`` exemptions for
    #: binaries whose self-reported version is known to be wrong.
    self_report_aliases: tuple[tuple[str, str, str], ...] = ()
    #: Appended to the failure message. Tells the operator how to get it right.
    remediation: str = ""
    #: Probe through ``backend.utils.paths.get_obabel_env()``. BABEL_DATADIR has to
    #: match the resolved binary or plugin loading fails, and `obabel -V` can die
    #: before it prints anything.
    needs_obabel_env: bool = False


_VINA_REMEDIATION = (
    "Install the official release asset rather than the conda-forge package:\n"
    "    curl -fsSL -o vina https://github.com/ccsb-scripps/AutoDock-Vina/"
    "releases/download/v1.2.6/vina_1.2.6_linux_x86_64\n"
    "    sha256sum vina  # 06dfe473434e666723436f6bc9379d6ea7ba75a19203feb00c1196ec3a1593e0\n"
    "then point HELIX_VINA at it. To measure on a different *release* on purpose, "
    "declare it in HELIX_EXPECTED_VINA and the declaration is recorded in the bundle. "
    "A build that self-identifies as modified cannot be declared acceptable at all: "
    "there is no upstream artefact anyone could reproduce it from."
)

_OBABEL_REMEDIATION = (
    "Install conda-forge openbabel 3.1.1, or point HELIX_OBABEL at the bundled "
    "tools/OpenBabel build. To measure on a different release on purpose, declare it "
    "in HELIX_EXPECTED_OBABEL and the declaration is recorded in the bundle."
)

_SPECS: dict[str, EngineSpec] = {
    VINA: EngineSpec(
        key=VINA,
        label="AutoDock Vina",
        version_args=("--version",),
        banner=re.compile(r"^\s*AutoDock\s+Vina\b\s*", re.IGNORECASE),
        remediation=_VINA_REMEDIATION,
    ),
    OPENBABEL: EngineSpec(
        key=OPENBABEL,
        label="Open Babel",
        version_args=("-V",),
        banner=re.compile(r"^\s*Open\s+Babel\b\s*", re.IGNORECASE),
        self_report_aliases=(
            (
                "3.1.0",
                "3.1.1",
                "the Open Babel 3.1.1 binaries self-report 3.1.0 — a known upstream "
                "packaging quirk, documented in tools/OpenBabel/SOURCE.md",
            ),
        ),
        remediation=_OBABEL_REMEDIATION,
        needs_obabel_env=True,
    ),
}


def _spec(engine: str) -> EngineSpec:
    try:
        return _SPECS[engine]
    except KeyError:
        raise ValueError(
            f"unknown engine {engine!r}; expected one of {sorted(_SPECS)}"
        ) from None


def _resolve_default(engine: str) -> str | None:
    """Locate *engine* the same way the running application would."""
    if engine == VINA:
        return config.find_vina()
    if engine == OPENBABEL:
        # get_obabel() returns the bundled path even when the file is absent so
        # that callers can name a concrete location; the caller checks existence.
        return config.get_obabel()
    raise ValueError(f"unknown engine {engine!r}")


def _probe_env(spec: EngineSpec) -> Mapping[str, str] | None:
    """The environment the version probe runs in, or None to inherit."""
    if not spec.needs_obabel_env:
        return None
    from backend.utils.paths import get_obabel_env

    return get_obabel_env()


# ---------------------------------------------------------------------------
# Version parsing
# ---------------------------------------------------------------------------

# A release number needs at least major.minor so that a bare git hash such as
# "f458505" is never mistaken for a version.
_RELEASE_RE = re.compile(
    r"(?<![\w.])v?(?P<release>\d+\.\d+(?:\.\d+)*)"
    r"(?:-(?P<build>[0-9A-Za-z][0-9A-Za-z._+-]*))?"
)

# Markers by which a build declares itself not to be an upstream release.
# "v1.2.6-56-gc28e340" is `git describe` output for an upstream commit and is not
# a modification marker; "f458505-mod" is.
_MODIFIED_RE = re.compile(r"(?:^|[-_+\s])(mod|modified|dirty|patched)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedVersion:
    """A version banner broken into the parts the comparison cares about."""

    raw: str
    release: str | None
    build: str | None
    modified: bool

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.raw


def _first_nonempty_line(text: str) -> str:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def parse_version(text: str, spec: EngineSpec | None = None) -> ParsedVersion:
    """Parse a version banner into release / build / modified-marker parts.

    Only the first non-empty line is considered: ``obabel -V`` appends a build
    date, and a mis-invoked binary can emit a usage block underneath.
    """
    line = _first_nonempty_line(text)
    body = spec.banner.sub("", line, count=1) if spec is not None else line
    match = _RELEASE_RE.search(body)
    return ParsedVersion(
        raw=line,
        release=match.group("release") if match else None,
        build=match.group("build") if match else None,
        modified=bool(_MODIFIED_RE.search(line)),
    )


def _alias_for(spec: EngineSpec, reported: str, expected: str) -> str | None:
    for reported_release, expected_release, why in spec.self_report_aliases:
        if reported == reported_release and expected == expected_release:
            return why
    return None


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


class EngineStatus(str, Enum):
    """Outcome of one engine check.

    Only :attr:`OK` is acceptable for a measurement run.
    """

    OK = "ok"
    MISMATCH = "mismatch"
    MODIFIED_BUILD = "modified_build"
    UNPARSEABLE = "unparseable"
    MISSING = "missing"
    UNREADABLE = "unreadable"
    UNDECLARED = "undeclared"
    SKIPPED = "skipped"


#: Statuses that warrant an error-level log line rather than a warning.
_LOUD = frozenset(
    {EngineStatus.MISMATCH, EngineStatus.MODIFIED_BUILD, EngineStatus.UNPARSEABLE}
)


@dataclass(frozen=True)
class EngineReport:
    """What one engine is, what it was expected to be, and whether that is fine."""

    engine: str
    label: str
    status: EngineStatus
    detail: str
    path: str | None = None
    raw_version: str | None = None
    release: str | None = None
    build: str | None = None
    expected: str | None = None
    self_report_alias_applied: bool = False

    @property
    def ok(self) -> bool:
        """True when the resolved engine is the declared one."""
        return self.status is EngineStatus.OK

    @property
    def acceptable_for_measurement(self) -> bool:
        """True only when this engine may back a recorded measurement.

        Everything other than an affirmative match is refused, including
        "could not tell" states such as a missing binary or an undeclared
        expectation. An unverifiable engine is not a verified one.
        """
        return self.status is EngineStatus.OK

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for embedding in an evidence bundle."""
        return {
            "engine": self.engine,
            "label": self.label,
            "status": self.status.value,
            "detail": self.detail,
            "path": self.path,
            "reported_version": self.raw_version,
            "reported_release": self.release,
            "reported_build": self.build,
            "expected": self.expected,
            "self_report_alias_applied": self.self_report_alias_applied,
            "acceptable_for_measurement": self.acceptable_for_measurement,
        }

    def one_line(self) -> str:
        return f"[{self.status.value}] {self.label}: {self.detail}"


class EngineMismatchError(RuntimeError):
    """Raised when a measurement run would use an engine it did not declare."""

    def __init__(self, reports: Mapping[str, EngineReport]) -> None:
        self.reports: dict[str, EngineReport] = dict(reports)
        self.failures: tuple[EngineReport, ...] = tuple(
            report
            for report in self.reports.values()
            if not report.acceptable_for_measurement
        )
        super().__init__(self._message())

    def _message(self) -> str:
        lines = [
            "Refusing to record a measurement run: the resolved engine is not the "
            "declared one.",
        ]
        for report in self.failures:
            lines.append(f"  - {report.one_line()}")
            spec = _SPECS.get(report.engine)
            if spec is not None and spec.remediation:
                lines.extend(f"      {piece}" for piece in spec.remediation.splitlines())
        lines.append(
            "  Docking scores from a different engine are not comparable with the "
            "reported results."
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------


def _is_usable_file(path: str | None) -> bool:
    if not path:
        return False
    try:
        return Path(path).is_file()
    except OSError:  # pragma: no cover - defensive, e.g. a path too long
        return False


def check_engine(
    engine: str,
    *,
    expected: str | None = None,
    path: str | None = None,
    resolve: Callable[[], str | None] | None = None,
    probe: Probe | None = None,
) -> EngineReport:
    """Resolve *engine*, read its version, and compare it against expectation.

    Parameters
    ----------
    expected:
        The declared version, e.g. ``"v1.2.6"``. ``None`` means "read it from
        :func:`backend.config.expected_engine_version`", which itself returns
        ``None`` when the expectation has been explicitly withdrawn.
    path / resolve:
        Test and caller seams. ``path`` pins the executable outright; ``resolve``
        replaces the locator. Neither is needed in normal use.
    probe:
        Replaces the ``--version`` subprocess. Any exception it raises becomes an
        ``UNREADABLE`` report rather than propagating.

    Never raises for an engine-related reason; every failure mode is a status.
    """
    spec = _spec(engine)
    declared = expected if expected is not None else config.expected_engine_version(engine)

    if path is not None:
        resolved: str | None = path
    elif resolve is not None:
        resolved = resolve()
    else:
        resolved = _resolve_default(engine)

    base = EngineReport(
        engine=spec.key,
        label=spec.label,
        status=EngineStatus.MISSING,
        detail="",
        path=resolved,
        expected=declared,
    )

    if not _is_usable_file(resolved):
        where = f" at {resolved}" if resolved else ""
        return replace(
            base,
            status=EngineStatus.MISSING,
            detail=(
                f"{spec.label} could not be resolved{where}. Nothing can be measured "
                f"with an engine that is not there."
            ),
        )

    runner = probe if probe is not None else _default_probe
    try:
        returncode, output = runner(resolved, spec.version_args, _probe_env(spec))
    except Exception as exc:  # noqa: BLE001 - any failure is the same outcome here
        return replace(
            base,
            status=EngineStatus.UNREADABLE,
            detail=(
                f"{spec.label} at {resolved} could not be asked for its version: "
                f"{type(exc).__name__}: {exc}"
            ),
        )

    reported = parse_version(output, spec)
    base = replace(
        base,
        raw_version=reported.raw or None,
        release=reported.release,
        build=reported.build,
    )

    if returncode != 0 and reported.release is None:
        return replace(
            base,
            status=EngineStatus.UNREADABLE,
            detail=(
                f"{spec.label} at {resolved} exited {returncode} without printing a "
                f"version (output: {reported.raw or '<empty>'!r})."
            ),
        )

    if reported.modified:
        return replace(
            base,
            status=EngineStatus.MODIFIED_BUILD,
            detail=(
                f"{spec.label} reports {reported.raw!r} — a modified build, not an "
                f"upstream release"
                + (f" (expected {declared})" if declared else "")
                + ". Its results are not comparable with the reported ones."
            ),
        )

    if reported.release is None:
        return replace(
            base,
            status=EngineStatus.UNPARSEABLE,
            detail=(
                f"{spec.label} reports {reported.raw or '<empty>'!r}, which carries no "
                f"recognisable release number, so it cannot be checked against "
                f"{declared or 'anything'}."
            ),
        )

    if declared is None:
        return replace(
            base,
            status=EngineStatus.UNDECLARED,
            detail=(
                f"{spec.label} reports {reported.raw!r}, but no expected version is "
                f"declared, so nothing was verified. Set the expectation before "
                f"recording a measurement."
            ),
        )

    wanted = parse_version(declared, spec)
    if wanted.release is None:
        return replace(
            base,
            status=EngineStatus.UNPARSEABLE,
            detail=(
                f"the declared expectation {declared!r} carries no recognisable "
                f"release number, so {spec.label} {reported.raw!r} cannot be checked "
                f"against it."
            ),
        )

    if reported.release == wanted.release:
        if wanted.build and reported.build != wanted.build:
            return replace(
                base,
                status=EngineStatus.MISMATCH,
                detail=(
                    f"{spec.label} release {reported.release} matches, but the build "
                    f"string does not: reported {reported.build or '<none>'}, declared "
                    f"{wanted.build}."
                ),
            )
        return replace(
            base,
            status=EngineStatus.OK,
            detail=(
                f"{spec.label} reports {reported.raw!r}, which matches the declared "
                f"{declared}"
                + (f" (build {reported.build})" if reported.build else "")
                + "."
            ),
        )

    alias = _alias_for(spec, reported.release, wanted.release)
    if alias is not None:
        return replace(
            base,
            status=EngineStatus.OK,
            detail=(
                f"{spec.label} reports {reported.raw!r} and the declared version is "
                f"{declared}; accepted because {alias}."
            ),
            self_report_alias_applied=True,
        )

    return replace(
        base,
        status=EngineStatus.MISMATCH,
        detail=(
            f"{spec.label} reports {reported.raw!r} (release {reported.release}) but "
            f"{declared} was declared. Results from the two are not comparable."
        ),
    )


def check_engines(
    engines: Sequence[str] = DEFAULT_ENGINES,
    *,
    expected: Mapping[str, str | None] | None = None,
    probe: Probe | None = None,
) -> dict[str, EngineReport]:
    """Run :func:`check_engine` over several engines. Never raises."""
    overrides = dict(expected or {})
    return {
        engine: check_engine(engine, expected=overrides.get(engine), probe=probe)
        for engine in engines
    }


# ---------------------------------------------------------------------------
# The two entry points
# ---------------------------------------------------------------------------


def warn_if_unexpected_engines(
    engines: Sequence[str] = DEFAULT_ENGINES,
    *,
    expected: Mapping[str, str | None] | None = None,
    probe: Probe | None = None,
    force: bool = False,
) -> dict[str, EngineReport]:
    """Startup check. Logs loudly, **never raises**, never blocks the application.

    A user who installed their own Vina is entitled to a working application; they
    are not entitled to a silent one. Mismatches log at ``ERROR`` with the exact
    version strings and how to fix it, and the application continues.

    ``HELIX_ENGINE_CHECK=0`` skips the probe entirely for casual, non-measurement
    use. ``force=True`` runs it anyway. This switch has no effect on
    :func:`require_measurement_engines`.
    """
    if not force and not config.engine_check_enabled():
        return {
            engine: EngineReport(
                engine=engine,
                label=_spec(engine).label,
                status=EngineStatus.SKIPPED,
                detail=(
                    f"engine check disabled by {config.ENGINE_CHECK_ENV}; no "
                    f"measurement may be recorded in this configuration"
                ),
                expected=None,
            )
            for engine in engines
        }

    reports = check_engines(engines, expected=expected, probe=probe)
    for report in reports.values():
        if report.status is EngineStatus.OK:
            logger.info("%s", report.one_line())
        elif report.status in _LOUD:
            spec = _SPECS.get(report.engine)
            logger.error(
                "ENGINE MISMATCH — %s\n  %s\n  This is fine for interactive use, but "
                "no measurement recorded on this engine is comparable with the "
                "published results.%s",
                report.label,
                report.detail,
                f"\n  {spec.remediation}" if spec and spec.remediation else "",
            )
        else:
            logger.warning("%s", report.one_line())
    return reports


def require_measurement_engines(
    engines: Sequence[str] = DEFAULT_ENGINES,
    *,
    expected: Mapping[str, str | None] | None = None,
    probe: Probe | None = None,
) -> dict[str, EngineReport]:
    """Gate for anything that writes a number into an evidence bundle.

    Returns the reports on success so the caller can embed them in the run
    metadata; raises :class:`EngineMismatchError` otherwise.

    This deliberately ignores ``HELIX_ENGINE_CHECK``. If one environment variable
    could switch the guard off, the guard would not be one. The supported way to
    measure on a different engine is to *declare* it via ``HELIX_EXPECTED_VINA`` /
    ``HELIX_EXPECTED_OBABEL``, which puts the declaration into the bundle.
    """
    reports = check_engines(engines, expected=expected, probe=probe)
    if any(not report.acceptable_for_measurement for report in reports.values()):
        raise EngineMismatchError(reports)
    return reports


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def provenance_block(reports: Mapping[str, EngineReport]) -> dict[str, Any]:
    """JSON-serialisable summary for the ``tools`` section of a run's metadata."""
    return {
        "schema": "helix.engine_guard/1",
        "checked_at_utc": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "all_acceptable_for_measurement": all(
            report.acceptable_for_measurement for report in reports.values()
        ),
        "engines": {key: report.as_dict() for key, report in reports.items()},
    }


def describe(reports: Mapping[str, EngineReport]) -> str:
    """Human-readable multi-line summary, for CLI output."""
    return "\n".join(report.one_line() for report in reports.values())
