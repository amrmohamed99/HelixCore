# Third-Party Licenses

Helix Core is licensed under the [MIT License](LICENSE). It depends on, and in two cases
**redistributes**, third-party software that retains its own license. This file lists those
components and their licenses.

Nothing here overrides the upstream license texts; where a component ships its own license
file (for example `tools/OpenBabel/License.txt`, which lives inside the tool bundle described
in §1, not in this repository), that file is authoritative.

---

## 1. Bundled binaries (Windows tool bundle, `tools/`)

Two scientific engines are redistributed as prebuilt Windows executables. Helix Core invokes
them as **separate subprocesses**; it does not statically or dynamically link against either.

| Component | Version | License | Upstream |
|-----------|---------|---------|----------|
| AutoDock Vina | v1.2.6 (`v1.2.6-56-gc28e340`) | Apache-2.0 | https://github.com/ccsb-scripps/AutoDock-Vina |
| Open Babel | 3.1.1 | **GPL-2.0-only** | https://github.com/openbabel/openbabel |

### 1.1 How they are distributed

These binaries are **not in this git repository**. Keeping 32 MB of GPL-2.0 executables inside
an MIT-licensed source tree serves nobody: no test, CI job, container image, or PyInstaller
step reads `tools/` (the Linux image fetches Vina from upstream by SHA-256 and takes Open
Babel from conda-forge, and `backend/config.py` falls back to `PATH`). The directory is
consumed only by Windows runtime resolution and by Windows packaging.

They ship instead as a single GitHub **Release asset**, restored on demand:

```bash
python scripts/fetch_tools.py        # download, verify, unpack into tools/
python scripts/fetch_tools.py --check  # verify an existing tools/ and exit non-zero if wrong
```

`tools_manifest.json` records the SHA-256 and byte count of every file the bundle must
contain. `scripts/fetch_tools.py` hashes each archive member *before* unpacking, rejects any
file the manifest does not describe, and refuses to write anything if a single digest
disagrees — so the licensing artefacts below cannot be silently dropped or replaced by a
mirror.

The Linux artifacts (AppImage, deb) bundle **neither** engine — both are resolved from `PATH`
— so no redistribution obligation for Vina or Open Babel attaches to them. The container
image built from `Dockerfile` is different: it *does* contain both engines (Vina fetched from
the upstream release by SHA-256, Open Babel installed from conda-forge). Publishing that
image to a registry is a redistribution, and §1.2 applies to whoever publishes it.

### 1.2 GPL-2.0 compliance (Open Babel)

Open Babel is licensed under the GNU General Public License, version 2. Helix Core invokes
the unmodified `obabel` executable as an external process; this is *mere aggregation* under
the GPL and does not place Helix Core's own MIT-licensed source under the GPL.

**The attribution travels inside the bundle, not in this repository.** Two files sit next to
the binaries, are listed in `tools_manifest.json`, and are copied verbatim into every Windows
installer by the `win.extraResources` step in `frontend/electron-builder.yml`:

| File | Contents |
|---|---|
| `tools/OpenBabel/License.txt` | The full GPL-2.0 text (GNU General Public License, Version 2, June 1991) |
| `tools/OpenBabel/SOURCE.md` | Provenance and the written source offer |
| `tools/OpenBabel/THIRD_PARTY_NOTICES.md` | Exact conda-forge runtime-closure inventory and license map |
| `tools/OpenBabel/licenses/` | Upstream license texts for the bundled runtime DLL closure |

**Written source offer (reproduced here so it is available without the asset).** The bundled
binaries come from the conda-forge package `openbabel-3.1.1-py311h6f56430_9` (win-64),
SHA-256 `7b53f6014439f8d15b2f747373263417a36f638721b2f23a9c7f0f62a7269af9`, at
https://conda.anaconda.org/conda-forge/win-64/openbabel-3.1.1-py311h6f56430_9.conda. The
complete corresponding source code is the upstream release
https://github.com/openbabel/openbabel/releases/tag/openbabel-3-1-1 together with the build
recipe at https://github.com/conda-forge/openbabel-feedstock. The binaries are unmodified
except that the ICU DLLs from the upstream package were deleted; no source change was made.

If you redistribute a build that bundles these binaries, you must keep `License.txt` and
`SOURCE.md` alongside them and preserve the source reference, as required by GPL-2.0 §3. The
default Windows packaging does this automatically; a custom packaging step must not strip
them.

The Open Babel directory also contains DLLs from its exact conda-forge runtime closure
(Cairo, GLib, XML, compression, font, Tcl/Tk, and Microsoft runtimes). Their versions,
build identifiers, declared licenses, and corresponding license files are recorded in
`OpenBabel/THIRD_PARTY_NOTICES.md`. Those files are part of the hashed bundle inventory.

### 1.3 Apache-2.0 compliance (AutoDock Vina)

The bundled `vina.exe` is the official upstream v1.2.6 Windows release asset, unmodified.
Apache-2.0 §4 requires that redistributions carry a copy of the license and retain the
attribution notices. The unmodified license text from the v1.2.6 source tag is carried as
`tools/LICENSE.AutoDock-Vina.txt`, is hashed in `tools_manifest.json`, and is included in
both the standalone tools archive and Windows application. Vina is not modified, so no
"changed files" notice is required.

---

## 2. Python dependencies

Declared licenses as reported by the installed package metadata. All are permissive except
Meeko (LGPL-2.1) and Gemmi (MPL-2.0), both of which permit use by an MIT-licensed application
when consumed as unmodified, separately-installed packages.

| Package | License |
|---------|---------|
| fastapi | MIT |
| uvicorn | BSD-3-Clause |
| pydantic | MIT |
| python-multipart | Apache-2.0 |
| rdkit | BSD-3-Clause |
| numpy | BSD-3-Clause |
| scipy | BSD-3-Clause |
| scikit-learn | BSD-3-Clause |
| meeko | **LGPL-2.1** |
| prody | MIT |
| gemmi | **MPL-2.0** |
| psutil | BSD-3-Clause |
| requests | Apache-2.0 |
| sse-starlette | BSD-3-Clause |
| httpx | BSD-3-Clause |
| websockets | BSD-3-Clause |
| reportlab | BSD (BSD-3-Clause) |
| jinja2 | BSD-3-Clause |
| aiosqlite | MIT |

**Meeko (LGPL-2.1):** used as an imported Python library. LGPL-2.1 permits linking from a
work under a different license provided the library remains replaceable and its source is
available. Helix Core installs Meeko as an unmodified dependency; do not vendor a modified
copy without meeting LGPL source-availability terms.

**Gemmi (MPL-2.0):** file-level copyleft. Used unmodified; MPL obligations attach only to
modified MPL-covered files, not to Helix Core's own source.

---

## 3. JavaScript / frontend dependencies

Principal runtime and build dependencies (see `frontend/package.json` for the full list):

| Package | License |
|---------|---------|
| react, react-dom | MIT |
| react-router-dom | MIT |
| electron | MIT |
| electron-builder | MIT |
| vite | MIT |
| typescript | Apache-2.0 |
| molstar (Mol\*) | MIT |
| d3 | ISC |
| @playwright/test | Apache-2.0 |

---

*To regenerate the Python license summary:*

```bash
python -c "import importlib.metadata as m; [print(p, '|', (m.metadata(p).get('License-Expression') or m.metadata(p).get('License'))) for p in ['fastapi','rdkit','meeko','gemmi']]"
```

*To re-record the bundled-binary inventory in §1 after changing `tools/`:*

```bash
python scripts/fetch_tools.py --write-manifest   # rehash every file into tools_manifest.json
python scripts/fetch_tools.py --pack helixcore-tools-win-x64.zip   # rebuild the release asset
```
