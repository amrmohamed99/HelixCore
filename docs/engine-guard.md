# Engine identity guard

Source: [`backend/utils/engine_guard.py`](../backend/utils/engine_guard.py),
with the declared versions and the environment-variable plumbing in
[`backend/config.py`](../backend/config.py).

---

## The problem it solves

`find_vina()` resolves the first AutoDock Vina it can find. On Linux that is
normally whatever conda-forge or the distribution installed, and the conda-forge
`vina` package reports:

```
AutoDock Vina f458505-mod
```

A *modified* build of a 1.2.7 development commit, carrying no release tag. Every
docking number this project reports comes from the official upstream v1.2.6 release
assets:

```
AutoDock Vina v1.2.6-56-gc28e340    (Windows, bundled under tools/)
AutoDock Vina v1.2.6-27-gbe1689c    (Linux, upstream linux_x86_64 asset)
```

Scores from the modified build are not comparable with either. And because the
build identifies itself as modified rather than as a release, there is no upstream
artifact anyone could download to reproduce a run made with it.

The failure mode this guards against is not "the wrong engine crashes". It is
worse: the wrong engine works perfectly, produces plausible numbers, and the
provenance block records the substituted version string without ever comparing it to
what was expected. The substitution is invisible in the evidence bundle. This module
closes that hole.

---

## Two entry points, deliberately different in severity

```python
from backend.utils import engine_guard
```

### `warn_if_unexpected_engines()` — for the running application

Never raises. Never blocks startup. A mismatch logs at **ERROR** with the exact
version strings and concrete remediation, and the application carries on.

A user who installed their own Vina is entitled to a working application. They are
not entitled to a *silent* one.

### `require_measurement_engines()` — for anything that records a number

Raises `EngineMismatchError`. Called by anything that writes a value into an
evidence bundle. The exception message names every failing engine, its reported
version, the declared expectation, and how to fix it.

```python
reports = engine_guard.require_measurement_engines()   # raises on any mismatch
metadata["tools"] = engine_guard.provenance_block(reports)
```

`provenance_block()` returns a JSON-serialisable record — schema
`helix.engine_guard/1` — with a UTC timestamp, a per-engine breakdown, and an
`all_acceptable_for_measurement` boolean, ready to embed in run metadata.

---

## What it actually checks

For each engine, in order:

1. **Resolve it the way the application does.** Vina through `config.find_vina()`,
   Open Babel through `config.get_obabel()` — the same resolution order the running
   app uses, so the guard cannot check one binary while the app runs another.
2. **Confirm the file exists.** A missing binary is `MISSING`, not "fine".
3. **Run the version probe** (`vina --version`, `obabel -V`) with a 30-second
   timeout. Open Babel is probed through `get_obabel_env()`, because `BABEL_DATADIR`
   has to match the resolved binary or plugin loading fails before it prints
   anything. Any exception becomes `UNREADABLE` rather than propagating.
4. **Parse the banner.** Only the first non-empty line is considered — `obabel -V`
   appends a build date, and a mis-invoked binary can emit a usage block underneath.
   The product-name prefix is stripped before searching for a number, so a digit
   inside a product name can never be read as a version. A release needs at least
   `major.minor`, so a bare git hash such as `f458505` is never mistaken for one.
5. **Refuse modification markers unconditionally.** `-mod`, `-modified`, `-dirty`,
   `-patched` → `MODIFIED_BUILD`, checked **before** any comparison. Note that
   `v1.2.6-56-gc28e340` is `git describe` output for an upstream commit and is *not*
   a modification marker; `f458505-mod` is.
6. **Compare release, then build string.** Releases must match. If the declared
   expectation also carries a build suffix, the reported build must match it too;
   if the expectation names only a release, any build of that release is accepted.
   This is what lets Windows and Linux both declare `v1.2.6` while legitimately
   reporting different `git describe` suffixes.

### Statuses

| Status | Meaning | Acceptable for a measurement? |
|---|---|---|
| `OK` | Resolved engine matches the declaration | **yes** |
| `MISMATCH` | Different release, or right release wrong build | no |
| `MODIFIED_BUILD` | Self-identifies as modified | no, and cannot be declared away |
| `UNPARSEABLE` | No recognisable release number in the banner | no |
| `MISSING` | Binary not found | no |
| `UNREADABLE` | Probe failed, timed out, or exited without a version | no |
| `UNDECLARED` | Engine is fine, but no expectation was declared | no |
| `SKIPPED` | Startup check disabled by `HELIX_ENGINE_CHECK=0` | no |

Only `OK` passes. That includes the "could not tell" states — `MISSING`,
`UNREADABLE`, `UNDECLARED`. **An unverifiable engine is not a verified one**, and a
guard that treated uncertainty as success would be decorative.

---

## Declaring a different version: `HELIX_EXPECTED_VINA`

| Variable | Default |
|---|---|
| `HELIX_EXPECTED_VINA` | `v1.2.6` |
| `HELIX_EXPECTED_OBABEL` | `3.1.1` |

The variable **replaces** the shipped default:

```bash
# Measure on 1.2.5 on purpose. The declaration is recorded in the bundle.
export HELIX_EXPECTED_VINA=v1.2.5

# Pin the build string too, not just the release.
export HELIX_EXPECTED_VINA=v1.2.6-27-gbe1689c
```

Setting it to an empty string, `any`, `*`, or `none` **withdraws** the expectation.
That silences the startup warning, but the resulting status is `UNDECLARED`, which a
measurement run refuses:

```bash
export HELIX_EXPECTED_VINA=any     # quiet startup; measurement runs still refuse
```

The design point: to measure on a different release you must **declare** it, and the
declaration then travels inside the provenance block in the evidence bundle. The
substitution stays visible either way. You cannot make it disappear — only make it
explicit.

**One thing cannot be declared away.** A build carrying a modification marker is
refused unconditionally, before any comparison happens. No value of
`HELIX_EXPECTED_VINA` makes `f458505-mod` acceptable, because there is no upstream
artifact a reader could obtain to reproduce such a run.

---

## `HELIX_ENGINE_CHECK` only silences startup

```bash
export HELIX_ENGINE_CHECK=0     # also: false, no, off, skip, disabled
```

This skips the probe at application startup — useful for casual, non-measurement use
on a machine where you already know the engine differs and do not want the error
line every time.

It has **no effect** on `require_measurement_engines()`, which ignores it
deliberately. If one environment variable could switch the guard off, the guard
would not be one.

---

## The Open Babel self-report quirk

The bundled Open Babel is conda-forge **3.1.1**, but the binary prints:

```
Open Babel 3.1.0 -- Nov 30 2023 -- 20:56:55
```

A known upstream packaging quirk, documented in `tools/OpenBabel/SOURCE.md`. The
comparison carries a single **directional** alias for exactly that pair — reported
`3.1.0` against expected `3.1.1` — so the quirk is accepted without weakening the
check for any other version. The reverse direction is not aliased, and no other pair
is.

Whenever the alias is applied, `self_report_alias_applied: true` appears in the
provenance block, because 3.1.0 and 3.1.1 are genuinely indistinguishable from the
version string alone and a reader deserves to know the acceptance rested on an
exemption rather than on a match.

---

## Checking your own install

```python
from backend.utils import engine_guard

reports = engine_guard.check_engines()          # never raises
print(engine_guard.describe(reports))
```

On a correct Windows install:

```
[ok] AutoDock Vina: AutoDock Vina reports 'AutoDock Vina v1.2.6-56-gc28e340', which matches the declared v1.2.6 (build 56-gc28e340).
[ok] Open Babel: Open Babel reports 'Open Babel 3.1.0 -- Nov 30 2023 -- 20:56:55' and the declared version is 3.1.1; accepted because the Open Babel 3.1.1 binaries self-report 3.1.0 — a known upstream packaging quirk, documented in tools/OpenBabel/SOURCE.md.
```

Or just read the version banners directly — `vina --version`, `obabel -V` — and
compare them against the table in
[installation.md](installation.md#which-autodock-vina).

CI enforces the same rule independently of this module: the Linux job runs
`vina --version` inside the built image and fails the build on `-mod`, or on
anything that is not `v1.2.6`. Two mechanisms, one rule.

---

## If the guard fires

The error message tells you what to do; the short version:

```bash
curl -fsSL -o vina \
  https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/v1.2.6/vina_1.2.6_linux_x86_64
sha256sum vina   # 06dfe473434e666723436f6bc9379d6ea7ba75a19203feb00c1196ec3a1593e0
chmod +x vina
export HELIX_VINA="$PWD/vina"
```

`HELIX_VINA` takes priority over every other resolution path, so you can leave
whatever else is on `PATH` exactly where it is.
