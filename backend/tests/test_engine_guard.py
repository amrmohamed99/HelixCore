"""Tests for the engine identity guard (`backend/utils/engine_guard.py`).

Plan item 1.2a: `find_vina()` resolves whatever `vina` is on PATH, and in WSL that
is the conda-forge build reporting "AutoDock Vina f458505-mod" — a modified 1.2.7,
not the v1.2.6 the manuscript reports. The provenance capture recorded whatever
`vina --version` printed without comparing it against anything, so the swap was
invisible in the evidence bundle.

These tests pin the behaviour that closes that hole:

* the two official v1.2.6 build strings (Windows and Linux differ upstream) match;
* the conda-forge "-mod" string is refused for a measurement run;
* a binary that is absent, or present but unreadable, is refused rather than
  silently skipped;
* Open Babel 3.1.1 self-reporting "3.1.0" is *not* treated as a mismatch, and the
  exemption is directional and narrow;
* startup warns and never raises, while the measurement gate raises and cannot be
  switched off by the same environment variable that silences startup.

No real binary is required: the version probe is injected. One optional test at the
end runs the genuinely resolved engines and skips when they are not installed.
"""

import logging

import pytest

from backend import config
from backend.utils import engine_guard
from backend.utils.engine_guard import (
    OPENBABEL,
    VINA,
    EngineMismatchError,
    EngineStatus,
    check_engine,
    parse_version,
    provenance_block,
    require_measurement_engines,
    warn_if_unexpected_engines,
)


# --- Version banners observed in the wild -----------------------------------
# tools/vina.exe --version              (bundled Windows, official v1.2.6 asset)
VINA_WINDOWS = "AutoDock Vina v1.2.6-56-gc28e340"
# ~/helix-tools/vina --version          (official v1.2.6 linux_x86_64 asset)
VINA_LINUX_OFFICIAL = "AutoDock Vina v1.2.6-27-gbe1689c"
# conda-forge `vina` resolved from PATH inside WSL — the substitution in 1.2a
VINA_CONDA_FORGE_MOD = "AutoDock Vina f458505-mod"
# tools/OpenBabel/obabel.exe -V         (conda-forge 3.1.1, mislabelled upstream)
OBABEL_BUNDLED = "Open Babel 3.1.0 -- Nov 30 2023 -- 20:56:55"
OBABEL_HONEST_311 = "Open Babel 3.1.1 -- Jan 15 2024 -- 09:12:03"
# the version bundled through manuscript v10
OBABEL_LEGACY_241 = "Open Babel 2.4.1 -- Feb 15 2017 -- 12:00:00"


def probe_returning(text: str, returncode: int = 0):
    """A version probe that reports `text` without running anything."""

    def _probe(_executable, _args, _env):
        return returncode, text

    return _probe


def probe_raising(exc: Exception):
    def _probe(_executable, _args, _env):
        raise exc

    return _probe


@pytest.fixture
def present(tmp_path):
    """A path that exists, standing in for a resolved executable."""
    binary = tmp_path / "vina"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    return str(binary)


@pytest.fixture(autouse=True)
def clean_engine_env(monkeypatch):
    """Never inherit an expectation from the developer's shell."""
    for name in ("HELIX_EXPECTED_VINA", "HELIX_EXPECTED_OBABEL", "HELIX_ENGINE_CHECK"):
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

PARSE_CASES = [
    (VINA_WINDOWS, VINA, "1.2.6", "56-gc28e340", False, "official Windows asset"),
    (VINA_LINUX_OFFICIAL, VINA, "1.2.6", "27-gbe1689c", False, "official Linux asset"),
    (VINA_CONDA_FORGE_MOD, VINA, None, None, True, "conda-forge modified build"),
    (OBABEL_BUNDLED, OPENBABEL, "3.1.0", None, False, "build date is not a version"),
    (OBABEL_LEGACY_241, OPENBABEL, "2.4.1", None, False, "the v10 Open Babel"),
]


@pytest.mark.parametrize("text,engine,release,build,modified,rationale", PARSE_CASES)
def test_parse_version_splits_release_from_build(
    text, engine, release, build, modified, rationale
):
    parsed = parse_version(text, engine_guard._SPECS[engine])
    assert parsed.release == release, rationale
    assert parsed.build == build, rationale
    assert parsed.modified is modified, rationale
    assert parsed.raw == text


def test_bare_git_hash_is_not_read_as_a_version_number():
    """"f458505" must not be mined for digits — that would fake a match."""
    parsed = parse_version(VINA_CONDA_FORGE_MOD, engine_guard._SPECS[VINA])
    assert parsed.release is None


def test_upstream_git_describe_suffix_is_not_a_modification_marker():
    """"-56-gc28e340" is upstream `git describe` output, not a local patch."""
    assert parse_version(VINA_WINDOWS, engine_guard._SPECS[VINA]).modified is False


# ---------------------------------------------------------------------------
# Exact match — both official v1.2.6 builds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "banner,rationale",
    [
        (VINA_WINDOWS, "bundled Windows build"),
        (VINA_LINUX_OFFICIAL, "official Linux release asset"),
    ],
)
def test_official_v126_builds_match_the_declared_version(present, banner, rationale):
    """Upstream builds the two platform assets from different commits; the release
    tag is what must agree, so both are acceptable for a measurement run."""
    report = check_engine(
        VINA, expected="v1.2.6", path=present, probe=probe_returning(banner)
    )
    assert report.status is EngineStatus.OK, rationale
    assert report.acceptable_for_measurement is True
    assert report.release == "1.2.6"
    assert report.raw_version == banner
    assert report.self_report_alias_applied is False


def test_matching_engines_let_a_measurement_run_proceed(present, monkeypatch):
    monkeypatch.setattr(engine_guard, "_resolve_default", lambda _engine: present)
    reports = require_measurement_engines(
        probe=lambda executable, args, env: (
            0,
            VINA_WINDOWS if "--version" in args else OBABEL_BUNDLED,
        )
    )
    assert {key: report.status for key, report in reports.items()} == {
        VINA: EngineStatus.OK,
        OPENBABEL: EngineStatus.OK,
    }


def test_declaring_a_full_build_string_pins_the_exact_build(present):
    """An operator who declares the build, not just the tag, gets the stricter check."""
    ok = check_engine(
        VINA,
        expected="v1.2.6-56-gc28e340",
        path=present,
        probe=probe_returning(VINA_WINDOWS),
    )
    assert ok.status is EngineStatus.OK

    cross_platform = check_engine(
        VINA,
        expected="v1.2.6-56-gc28e340",
        path=present,
        probe=probe_returning(VINA_LINUX_OFFICIAL),
    )
    assert cross_platform.status is EngineStatus.MISMATCH
    assert "build string" in cross_platform.detail


# ---------------------------------------------------------------------------
# The conda-forge '-mod' build — the substitution 1.2a is about
# ---------------------------------------------------------------------------


def test_conda_forge_mod_build_is_flagged_as_modified(present):
    report = check_engine(
        VINA,
        expected="v1.2.6",
        path=present,
        probe=probe_returning(VINA_CONDA_FORGE_MOD),
    )
    assert report.status is EngineStatus.MODIFIED_BUILD
    assert report.acceptable_for_measurement is False
    assert report.raw_version == VINA_CONDA_FORGE_MOD
    assert "not comparable" in report.detail


def test_conda_forge_mod_build_refuses_a_measurement_run(present, monkeypatch):
    monkeypatch.setattr(engine_guard, "_resolve_default", lambda _engine: present)
    with pytest.raises(EngineMismatchError) as excinfo:
        require_measurement_engines(
            engines=(VINA,), probe=probe_returning(VINA_CONDA_FORGE_MOD)
        )
    message = str(excinfo.value)
    assert VINA_CONDA_FORGE_MOD in message
    assert "vina_1.2.6_linux_x86_64" in message, "the fix must be in the message"
    assert excinfo.value.failures[0].engine == VINA


def test_conda_forge_mod_build_warns_but_never_blocks_startup(
    present, monkeypatch, caplog
):
    """An ordinary user with a different Vina gets a working application — loudly."""
    monkeypatch.setattr(engine_guard, "_resolve_default", lambda _engine: present)
    with caplog.at_level(logging.INFO, logger=engine_guard.logger.name):
        reports = warn_if_unexpected_engines(
            engines=(VINA,), probe=probe_returning(VINA_CONDA_FORGE_MOD)
        )
    assert reports[VINA].status is EngineStatus.MODIFIED_BUILD
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1, "the mismatch must be loud, not a debug line"
    assert VINA_CONDA_FORGE_MOD in errors[0].getMessage()


def test_a_mod_marker_is_refused_even_when_the_release_tag_matches(present):
    """A locally patched v1.2.6 is still not the v1.2.6 the paper reports."""
    report = check_engine(
        VINA,
        expected="v1.2.6",
        path=present,
        probe=probe_returning("AutoDock Vina v1.2.6-mod"),
    )
    assert report.status is EngineStatus.MODIFIED_BUILD


@pytest.mark.parametrize("declared", ["f458505-mod", "1.2.7", "any"])
def test_a_modified_build_cannot_be_declared_acceptable(present, monkeypatch, declared):
    """No expectation makes a modified build quotable.

    There is no upstream artefact a reader could obtain to reproduce it, so the
    modification marker short-circuits ahead of every comparison — including the
    escape hatch that legitimises a different *release*.
    """
    monkeypatch.setenv("HELIX_EXPECTED_VINA", declared)
    monkeypatch.setattr(engine_guard, "_resolve_default", lambda _engine: present)
    report = check_engine(VINA, path=present, probe=probe_returning(VINA_CONDA_FORGE_MOD))
    assert report.status is EngineStatus.MODIFIED_BUILD
    with pytest.raises(EngineMismatchError):
        require_measurement_engines(
            engines=(VINA,), probe=probe_returning(VINA_CONDA_FORGE_MOD)
        )


def test_a_different_release_can_be_declared_and_is_then_recorded(present, monkeypatch):
    """The supported escape hatch: declare the release, do not disable the check."""
    monkeypatch.setenv("HELIX_EXPECTED_VINA", "v1.2.7")
    monkeypatch.setattr(engine_guard, "_resolve_default", lambda _engine: present)
    reports = require_measurement_engines(
        engines=(VINA,), probe=probe_returning("AutoDock Vina v1.2.7-1-gdeadbee")
    )
    block = provenance_block(reports)
    assert block["engines"][VINA]["expected"] == "v1.2.7", (
        "the substitution must be visible in the bundle, not hidden by it"
    )


def test_a_different_release_is_a_plain_mismatch(present):
    report = check_engine(
        VINA,
        expected="v1.2.6",
        path=present,
        probe=probe_returning("AutoDock Vina v1.2.7"),
    )
    assert report.status is EngineStatus.MISMATCH
    assert report.acceptable_for_measurement is False
    assert "1.2.7" in report.detail and "v1.2.6" in report.detail


# ---------------------------------------------------------------------------
# Missing / unreadable binary
# ---------------------------------------------------------------------------


def test_unresolvable_binary_is_missing_not_ok():
    report = check_engine(VINA, expected="v1.2.6", resolve=lambda: None)
    assert report.status is EngineStatus.MISSING
    assert report.acceptable_for_measurement is False
    assert report.path is None
    assert report.raw_version is None


def test_resolved_but_absent_binary_is_missing(tmp_path):
    """get_obabel() returns the bundled path even when the file is not there."""
    absent = str(tmp_path / "OpenBabel" / "obabel")
    report = check_engine(OPENBABEL, expected="3.1.1", resolve=lambda: absent)
    assert report.status is EngineStatus.MISSING
    assert absent in report.detail


def test_missing_binary_refuses_a_measurement_run(monkeypatch):
    monkeypatch.setattr(engine_guard, "_resolve_default", lambda _engine: None)
    with pytest.raises(EngineMismatchError) as excinfo:
        require_measurement_engines(engines=(VINA,))
    assert excinfo.value.failures[0].status is EngineStatus.MISSING


def test_missing_binary_warns_without_raising(monkeypatch, caplog):
    monkeypatch.setattr(engine_guard, "_resolve_default", lambda _engine: None)
    with caplog.at_level(logging.INFO, logger=engine_guard.logger.name):
        reports = warn_if_unexpected_engines(engines=(VINA,))
    assert reports[VINA].status is EngineStatus.MISSING
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_a_binary_that_cannot_be_run_is_unreadable(present):
    report = check_engine(
        VINA,
        expected="v1.2.6",
        path=present,
        probe=probe_raising(OSError("Exec format error")),
    )
    assert report.status is EngineStatus.UNREADABLE
    assert report.acceptable_for_measurement is False
    assert "Exec format error" in report.detail


def test_a_binary_that_errors_without_a_version_is_unreadable(present):
    report = check_engine(
        VINA,
        expected="v1.2.6",
        path=present,
        probe=probe_returning("usage: vina [options]", returncode=1),
    )
    assert report.status is EngineStatus.UNREADABLE


# ---------------------------------------------------------------------------
# Open Babel 3.1.0 / 3.1.1 self-report quirk
# ---------------------------------------------------------------------------


def test_open_babel_311_self_reporting_310_is_accepted(present):
    """tools/OpenBabel/SOURCE.md: the 3.1.1 binaries print "Open Babel 3.1.0"."""
    report = check_engine(
        OPENBABEL, expected="3.1.1", path=present, probe=probe_returning(OBABEL_BUNDLED)
    )
    assert report.status is EngineStatus.OK
    assert report.acceptable_for_measurement is True
    assert report.release == "3.1.0", "the raw self-report is preserved, not rewritten"
    assert report.self_report_alias_applied is True
    assert "SOURCE.md" in report.detail, "the exemption must explain itself in the bundle"


def test_open_babel_quirk_does_not_block_a_measurement_run(present, monkeypatch):
    monkeypatch.setattr(engine_guard, "_resolve_default", lambda _engine: present)
    reports = require_measurement_engines(
        engines=(OPENBABEL,), probe=probe_returning(OBABEL_BUNDLED)
    )
    assert reports[OPENBABEL].status is EngineStatus.OK


def test_open_babel_reporting_311_honestly_also_matches(present):
    report = check_engine(
        OPENBABEL,
        expected="3.1.1",
        path=present,
        probe=probe_returning(OBABEL_HONEST_311),
    )
    assert report.status is EngineStatus.OK
    assert report.self_report_alias_applied is False


def test_the_open_babel_exemption_is_narrow(present):
    """It covers exactly the 3.1.0-reported-as-3.1.1 pair and nothing else."""
    legacy = check_engine(
        OPENBABEL,
        expected="3.1.1",
        path=present,
        probe=probe_returning(OBABEL_LEGACY_241),
    )
    assert legacy.status is EngineStatus.MISMATCH, "the v10 Open Babel is not 3.1.1"

    other = check_engine(
        OPENBABEL,
        expected="3.1.1",
        path=present,
        probe=probe_returning("Open Babel 3.0.0 -- Jan 01 2020 -- 00:00:00"),
    )
    assert other.status is EngineStatus.MISMATCH


def test_the_open_babel_exemption_is_directional(present):
    """Declaring 3.1.0 and getting 3.1.1 is a real difference, not the quirk."""
    report = check_engine(
        OPENBABEL,
        expected="3.1.0",
        path=present,
        probe=probe_returning(OBABEL_HONEST_311),
    )
    assert report.status is EngineStatus.MISMATCH


def test_the_vina_check_has_no_self_report_exemptions():
    assert engine_guard._SPECS[VINA].self_report_aliases == ()


# ---------------------------------------------------------------------------
# Declaration, overrides, and the disable switch
# ---------------------------------------------------------------------------


def test_the_shipped_defaults_are_the_versions_the_paper_reports():
    assert config.expected_engine_version("vina") == "v1.2.6"
    assert config.expected_engine_version("openbabel") == "3.1.1"


def test_env_var_overrides_the_expected_version(present, monkeypatch):
    monkeypatch.setenv("HELIX_EXPECTED_VINA", "1.2.7")
    assert config.expected_engine_version("vina") == "1.2.7"

    matches = check_engine(
        VINA, path=present, probe=probe_returning("AutoDock Vina v1.2.7")
    )
    assert matches.status is EngineStatus.OK
    assert matches.expected == "1.2.7", "the declaration is recorded in the report"

    now_wrong = check_engine(VINA, path=present, probe=probe_returning(VINA_WINDOWS))
    assert now_wrong.status is EngineStatus.MISMATCH


@pytest.mark.parametrize("value", ["", "any", "*", "none", "  "])
def test_withdrawing_the_expectation_yields_undeclared(present, monkeypatch, value):
    monkeypatch.setenv("HELIX_EXPECTED_VINA", value)
    assert config.expected_engine_version("vina") is None

    report = check_engine(VINA, path=present, probe=probe_returning(VINA_WINDOWS))
    assert report.status is EngineStatus.UNDECLARED
    assert report.acceptable_for_measurement is False, (
        "an unverified engine must not back a recorded measurement"
    )
    assert report.raw_version == VINA_WINDOWS, "the version is still captured"


def test_undeclared_expectation_refuses_a_measurement_run(present, monkeypatch):
    monkeypatch.setenv("HELIX_EXPECTED_VINA", "any")
    monkeypatch.setattr(engine_guard, "_resolve_default", lambda _engine: present)
    with pytest.raises(EngineMismatchError):
        require_measurement_engines(engines=(VINA,), probe=probe_returning(VINA_WINDOWS))


@pytest.mark.parametrize("value", ["0", "false", "off", "no", "skip", "disabled", "OFF"])
def test_helix_engine_check_off_skips_the_startup_probe(monkeypatch, value):
    monkeypatch.setenv("HELIX_ENGINE_CHECK", value)
    assert config.engine_check_enabled() is False

    def _explode(*_args, **_kwargs):  # pragma: no cover - must never be called
        raise AssertionError("the probe must not run when the check is disabled")

    reports = warn_if_unexpected_engines(engines=(VINA,), probe=_explode)
    assert reports[VINA].status is EngineStatus.SKIPPED
    assert reports[VINA].acceptable_for_measurement is False


def test_disabling_the_startup_check_does_not_disable_the_measurement_gate(
    present, monkeypatch
):
    """The whole point: one env var must not be able to switch the guard off."""
    monkeypatch.setenv("HELIX_ENGINE_CHECK", "0")
    monkeypatch.setattr(engine_guard, "_resolve_default", lambda _engine: present)
    with pytest.raises(EngineMismatchError):
        require_measurement_engines(
            engines=(VINA,), probe=probe_returning(VINA_CONDA_FORGE_MOD)
        )


def test_force_runs_the_startup_check_even_when_disabled(present, monkeypatch):
    monkeypatch.setenv("HELIX_ENGINE_CHECK", "0")
    monkeypatch.setattr(engine_guard, "_resolve_default", lambda _engine: present)
    reports = warn_if_unexpected_engines(
        engines=(VINA,), probe=probe_returning(VINA_WINDOWS), force=True
    )
    assert reports[VINA].status is EngineStatus.OK


def test_unknown_engine_is_rejected_loudly():
    with pytest.raises(ValueError, match="unknown engine"):
        check_engine("autodock4")
    with pytest.raises(ValueError, match="unknown engine"):
        config.expected_engine_version("autodock4")


# ---------------------------------------------------------------------------
# Provenance block
# ---------------------------------------------------------------------------


def test_provenance_block_is_json_serialisable_and_records_the_verdict(present):
    import json

    reports = {
        VINA: check_engine(
            VINA, expected="v1.2.6", path=present, probe=probe_returning(VINA_WINDOWS)
        ),
        OPENBABEL: check_engine(
            OPENBABEL,
            expected="3.1.1",
            path=present,
            probe=probe_returning(OBABEL_BUNDLED),
        ),
    }
    block = provenance_block(reports)
    json.dumps(block)  # must not raise

    assert block["all_acceptable_for_measurement"] is True
    assert block["engines"][VINA]["reported_version"] == VINA_WINDOWS
    assert block["engines"][VINA]["expected"] == "v1.2.6"
    assert block["engines"][OPENBABEL]["self_report_alias_applied"] is True


def test_provenance_block_records_a_failed_verdict(present):
    reports = {
        VINA: check_engine(
            VINA,
            expected="v1.2.6",
            path=present,
            probe=probe_returning(VINA_CONDA_FORGE_MOD),
        )
    }
    block = provenance_block(reports)
    assert block["all_acceptable_for_measurement"] is False
    assert block["engines"][VINA]["status"] == "modified_build"


# ---------------------------------------------------------------------------
# Against the engines actually installed on this host
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("engine", [VINA, OPENBABEL])
def test_the_resolved_engine_on_this_host(engine):
    """End-to-end against the real binary, skipped where it is not installed.

    This is the test that would have caught 1.2a: in the WSL environment it fails
    with `modified_build` and names the conda-forge string.
    """
    report = check_engine(engine)
    if report.status is EngineStatus.MISSING:
        pytest.skip(f"{engine} is not installed on this host: {report.detail}")
    assert report.status is EngineStatus.OK, report.detail
