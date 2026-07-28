# Installation

Helix Core is a desktop application: an **Electron + React** front end talking to a
**FastAPI** backend on `127.0.0.1:8299`, which in turn shells out to two external
scientific executables — **AutoDock Vina** and **Open Babel**.

Everything except those two executables installs from Python and npm package
managers. The engines are the part that differs per platform, and the part that
has to be got right: see [Which AutoDock Vina](#which-autodock-vina) before you
install anything on Linux or macOS.

| | Windows 10/11 (x64) | Linux (x86-64) | macOS | Docker |
|---|---|---|---|---|
| Backend + HTTP API | supported | supported | best-effort | supported |
| Electron GUI | supported | supported | best-effort | not included |
| Bundled engines | Vina + Open Babel | Vina in release packages | no — install yourself | Vina pinned in the image |

**Prerequisites on every platform:** Python 3.12, Node.js 20 or newer (22 is what
CI uses), and git.

---

## Which AutoDock Vina

This is the single most important paragraph in this document.

Install the **official upstream AutoDock Vina v1.2.6 release asset**:

<https://github.com/ccsb-scripps/AutoDock-Vina/releases/tag/v1.2.6>

**Do not run `conda install -c conda-forge vina`.** The conda-forge package is a
*modified* build. It self-reports

```
AutoDock Vina f458505-mod
```

— a patched 1.2.7 development commit carrying no release tag. Its docking scores
are **not comparable** with the numbers Helix Core's documentation and manuscript
report, which come from the official v1.2.6 assets on both platforms. Because it
identifies itself as modified, there is no upstream artifact anyone could download
to reproduce a run made with it.

Helix Core enforces this rather than trusting you to remember it. The startup check
logs an error and keeps running; anything that records a measurement refuses to
start. See [Engine identity guard](engine-guard.md).

Upstream builds the Windows and Linux assets from different commits, so the trailing
`git describe` suffix legitimately differs between platforms. The release tag is
what must agree:

| Platform | Expected banner |
|---|---|
| Windows (bundled `tools/vina.exe`) | `AutoDock Vina v1.2.6-56-gc28e340` |
| Linux (upstream `vina_1.2.6_linux_x86_64`) | `AutoDock Vina v1.2.6-27-gbe1689c` |

Open Babel is less fussy: conda-forge **3.1.1** on both platforms. Note that the
3.1.1 binaries self-report `Open Babel 3.1.0`. That is a known upstream packaging
quirk, not a wrong install, and the guard has an explicit exemption for exactly
that one pair.

---

## Windows

### 1. Clone and install Python dependencies

```bash
git clone https://github.com/amrmohamed99/HelixCore.git
cd HelixCore
python -m pip install -r backend/requirements.lock.txt
```

`backend/requirements.lock.txt` is the pinned runtime environment behind the
reported measurements. `backend/requirements.txt` is the looser development set;
use the lock unless you have a reason not to.

### 2. Fetch the Windows tools bundle — **required**

`tools/` is **not in git.** It is ~32 MB of prebuilt Windows executables, one of
which (Open Babel) is GPL-2.0, so it ships as a versioned GitHub Release asset
instead of living inside an MIT source tree. A fresh clone has no `tools/`
directory at all.

```bash
python scripts/fetch_tools.py
```

The script is stdlib-only — no `pip install` needed to bootstrap — and it hashes
every archive member against `tools_manifest.json` **before** unpacking anything.
A tampered, truncated, or unexpected member aborts the run with a non-zero exit and
nothing is written.

| Command | Effect |
|---|---|
| `python scripts/fetch_tools.py` | Download, verify, unpack. Idempotent: a no-op if `tools/` already matches. |
| `python scripts/fetch_tools.py --check` | Verify only, never download. Non-zero exit if invalid. This is the CI gate. |
| `python scripts/fetch_tools.py --force` | Re-fetch even if the current tree verifies. |
| `python scripts/fetch_tools.py --archive FILE.zip` | Install from an already-downloaded asset (offline / air-gapped). |

The bundle contains `vina.exe` (Apache-2.0) and `OpenBabel/` (GPL-2.0). The GPL
obligation travels inside the asset: `OpenBabel/License.txt` carries the full
licence text and `OpenBabel/SOURCE.md` the written source offer. `fetch_tools.py`
refuses a bundle that omits either. Do not commit the binaries back into git.

> The release asset is published from the repository's Releases page. If you are
> working from a clone made before the corresponding release exists, use
> `--archive` with a bundle obtained some other way, or install Vina and Open
> Babel yourself and point `HELIX_VINA` / `HELIX_OBABEL` at them.

### 3. Front end

```bash
cd frontend
npm install
npm run dev
```

`npm run dev` starts Vite and launches Electron (via `vite-plugin-electron`), and
Electron spawns the backend itself — you do not need a second terminal. If port
8299 is already serving a healthy backend, Electron attaches to it instead of
spawning another.

### 4. Verify

```bash
python -m pytest -q
tools/vina.exe --version          # expect: AutoDock Vina v1.2.6-56-gc28e340
tools/OpenBabel/obabel.exe -V     # expect: Open Babel 3.1.0 -- ...   (see the quirk above)
```

---

## Linux

The Electron GUI, the backend, and the full Playwright end-to-end suite all run on
Linux. `tools/` is Windows-only and is deliberately not used here. In development,
both engines resolve from `PATH`; the AppImage and Debian release packages instead
bundle the checksum-verified Vina binary while still resolving Open Babel from
`PATH`.

### 1. Python environment

The declared environment is `backend/environment.yml` (conda-forge). Micromamba or
mamba is the fastest route:

```bash
git clone https://github.com/amrmohamed99/HelixCore.git
cd HelixCore
micromamba env create -f backend/environment.yml
micromamba activate helix
python -m pip install -r backend/requirements.lock.txt
```

The micromamba layer installs Open Babel 3.1.1 build 9; the pip lock then installs
RDKit 2025.03.2 and the exact Python stack used by the manuscript. This split is
intentional: SciPy 1.15.3 is published on PyPI but not on conda-forge.
Neither command installs Vina — see the next step.

If you would rather use a plain virtualenv, `pip install -r
backend/requirements.lock.txt` gets the Python side, but you must then install Open
Babel through your distribution or conda-forge separately; it is not a pip package.

### 2. AutoDock Vina — the official release asset

```bash
mkdir -p ~/.local/bin
curl -fsSL -o ~/.local/bin/vina \
  https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/v1.2.6/vina_1.2.6_linux_x86_64
echo "06dfe473434e666723436f6bc9379d6ea7ba75a19203feb00c1196ec3a1593e0  $HOME/.local/bin/vina" | sha256sum -c -
chmod +x ~/.local/bin/vina
export PATH="$HOME/.local/bin:$PATH"
vina --version        # expect: AutoDock Vina v1.2.6-27-gbe1689c
```

The `sha256sum -c -` line is not decoration. It is the same digest the Dockerfile
and the CI workflow verify, and it is what makes "the official v1.2.6 asset" a
checkable claim rather than an assertion.

If you must keep a different Vina on `PATH` for other work, leave it there and point
Helix Core at this one:

```bash
export HELIX_VINA="$HOME/.local/bin/vina"
```

### 3. Open Babel

`micromamba env create` above already installed `openbabel=3.1.1` build 9. If you are not
using the conda environment:

```bash
micromamba install -c conda-forge openbabel=3.1.1
# or your distribution's package, if it is 3.1.x
obabel -V     # expect: Open Babel 3.1.0 -- ...
```

Do **not** set `BABEL_DATADIR` by hand. A `PATH`-resolved Open Babel finds its own
data relative to its install prefix; pointing it at a different build's data
directory silently mixes incompatible element and atom-typing tables. Helix Core
sets the variable only when the *resolved* binary is the bundled Windows one.

### 4. Front end

```bash
cd frontend
npm ci
npm run dev
```

### 5. Verify

```bash
python -m pytest -q
```

### Colour-emoji font — needed for a readable sidebar

Helix Core's navigation and status icons are **emoji characters, not an icon
font**. On a Linux host with no colour-emoji font installed, every one of them
renders as a tofu box (▯) and the sidebar becomes unreadable. Minimal server and
container images routinely ship without one.

```bash
sudo apt-get install -y fonts-noto-color-emoji     # Debian / Ubuntu
```

The `.deb` package declares `fonts-noto-color-emoji` as a dependency, so installing
Helix Core from the deb pulls it in automatically.

**The AppImage cannot do this.** AppImage has no dependency mechanism at all — it
is a single self-contained file with no package metadata and no way to require
anything of the host. If you run the AppImage, installing a colour-emoji font is
your responsibility. This is the one thing about the AppImage build that a new user
reliably trips over.

---

## macOS

**Best-effort and not covered by CI.** The backend and the front end are
platform-independent Python and Node, and `backend/config.py` resolves engines from
`PATH` on any non-Windows platform, so the pieces are all present. Nobody has
validated the full pipeline on macOS, no packaged artifact is produced for it, and
the test matrix does not include it.

The install follows the Linux instructions, except for Vina: take the macOS asset
matching your architecture from the same
[v1.2.6 release page](https://github.com/ccsb-scripps/AutoDock-Vina/releases/tag/v1.2.6),
verify its checksum against the digest published there, and put it on `PATH` or
point `HELIX_VINA` at it. `backend/config.py` also recognises the filename
`vina_1.2.6_mac_x86_64` inside a tools directory.

The same rule applies as everywhere else: not the conda-forge package.

---

## Docker — backend only

The image gives a reviewer a one-command reproduction of the backend and its test
suite. The Electron GUI is not in it.

```bash
docker build -t helixcore-backend .
docker run --rm helixcore-backend pytest -q            # run the suite
docker run --rm -p 8299:8299 helixcore-backend         # serve the API
```

Then browse <http://127.0.0.1:8299/docs>.

What the image pins, and why it is worth knowing:

- The base image is pinned by **digest**, not by tag, because a republished tag
  would silently change the toolchain under an already-published result.
- Vina is fetched from the official v1.2.6 URL and verified by SHA-256 during the
  build. `vina --version` runs inside the build, so a bad asset fails the build
  rather than the science.
- Open Babel comes from conda-forge at the same build number as the Windows bundle,
  so PDBQT output and charge assignment match across platforms.
- No `HELIX_TOOLS_DIR` is set: both engines resolve from `PATH`.

To keep results, mount a workspace:

```bash
docker run --rm -p 8299:8299 -v "$PWD/workspace:/app/workspace" helixcore-backend
```

---

## Running the backend without Electron

Any of these work; they differ only in reload behaviour and crash logging.

```bash
# Development, auto-reload
PYTHONPATH=. python -m uvicorn backend.main:app --host 127.0.0.1 --port 8299 --reload

# Production entry point (sets up crash logging, honours HELIX_HOST / HELIX_PORT)
python run_backend.py
```

Health check: `curl http://127.0.0.1:8299/api/health` → `{"status":"online","version":"3.0.0"}`

---

## Configuration reference

Every setting is an environment variable. There is no config file to edit.

### Paths and ports

| Variable | Default | Meaning |
|---|---|---|
| `HELIX_PORT` | `8299` | Backend port. |
| `HELIX_HOST` | `127.0.0.1` | Bind address. Read by `run_backend.py`, not by `uvicorn` invoked directly. |
| `HELIX_WORKSPACE_DIR` | `<repo>/workspace` | Where prepared receptors, results, and reports are written. Electron overrides this with a per-user directory (see below). |
| `HELIX_TOOLS_DIR` | `<repo>/tools` | Where bundled engines are looked for. |
| `HELIX_VINA` | — | Absolute path to a specific Vina executable. Highest priority. |
| `HELIX_OBABEL` | — | Absolute path to a specific Open Babel executable. Highest priority. |
| `HELIX_CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | Comma-separated allowed origins. |

Binary resolution order, for both engines: `HELIX_VINA` / `HELIX_OBABEL` →
`HELIX_TOOLS_DIR` (bundled) → the frozen executable's own directory → `PATH`. A
`HELIX_*` override that names a file which does not exist logs a warning and falls
through to the next candidate rather than failing hard.

### Engine identity

| Variable | Default | Meaning |
|---|---|---|
| `HELIX_EXPECTED_VINA` | `v1.2.6` | Declared Vina release. Empty, `any`, `*`, or `none` withdraws the expectation. |
| `HELIX_EXPECTED_OBABEL` | `3.1.1` | Declared Open Babel release, same syntax. |
| `HELIX_ENGINE_CHECK` | on | `0`/`false`/`no`/`off`/`skip`/`disabled` silences the **startup** check only. It has no effect on measurement runs. |

Full semantics in [Engine identity guard](engine-guard.md).

### Where the GUI puts your workspace

When you launch through Electron, the front end chooses the workspace and passes it
to the backend as `HELIX_WORKSPACE_DIR`, overriding the repo-relative default:

| Situation | Workspace root |
|---|---|
| A path saved earlier via the in-app picker | that path (`workspace.json` in the app-data directory) |
| Portable Windows `.exe` | `HelixCoreWorkspace/` beside the executable |
| Windows, installed or dev | `%APPDATA%\HelixCore\workspace` |
| Linux | `$XDG_DATA_HOME/HelixCore/workspace`, else `~/.local/share/HelixCore/workspace` |
| macOS | `~/Library/Application Support/HelixCore/workspace` |

If you follow the [tutorial](tutorial.md) through the API rather than the GUI, the
workspace is whatever `HELIX_WORKSPACE_DIR` says, defaulting to `workspace/` inside
the checkout.

---

## Building distributable artifacts

### Windows portable executable

```powershell
python scripts/fetch_tools.py     # MUST run first — see the warning below
pyinstaller backend.spec          # → dist/backend/backend.exe
cd frontend; npm run package      # → frontend/release/
```

> **A missing `tools/` does not fail the packaging step.** electron-builder logs
> `file source doesn't exist` at *warn* level and carries on, producing an installer
> with no docking engine and no format converter, explained by one line of build
> output. Run the fetch script first and treat that warning as fatal.

`.\build_portable.ps1` runs the whole chain and produces
`frontend/release/HelixCore-3.0.0-portable.exe`.

The Windows release backend must be frozen with CPython 3.12.1–3.12.x.
CPython 3.12.0 has a bytecode-compiler defect that breaks frozen SciPy imports,
so the build script rejects it before spending time on PyInstaller. Use
`-PythonExe C:\path\to\python.exe` to select a release interpreter explicitly.

### Linux AppImage and deb

```bash
python -m pip install -r backend/requirements.lock.txt pyinstaller==6.20.0
python scripts/fetch_linux_tools.py    # verified Vina + Apache-2.0 license
bash scripts/build_backend_linux.sh    # PyInstaller → dist/backend/backend
cd frontend
npm ci
npm run package:linux
```

This produces:

- `frontend/release/HelixCore-3.0.0-linux-x64.AppImage`
- `frontend/release/HelixCore-3.0.0-linux-x64.deb`

Build release artifacts on Ubuntu 22.04 (glibc 2.35). PyInstaller does not bundle
glibc, so building on a newer system raises the minimum runtime version. PyInstaller
is deliberately absent from `backend/environment.yml`, because it is a packaging
tool rather than part of the measured scientific environment.

Both packages bundle the official AutoDock Vina 1.2.6 Linux release binary recorded
in `linux_tools_manifest.json`. Open Babel remains a host dependency. Installing the
`.deb` pulls the distribution's `openbabel` package automatically:

```bash
sudo apt install ./frontend/release/HelixCore-3.0.0-linux-x64.deb
```

For the AppImage, install Open Babel and the colour-emoji font first:

```bash
sudo apt-get install -y openbabel fonts-noto-color-emoji
chmod +x frontend/release/HelixCore-3.0.0-linux-x64.AppImage
./frontend/release/HelixCore-3.0.0-linux-x64.AppImage
```

---

## Next steps

- [Worked tutorial](tutorial.md) — 3PTB from fetch to report, with real outputs.
- [HTTP API reference](api/README.md) — all 70 operations, generated from the schema.
- [Engine identity guard](engine-guard.md).
- [Troubleshooting](troubleshooting.md).
