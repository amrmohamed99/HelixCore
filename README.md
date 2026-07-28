<p align="center">
  <img src="frontend/resources/icon.png" alt="Helix Core" width="96" height="96" />
</p>

<h1 align="center">Helix Core</h1>

<p align="center">
  <strong>An open-source desktop platform for computational drug discovery.</strong><br/>
  Structure preparation, molecular docking, post-docking analysis, descriptor-based triage,
  molecular design, and results management — in one graphical application.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="License: MIT" />
  <img src="https://img.shields.io/badge/version-3.0.0-informational?style=flat-square" alt="Version 3.0.0" />
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey?style=flat-square" alt="Platforms: Windows and Linux" />
  <img src="https://img.shields.io/badge/python-3.12%2B-green?style=flat-square" alt="Python 3.12+" />
  <img src="https://img.shields.io/badge/node-20%2B-green?style=flat-square" alt="Node 20+" />
  <a href="https://doi.org/10.5281/zenodo.21646166"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.21646166.svg" alt="DOI: 10.5281/zenodo.21646166" /></a>
  <a href="https://doi.org/10.5281/zenodo.21647828"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.21647828.svg" alt="Evidence DOI: 10.5281/zenodo.21647828" /></a>
</p>

---

## Overview

Helix Core is a desktop application that wraps a curated stack of open scientific
tools — **RDKit**, **AutoDock Vina**, **Open Babel**, and **Meeko** — behind a single
graphical interface, so a structure-based drug-discovery workflow can be run without
switching between command-line tools and ad-hoc scripts. It pairs a **FastAPI** Python
backend with an **Electron + React** frontend, and exposes every step of the pipeline
(preparation, docking, analysis, design, reporting) as both a UI page and a documented
HTTP endpoint.

> **Scope of claims.** Helix Core is an integration and orchestration layer over
> established engines. It does not introduce a new scoring function or predictive model,
> and no claim of predictive accuracy or superiority over other software is made. See the
> accompanying publication materials for the controlled evaluations and their explicit
> limitations.

## Table of Contents

- [Features](#features)
- [Technology Stack](#technology-stack)
- [Getting Started](#getting-started)
- [Production Build](#production-build)
- [Project Structure](#project-structure)
- [Bundled Tools & Third-Party Licenses](#bundled-tools--third-party-licenses)
- [Contributing](#contributing)
- [Citation](#citation)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## Features

Helix Core organizes 20+ integrated modules into five workflow stages:

**Structure preparation**
- **PDB Fetcher** — retrieve and clean structures directly from the RCSB PDB
- **Receptor Preparation** — protonation, cleanup, and PDBQT conversion (Meeko)
- **Pocket Analyzer** — binding-site detection and grid-box definition
- **Format Converter** — interconvert molecular formats via Open Babel
- **Energy Minimization** — force-field minimization of ligand geometries

**Screening & docking**
- **Virtual Screening** — batch molecular docking with AutoDock Vina, real-time progress
- **Auto-Pipeline** — end-to-end prepare → dock → score → report orchestration
- **Similarity Search** — fingerprint (Tanimoto) similarity over compound libraries
- **Oracle AI Rescoring** — optional heuristic pKd-proxy re-ranking of docked poses

**Profiling & analysis**
- **ADMET Profiler** — descriptor-based drug-likeness and ADMET triage
- **Compound Filters** — Lipinski/Veber/PAINS and 16 curated structural alerts
- **Interaction Profiler** — protein–ligand contact classification
- **Chemical Clustering** — Tanimoto/Butina clustering of hit sets

**Molecular design**
- **Analog Generator** — BRICS, bioisostere, and chemical-space-walk analog generation
- **Fragment-Based Design** — fragmentation and growing
- **Scaffold Hopping** — scaffold replacement
- **Pharmacophore Modeling** — RDKit feature-based pharmacophore screening

**Workflow & reporting**
- **Dashboard**, **Results Explorer**, **Project Manager**, **Compound Watchlist**,
  **Compound Comparison**, and one-click **HTML/PDF report generation**.

The backend exposes **29 routers / 76 documented HTTP operations + 1 WebSocket endpoint**;
the frontend provides real-time progress control, item-level failure reporting, and
automated orchestration.

## Technology Stack

| Layer | Technologies |
|-------|--------------|
| **Frontend** | React 18, TypeScript 5.6, Electron 43, Vite 6, Mol\*, D3 |
| **Backend** | FastAPI, Uvicorn, Pydantic 2, SSE + WebSocket streaming |
| **Science** | RDKit, AutoDock Vina, Open Babel, Meeko, NumPy, SciPy, scikit-learn, ProDy, Gemmi |
| **Packaging** | PyInstaller backend; electron-builder Windows portable, Linux AppImage and deb |

## Getting Started

### Prerequisites

- **Python 3.12+** with `pip`
- **Node.js 20+** with `npm`
- **Windows 10/11 (64-bit)** — the portable application bundles the verified Windows
  tool set (see [Bundled Tools](#bundled-tools--third-party-licenses)).
- **Linux x86-64 with glibc 2.35+** — the AppImage and Debian package bundle the
  official AutoDock Vina 1.2.6 Linux binary. Open Babel 3.1.1 must be installed
  on the host; the `.deb` declares it as a package dependency.

> Ubuntu Electron execution is covered by CI, and the Linux packaging workflow runs
> the full end-to-end suite against the production AppImage payload. macOS remains
> best-effort and is not currently a release target.

### Install & run (development)

```bash
# Clone
git clone https://github.com/amrmohamed99/HelixCore.git
cd HelixCore

# Backend dependencies
pip install -r backend/requirements.txt

# Frontend dependencies
cd frontend && npm install && cd ..
```

Launch both processes together (Windows PowerShell):

```powershell
.\start.ps1
```

Or start them manually in two terminals:

```bash
# Terminal 1 — backend (http://127.0.0.1:8299)
PYTHONPATH=. python -m uvicorn backend.main:app --host 127.0.0.1 --port 8299 --reload
```

```bash
# Terminal 2 — frontend (Electron dev)
cd frontend && npm run dev
```

### API documentation

With the backend running:

- **Swagger UI** — http://127.0.0.1:8299/docs
- **ReDoc** — http://127.0.0.1:8299/redoc

### Tests

```bash
python -m pytest backend/tests/ -q
```

## Production Build

### Backend (PyInstaller)

Use CPython **3.12.1 or newer in the 3.12 series** for release packaging.
CPython 3.12.0 has a bytecode-compiler defect that can make a frozen SciPy
import fail even though the source environment works; `build_portable.ps1`
detects and rejects that interpreter.

```bash
pyinstaller backend.spec
# → dist/backend/backend.exe
```

### Frontend (electron-builder)

```bash
cd frontend
npm run package:win       # Windows portable executable
npm run package:linux     # Linux AppImage + deb (run on Linux)
```

### Full portable installer

```powershell
.\build_portable.ps1
# → frontend/release/HelixCore-3.0.0-portable.exe
```

### Linux AppImage and Debian package

Build on Ubuntu 22.04 or another glibc 2.35 baseline:

```bash
micromamba env create -f backend/environment.yml
micromamba activate helix
python -m pip install -r backend/requirements.lock.txt pyinstaller==6.20.0
python scripts/fetch_linux_tools.py
bash scripts/build_backend_linux.sh
cd frontend
npm ci
npm run package:linux
```

The outputs are `frontend/release/HelixCore-3.0.0-linux-x64.AppImage` and
`frontend/release/HelixCore-3.0.0-linux-x64.deb`. The official Vina binary and
license are fetched and hash-verified from `linux_tools_manifest.json` before
packaging. See [Installation](docs/installation.md#linux-appimage-and-deb) for
Open Babel and font requirements.

## Project Structure

```
HelixCore/
├── backend/                     ← FastAPI application
│   ├── main.py                  ← App entry, router registration
│   ├── config.py                ← Paths, ports, tool locations
│   ├── routers/                 ← 29 API routers (one per capability)
│   ├── services/                ← Persistence, report builder
│   ├── models/                  ← Pydantic schemas
│   ├── utils/                   ← PDB/PDBQT parsing, path & logging helpers
│   └── tests/                   ← pytest contract + scientific-claim suites
│
├── frontend/                    ← Electron + React + TypeScript
│   ├── electron/                ← Main process, preload bridge, splash
│   ├── src/
│   │   ├── App.tsx              ← Router + route definitions
│   │   ├── pages/               ← Feature pages
│   │   ├── components/          ← Layout + shared UI components
│   │   ├── hooks/ context/ lib/ ← State, API client, session
│   │   └── types/               ← Shared TypeScript types
│   ├── vite.config.ts
│   └── electron-builder.yml
│
├── tools/                       ← Bundled science binaries (Windows)
│   ├── vina.exe                 ← AutoDock Vina
│   └── OpenBabel/               ← Open Babel binaries + data
│
├── run_backend.py               ← Production backend entry point
├── backend.spec                 ← PyInstaller spec
├── build_portable.ps1           ← Full portable build pipeline
├── THIRD_PARTY_LICENSES.md
├── CITATION.cff
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
└── LICENSE                      ← MIT
```

## Bundled Tools & Third-Party Licenses

Helix Core is MIT-licensed. It **redistributes** two third-party scientific executables
under `tools/`, each invoked as a separate subprocess (not linked as a library):

| Tool | Version | License | Notes |
|------|---------|---------|-------|
| **AutoDock Vina** | v1.2.6 | Apache-2.0 | Molecular docking engine |
| **Open Babel** | 3.1.1 | **GPL-2.0** | Format conversion & charge assignment |

Because these binaries are unmodified and executed as standalone processes (mere
aggregation), the MIT license on Helix Core's own source is compatible with redistributing
them. When you distribute an installer that bundles these tools, you must comply with each
tool's license — in particular, Open Babel's GPL-2.0 requires that its license text
accompany the distribution and that its source remain available.

Full attribution for bundled binaries and key Python/JavaScript dependencies is listed in
**[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)**.

## Contributing

Bug reports, reproducible test cases, documentation fixes, and code contributions are
welcome. See **[CONTRIBUTING.md](CONTRIBUTING.md)** for the development setup, the checks a
pull request must pass, and the extra requirements for changes that alter numerical output.
Participation is covered by the **[Code of Conduct](CODE_OF_CONDUCT.md)**.

## Citation

If you use Helix Core in academic work, please cite it. Machine-readable metadata is in
**[CITATION.cff](CITATION.cff)**. The evaluated v3.0.0 source release is permanently
archived on Zenodo:

> Alhfnawy, A. M. (2026). *Helix Core: an open-source desktop platform for
> computational drug discovery* (Version 3.0.0) [Computer software]. Zenodo.
> https://doi.org/10.5281/zenodo.21646166

The content-addressed scientific evaluation evidence for v3.0.0—including raw benchmark
outputs, manifests, validators, provenance records, and checksums—is archived separately:

> Alhfnawy, A. M. (2026). *Helix Core v3.0.0 scientific evaluation evidence:
> redocking, scalability, workflow fidelity, and structural-alert concordance*
> (Version 1.0.0) [Data set]. Zenodo.
> https://doi.org/10.5281/zenodo.21647828

## License

Helix Core is released under the **MIT License** — see **[LICENSE](LICENSE)**.

Bundled third-party binaries retain their own licenses (see
[Bundled Tools](#bundled-tools--third-party-licenses)).

## Acknowledgments

Helix Core stands on the work of the **RDKit**, **AutoDock Vina**, **Open Babel**, and
**Meeko** developers, and on the **RCSB Protein Data Bank**, whose openly available tools
and data made this project possible.

<p align="center">
  <em>From structure to lead, all in one place.</em>
</p>
