#!/usr/bin/env bash
#
# Helix Core — build the Linux backend binary that electron-builder packages.
#
# Runs PyInstaller against backend.spec inside the conda/micromamba environment
# declared by backend/environment.yml and leaves the result at
# dist/backend/backend — the path frontend/electron-builder.yml maps into
# resources/backend for the AppImage and deb targets, and the one
# frontend/electron/main.ts launches when process.platform is not win32.
#
# Notes
#   * PyInstaller does not bundle docking engines. The later electron-builder
#     step copies the official Vina 1.2.6 Linux asset from `linux-tools/`,
#     populated and hash-verified by scripts/fetch_linux_tools.py. Open Babel
#     remains a host dependency resolved from PATH. Do NOT use
#     `conda install -c conda-forge vina`; that is a modified build reporting
#     `f458505-mod`.
#   * PyInstaller does not bundle glibc, so a binary built here runs only on a
#     host whose glibc is at least as new as this machine's. Build on the
#     oldest supported baseline, or in the container from Dockerfile, before
#     shipping an AppImage or deb.
#   * PyInstaller is deliberately absent from backend/environment.yml: it is a
#     packaging tool, not a runtime dependency, and adding it would place it
#     inside the hermetic environment the measurements come from. Install it
#     alongside, with --install-deps.

set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: bash scripts/build_backend_linux.sh [options]

  -n, --env NAME     Environment name or prefix path (default: $HELIX_ENV, else "helix")
      --install-deps Install PyInstaller into the environment if it is missing
      --no-smoke     Skip the start-and-probe check of the built binary
      --strip        Strip symbols from the bundle (smaller; occasionally
                     corrupts conda-built shared objects, hence opt-in)
      --clean        Also clear the PyInstaller cache
  -h, --help         Show this help

Environment:
  HELIX_ENV          Same as --env
  HELIX_PYTHON       Absolute path to a python, bypassing environment resolution
  HELIX_SMOKE_PORT   Port for the smoke test (default 8399)
USAGE
}

# --------------------------------------------------------------------------- #
#  Locations and defaults                                                      #
# --------------------------------------------------------------------------- #

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
SPEC_FILE="$REPO_ROOT/backend.spec"
DIST_DIR="$REPO_ROOT/dist"
WORK_DIR="$REPO_ROOT/build"
OUT_DIR="$DIST_DIR/backend"
OUT_BIN="$OUT_DIR/backend"

ENV_NAME="${HELIX_ENV:-helix}"
SMOKE_PORT="${HELIX_SMOKE_PORT:-8399}"
SMOKE=1
INSTALL_DEPS=0
CLEAN_CACHE=0

if [ -t 1 ]; then
    C_RESET=$'\033[0m'; C_INFO=$'\033[36m'; C_OK=$'\033[32m'
    C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_DIM=$'\033[90m'
else
    C_RESET=''; C_INFO=''; C_OK=''; C_WARN=''; C_ERR=''; C_DIM=''
fi

step() { printf '\n%s=== %s ===%s\n' "$C_INFO" "$*" "$C_RESET"; }
info() { printf '%s  %s%s\n' "$C_DIM" "$*" "$C_RESET"; }
ok()   { printf '%s  %s%s\n' "$C_OK" "$*" "$C_RESET"; }
warn() { printf '%s  WARNING: %s%s\n' "$C_WARN" "$*" "$C_RESET" >&2; }
die()  { printf '\n%sERROR: %s%s\n' "$C_ERR" "$*" "$C_RESET" >&2; exit 1; }

# --------------------------------------------------------------------------- #
#  Arguments                                                                   #
# --------------------------------------------------------------------------- #

while [ $# -gt 0 ]; do
    case "$1" in
        -n|--env)       ENV_NAME="${2:-}"; [ -n "$ENV_NAME" ] || die "--env needs a value"; shift 2 ;;
        --install-deps) INSTALL_DEPS=1; shift ;;
        --no-smoke)     SMOKE=0; shift ;;
        --strip)        export HELIX_PYI_STRIP=1; shift ;;
        --clean)        CLEAN_CACHE=1; shift ;;
        -h|--help)      usage; exit 0 ;;
        *)              die "Unknown option: $1 (try --help)" ;;
    esac
done

[ "$(uname -s)" = "Linux" ] || die "This builds the Linux backend. On Windows use build_portable.ps1."
[ -f "$SPEC_FILE" ] || die "backend.spec not found at $SPEC_FILE"
[ -f "$REPO_ROOT/run_backend.py" ] || die "run_backend.py not found in $REPO_ROOT"

# --------------------------------------------------------------------------- #
#  1. Resolve the interpreter                                                  #
# --------------------------------------------------------------------------- #

step "1/5  Resolving the build environment"

# Locate an environment prefix without going through the manager. `micromamba
# run -n NAME` only works when MAMBA_ROOT_PREFIX is exported, which the
# installer does from the interactive shell profile — so it is set under
# `bash -l` and unset under `bash -c`, and the failure mode is a confusing
# "prefix does not exist" for a prefix nobody asked for.
find_env_prefix() {
    local name="$1" root
    if [ -x "$name/bin/python" ]; then
        (cd -- "$name" && pwd)
        return 0
    fi
    for root in "${MAMBA_ROOT_PREFIX:-}" "${CONDA_ROOT:-}" "${HOME}/micromamba" \
                "${HOME}/.local/share/mamba" "${HOME}/miniforge3" "${HOME}/mambaforge" \
                "${HOME}/miniconda3" "${HOME}/anaconda3" /opt/conda /opt/micromamba; do
        [ -n "$root" ] || continue
        if [ -x "$root/envs/$name/bin/python" ]; then
            printf '%s\n' "$root/envs/$name"
            return 0
        fi
    done
    return 1
}

PY_CMD=()

if [ -n "${HELIX_PYTHON:-}" ]; then
    [ -x "$HELIX_PYTHON" ] || die "HELIX_PYTHON=$HELIX_PYTHON is not executable"
    PY_CMD=("$HELIX_PYTHON")
    info "Using HELIX_PYTHON"
elif [ -n "${CONDA_PREFIX:-}" ] && [ "$(basename "$CONDA_PREFIX")" = "$ENV_NAME" ] && [ -x "$CONDA_PREFIX/bin/python" ]; then
    PY_CMD=("$CONDA_PREFIX/bin/python")
    info "Environment '$ENV_NAME' is already active"
elif ENV_PREFIX="$(find_env_prefix "$ENV_NAME")"; then
    PY_CMD=("$ENV_PREFIX/bin/python")
    info "Found environment at $ENV_PREFIX"
else
    MANAGER=""
    for candidate in micromamba mamba conda; do
        if command -v "$candidate" >/dev/null 2>&1; then MANAGER="$candidate"; break; fi
    done
    # micromamba's installer wires itself into interactive shells only, so the
    # conventional location is worth probing before giving up.
    if [ -z "$MANAGER" ] && [ -x "$HOME/.local/bin/micromamba" ]; then
        MANAGER="$HOME/.local/bin/micromamba"
    fi
    [ -n "$MANAGER" ] || die "No environment named '$ENV_NAME' in any known root, and no micromamba/mamba/conda found.
Create it with:  micromamba env create -f backend/environment.yml
Or point at an interpreter directly:  HELIX_PYTHON=/path/to/python bash scripts/build_backend_linux.sh"

    info "Falling back to '$MANAGER run'"
    PY_CMD=("$MANAGER" run -n "$ENV_NAME" python)
    "${PY_CMD[@]}" -c 'pass' >/dev/null 2>&1 || die "'$MANAGER run -n $ENV_NAME python' failed.
Create the environment with:  $MANAGER env create -f backend/environment.yml"
fi

py() { "${PY_CMD[@]}" "$@"; }

PREFIX="$(py -c 'import sys; print(sys.prefix)')"
info "Interpreter: $(py -c 'import sys; print(sys.executable)')"
info "Prefix:      $PREFIX"
info "Python:      $(py -c 'import sys; print(sys.version.split()[0])')"

# Mirror what `micromamba activate` would do. Without this the engine probe
# below reports the engines missing whenever the environment was located rather
# than activated, and PyInstaller's helper tools come from outside the env.
export PATH="$PREFIX/bin:$PATH"

# PyInstaller follows ELF NEEDED entries to pull in the conda shared libraries
# RDKit, numpy and scipy link against. Most conda packages carry an RPATH that
# resolves them already, but one built without it would silently drop its
# dependencies from the bundle, so make the environment's lib dir discoverable.
export LD_LIBRARY_PATH="$PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

# --------------------------------------------------------------------------- #
#  2. Check the build dependencies                                             #
# --------------------------------------------------------------------------- #

step "2/5  Checking build dependencies"

MISSING="$(py - <<'PY'
import importlib

required = [
    ("rdkit", "rdkit"), ("numpy", "numpy"), ("scipy", "scipy"),
    ("sklearn", "scikit-learn"), ("joblib", "joblib"),
    ("fastapi", "fastapi"), ("uvicorn", "uvicorn"), ("pydantic", "pydantic"),
    ("meeko", "meeko"), ("prody", "prody"), ("gemmi", "gemmi"),
    ("psutil", "psutil"), ("requests", "requests"), ("httpx", "httpx"),
]
missing = []
for module, dist in required:
    try:
        importlib.import_module(module)
    except Exception:
        missing.append(dist)
print(" ".join(missing))
PY
)"
[ -z "$MISSING" ] || die "Environment '$ENV_NAME' is missing: $MISSING
Recreate it with:  micromamba env create -f backend/environment.yml"
ok "Runtime dependencies present"

if ! py -c 'import PyInstaller' >/dev/null 2>&1; then
    if [ "$INSTALL_DEPS" -eq 1 ]; then
        warn "PyInstaller not found — installing it into '$ENV_NAME'"
        py -m pip install --disable-pip-version-check 'pyinstaller>=6.6'
    else
        die "PyInstaller is not installed in '$ENV_NAME'.
Re-run with --install-deps, or install it yourself:
  micromamba run -n $ENV_NAME python -m pip install 'pyinstaller>=6.6'
It is intentionally absent from backend/environment.yml — see this script's header."
    fi
fi
ok "PyInstaller $(py -c 'import PyInstaller; print(PyInstaller.__version__)')"

# The wheel and conda RDKit layouts differ in where Data/ and Contrib/ live,
# which is the one thing backend.spec has to detect. Report what it will see.
py - <<'PY'
import os
import rdkit
from rdkit import RDPaths

share = os.path.realpath(getattr(RDPaths, "_share", ""))
pkg = os.path.realpath(os.path.dirname(rdkit.__file__))
wheel = share == pkg or share.startswith(pkg + os.sep)
print("  RDKit %s — %s layout, share=%s" % (rdkit.__version__, "wheel" if wheel else "conda", share))
for sub in ("Data", "Contrib"):
    path = os.path.join(share, sub)
    if not os.path.isdir(path):
        raise SystemExit("ERROR: RDKit %s tree missing at %s" % (sub, path))
PY

for engine in vina obabel; do
    if command -v "$engine" >/dev/null 2>&1; then
        info "$engine: $(command -v "$engine")"
    else
        warn "$engine is not on PATH. The binary will build and start, but docking/conversion will fail at run time."
    fi
done

# --------------------------------------------------------------------------- #
#  3. Clean previous output                                                    #
# --------------------------------------------------------------------------- #

step "3/5  Cleaning previous output"
rm -rf "$OUT_DIR" "$WORK_DIR/backend"
info "Removed dist/backend and build/backend"

# --------------------------------------------------------------------------- #
#  4. Build                                                                    #
# --------------------------------------------------------------------------- #

step "4/5  Running PyInstaller"

PYI_ARGS=(-m PyInstaller "$SPEC_FILE" --noconfirm
          --distpath "$DIST_DIR" --workpath "$WORK_DIR" --log-level INFO)
[ "$CLEAN_CACHE" -eq 1 ] && PYI_ARGS+=(--clean)

cd "$REPO_ROOT"
START_TS=$(date +%s)
py "${PYI_ARGS[@]}"
BUILD_SECONDS=$(( $(date +%s) - START_TS ))

[ -f "$OUT_BIN" ] || die "PyInstaller reported success but $OUT_BIN is missing"
[ -x "$OUT_BIN" ] || chmod +x "$OUT_BIN"

ok "backend: $(du -h "$OUT_BIN" | cut -f1)   dist/backend/: $(du -sh "$OUT_DIR" | cut -f1)   (${BUILD_SECONDS}s)"

# Verify the RDKit resource fixup landed. Without Contrib/SA_Score the ADMET
# route falls back to a heuristic score without raising, so an absent tree would
# otherwise never surface as an error — only as different numbers.
RDKIT_SHARE="$OUT_DIR/_internal/rdkit_share"
if py -c 'import os, rdkit
from rdkit import RDPaths
share = os.path.realpath(getattr(RDPaths, "_share", ""))
pkg = os.path.realpath(os.path.dirname(rdkit.__file__))
raise SystemExit(0 if share == pkg or share.startswith(pkg + os.sep) else 1)'; then
    info "Wheel RDKit layout — Data/ and Contrib/ collected inside _internal/rdkit/"
else
    [ -f "$RDKIT_SHARE/Data/BaseFeatures.fdef" ] \
        || die "conda RDKit layout but _internal/rdkit_share/Data/BaseFeatures.fdef is missing — pharmacophore extraction would fail in the packaged app"
    [ -f "$RDKIT_SHARE/Contrib/SA_Score/sascorer.py" ] \
        || die "conda RDKit layout but _internal/rdkit_share/Contrib/SA_Score/sascorer.py is missing — ADMET would silently report heuristic SA scores"
    ok "RDKit Data/ and Contrib/SA_Score bundled at _internal/rdkit_share/"
fi

# Transitive dependencies that only an `excludes` entry can remove, and whose
# absence degrades a feature instead of crashing the app. Each of these was
# missing from a real build of this spec: `scipy.optimize`/`scipy.stats` made
# `from sklearn.ensemble import RandomForestRegressor` raise, so
# backend/routers/oracle.py quietly stopped honouring a user-supplied model, and
# `PIL` made reportlab unimportable, so PDF reports 500'd. The bundle is cheap
# to inspect; the failures are not cheap to notice.
for required in scipy/optimize scipy/stats scipy/fft scipy/ndimage \
                scipy/integrate scipy/interpolate scipy/cluster PIL; do
    [ -d "$OUT_DIR/_internal/$required" ] \
        || die "_internal/$required is missing from the bundle — check the excludes list in backend.spec.
scipy.optimize/stats/fft/ndimage/integrate/interpolate are import-time dependencies of
sklearn.ensemble (and, with cluster, of prody); PIL is one of reportlab's."
done
ok "sklearn, prody and reportlab dependency trees are complete"

# The bundled backend source is data, so nothing else checks it. Test files and
# __pycache__ leaking in is a size and reproducibility problem, not a runtime
# one: the .pyc are written by this build's own analysis pass, so their presence
# depends on whether the tree had been imported before.
if [ -d "$OUT_DIR/_internal/backend/tests" ] \
   || [ -n "$(find "$OUT_DIR/_internal/backend" -name '__pycache__' -print -quit 2>/dev/null)" ]; then
    die "tests/ or __pycache__ leaked into _internal/backend — the source filter in backend.spec regressed"
fi
ok "Bundled backend source is clean (no tests/, no __pycache__)"

# --------------------------------------------------------------------------- #
#  5. Smoke test                                                               #
# --------------------------------------------------------------------------- #

if [ "$SMOKE" -eq 0 ]; then
    step "5/5  Smoke test skipped (--no-smoke)"
else
    step "5/5  Smoke test"

    LOG="$(mktemp -t helix-smoke-log-XXXXXX)"
    SMOKE_CWD="$(mktemp -d -t helix-smoke-XXXXXX)"
    SMOKE_PID=""

    cleanup() {
        [ -n "$SMOKE_PID" ] && kill "$SMOKE_PID" 2>/dev/null || true
        [ -n "$SMOKE_PID" ] && wait "$SMOKE_PID" 2>/dev/null || true
        rm -rf "$SMOKE_CWD"
    }
    trap cleanup EXIT

    # Run from a scratch directory so the frozen binary cannot fall back to the
    # source tree and hide a packaging gap.
    #
    # HELIX_WORKSPACE_DIR is not optional here. backend/config.py derives the
    # workspace from PROJECT_ROOT, which is sys._MEIPASS when frozen — i.e.
    # dist/backend/_internal — so an unredirected smoke test creates
    # _internal/workspace/helix_core.db inside the very tree electron-builder is
    # about to copy into resources/backend, and every user gets this machine's
    # database. Electron sets the same variable in production.
    ( cd "$SMOKE_CWD" && exec env HELIX_HOST=127.0.0.1 HELIX_PORT="$SMOKE_PORT" \
        HELIX_WORKSPACE_DIR="$SMOKE_CWD/workspace" "$OUT_BIN" ) >"$LOG" 2>&1 &
    SMOKE_PID=$!

    get() {  # get URL [json-body]
        if [ $# -ge 2 ]; then
            curl -fsS --max-time 30 -X POST "$1" -H 'Content-Type: application/json' -d "$2" 2>/dev/null || true
        else
            curl -fsS --max-time 5 "$1" 2>/dev/null || true
        fi
    }
    command -v curl >/dev/null 2>&1 || die "curl is required for the smoke test (or pass --no-smoke)"

    HEALTH=""
    for _ in $(seq 1 60); do
        kill -0 "$SMOKE_PID" 2>/dev/null || break
        HEALTH="$(get "http://127.0.0.1:$SMOKE_PORT/api/health")"
        [ -n "$HEALTH" ] && break
        sleep 1
    done

    if [ -z "$HEALTH" ]; then
        printf '%s--- backend output ---%s\n' "$C_DIM" "$C_RESET" >&2
        tail -n 40 "$LOG" >&2 || true
        die "Backend did not answer /api/health on port $SMOKE_PORT (log kept at $LOG)"
    fi
    ok "/api/health -> $HEALTH"

    # Exercises RDConfig.RDDataDir/BaseFeatures.fdef, i.e. the RDBASE runtime
    # hook, through a real request rather than trusting the build log.
    PHARM="$(get "http://127.0.0.1:$SMOKE_PORT/api/pharmacophore/generate" '{"smiles":"CC(=O)Oc1ccccc1C(=O)O"}')"
    if printf '%s' "$PHARM" | grep -q '"feature_counts"'; then
        ok "/api/pharmacophore/generate -> $(printf '%s' "$PHARM" | tr -d '\n' | sed 's/.*\("feature_counts":{[^}]*}\).*/\1/')"
    else
        printf '%s--- backend output ---%s\n' "$C_DIM" "$C_RESET" >&2
        tail -n 40 "$LOG" >&2 || true
        die "Pharmacophore request failed — RDKit feature definitions are not resolving inside the bundle"
    fi

    # reportlab imports PIL at import time. When PIL is not in the bundle the
    # failure surfaces only here, as a 500 from a route whose dependency the
    # environment does contain, so probe the PDF path rather than trusting that
    # reportlab was collected.
    REPORT="$(get "http://127.0.0.1:$SMOKE_PORT/api/report/generate" \
        "{\"format\":\"pdf\",\"title\":\"smoke\",\"custom_text\":\"smoke\",\"output_dir\":\"$SMOKE_CWD/reports\"}")"
    if printf '%s' "$REPORT" | grep -q '\.pdf'; then
        ok "/api/report/generate (pdf) -> $(ls -1 "$SMOKE_CWD/reports" 2>/dev/null | head -1)"
    else
        printf '%s--- backend output ---%s\n' "$C_DIM" "$C_RESET" >&2
        tail -n 40 "$LOG" >&2 || true
        die "PDF report generation failed (response: ${REPORT:-<none>}) — reportlab is not importable inside the bundle"
    fi

    cleanup
    trap - EXIT
    rm -f "$LOG"

    # The smoke test must not have written anything into the tree that is about
    # to be packaged.
    if [ -d "$OUT_DIR/_internal/workspace" ]; then
        die "the smoke test created $OUT_DIR/_internal/workspace — it would ship inside resources/backend"
    fi
fi

step "Done"
printf '  Binary:   %s\n' "$OUT_BIN"
printf '  Package:  cd frontend && npx electron-builder --linux\n'
printf '  Caveat:   the AppImage and deb inherit this machine glibc floor (%s)\n' \
    "$(ldd --version 2>/dev/null | head -1 | awk '{print $NF}')"
