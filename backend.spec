# -*- mode: python ; coding: utf-8 -*-
"""
Helix Core — PyInstaller spec for the FastAPI backend (Windows and Linux).

Produces a --onedir distribution under `dist/backend/`:

    Windows   dist/backend/backend.exe
    Linux     dist/backend/backend

Electron launches that binary in production and picks the name by platform
(`frontend/electron/main.ts`), and `frontend/electron-builder.yml` maps
`../dist/backend` into `resources/backend` for every target, so the same
relative layout has to come out of this spec on both platforms.

Build:

    Windows   pyinstaller backend.spec --noconfirm      (see build_portable.ps1)
    Linux     bash scripts/build_backend_linux.sh

--------------------------------------------------------------------------
Platform notes
--------------------------------------------------------------------------
Docking engines are not bundled by PyInstaller on any platform. On Windows the `tools/`
tree (AutoDock Vina + Open Babel) is placed next to the binary by
electron-builder's `win.extraResources`, and `run_backend.py` points
HELIX_TOOLS_DIR at it. `tools/` holds Windows executables only, is not in git,
and has no tracked Linux counterpart. The Linux electron-builder target stages
the verified upstream Vina binary from untracked `linux-tools/`; Open Babel is
resolved from PATH. Nothing platform-specific is therefore needed inside the
PyInstaller bundle — this paragraph exists so the omission reads as deliberate.

UPX is applied on Windows only. It is not installed in the Linux build
environment, and UPX-compressed ELF objects interact badly with the
PyInstaller bootloader's shared-library loading for no size saving that any
packaging step depends on.

RDKit ships its `Data/` and `Contrib/` trees *inside* the Python package in the
PyPI wheel (`RDPaths._share == os.path.dirname(__file__)`) but *outside* it in
a conda-forge install (`$PREFIX/share/RDKit`), which is the layout
`backend/environment.yml` produces. `collect_data_files('rdkit')` only sees the
first case, so a conda-built binary would silently lose
`Data/BaseFeatures.fdef` (every pharmacophore request) and `Contrib/SA_Score`
(where `backend/routers/admet.py` falls back to a heuristic without raising).
The layout is detected below and the trees are collected plus a generated
runtime hook points RDBASE at them.

The Linux binary is only as portable as the glibc of the machine that builds
it: PyInstaller does not bundle libc, so an AppImage/deb built on Ubuntu 24.04
(glibc 2.39) will not start on an older distribution. Build on the oldest
target baseline, or in the container from `Dockerfile`.
"""

import os
import sys
import textwrap
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

# `SPECPATH` and `workpath` are injected into the spec namespace by PyInstaller.
# Resolving data paths against the spec directory rather than the process CWD
# keeps the build correct no matter where it is invoked from.
SPEC_DIR = Path(globals().get("SPECPATH", os.getcwd())).resolve()
WORK_DIR = Path(globals().get("workpath", SPEC_DIR / "build" / "backend")).resolve()

# UPX on Windows only — see the module docstring.
USE_UPX = IS_WINDOWS

# Stripping symbols shrinks the Linux bundle substantially but has a history of
# corrupting conda-built shared objects, so it stays opt-in on every platform.
STRIP_SYMBOLS = os.environ.get("HELIX_PYI_STRIP", "").lower() in ("1", "true", "yes")

# --------------------------------------------------------------------------- #
#  Hidden imports — packages that PyInstaller can't detect automatically       #
# --------------------------------------------------------------------------- #

hidden = [
    # FastAPI / Uvicorn stack
    *collect_submodules('uvicorn'),
    *collect_submodules('fastapi'),
    *collect_submodules('starlette'),
    *collect_submodules('pydantic'),
    *collect_submodules('pydantic_core'),
    'multipart',
    'python_multipart',

    # Our backend package. `backend.tests` is filtered out: it imports pytest,
    # which is excluded below, so collecting it would compile the suite into the
    # PYZ and emit a missing-module warning for every test module.
    *collect_submodules('backend', filter=lambda name: not name.startswith('backend.tests')),

    # Science
    *collect_submodules('rdkit'),
    *collect_submodules('numpy'),
    *collect_submodules('meeko'),
    *collect_submodules('prody'),
    *collect_submodules('scipy.linalg'),
    *collect_submodules('scipy.special'),
    *collect_submodules('scipy.spatial'),
    'gemmi',

    # ML
    *collect_submodules('sklearn'),
    *collect_submodules('joblib'),

    # Monitoring & HTTP
    'psutil',
    'requests',
    'httpx',
    'httpcore',
    'h11',
    'sniffio',
    'anyio',
    'certifi',
    'idna',
    'charset_normalizer',

    # WebSocket
    'websockets',

    # Standard lib helpers uvicorn needs
    'email.mime.multipart',
    'email.mime.text',
    'logging.config',
    'unittest',
    'unittest.case',
    'unittest.mock',
]

# --------------------------------------------------------------------------- #
#  RDKit resource trees (conda layout only)                                    #
# --------------------------------------------------------------------------- #

# Destination directory inside the bundle. Kept out of `rdkit/` so it can never
# shadow the collected Python package.
RDKIT_SHARE_DEST = 'rdkit_share'


def _external_rdkit_share():
    """Return the RDKit share root when it lives outside the Python package.

    Returns None for the PyPI-wheel layout, where `collect_data_files('rdkit')`
    already collects `Data/` and `Contrib/` and no fixup is needed.
    """
    try:
        import rdkit
        from rdkit import RDPaths
    except Exception as exc:  # pragma: no cover - build-time diagnostic
        print(f"[helix-spec] WARNING: rdkit not importable at build time ({exc})")
        return None

    share = Path(getattr(RDPaths, '_share', '')).resolve()
    package_dir = Path(rdkit.__file__).resolve().parent

    if not share.is_dir():
        print(f"[helix-spec] WARNING: RDKit share dir {share} does not exist")
        return None

    # Wheel layout: _share IS the package directory.
    if share == package_dir or package_dir in share.parents:
        return None

    return share


_rdkit_share = _external_rdkit_share()
rdkit_share_datas = []

if _rdkit_share is not None:
    for sub in ('Data', 'Contrib'):
        src = _rdkit_share / sub
        if src.is_dir():
            rdkit_share_datas.append((str(src), f'{RDKIT_SHARE_DEST}/{sub}'))
        else:
            print(f"[helix-spec] WARNING: expected RDKit tree missing: {src}")
    print(f"[helix-spec] RDKit share collected from {_rdkit_share} -> {RDKIT_SHARE_DEST}/")

# A runtime hook is the only place RDBASE can be set early enough: RDConfig
# reads it at import time, and the backend imports rdkit from many modules.
# The hook is generated here rather than committed so it can never drift from
# RDKIT_SHARE_DEST, and it no-ops when the tree was not collected (Windows).
_RTHOOK_SOURCE = textwrap.dedent(
    f'''\
    # Generated by backend.spec — do not edit, do not commit.
    #
    # conda-forge installs RDKit's Data/ and Contrib/ trees outside the Python
    # package and bakes the absolute build-time path into rdkit/RDPaths.py, so a
    # frozen binary would look for them under the build machine's environment
    # prefix. rdkit.RDConfig honours RDBASE ahead of RDPaths, so point it at the
    # copies collected into the bundle.
    import os
    import sys

    _base = getattr(sys, "_MEIPASS", None)
    if _base and not os.environ.get("RDBASE"):
        _share = os.path.join(_base, {RDKIT_SHARE_DEST!r})
        if os.path.isdir(os.path.join(_share, "Data")):
            os.environ["RDBASE"] = _share
    '''
)

_rthook_path = WORK_DIR / 'helix_rthooks' / 'pyi_rth_helix_rdkit.py'
_rthook_path.parent.mkdir(parents=True, exist_ok=True)
if not _rthook_path.is_file() or _rthook_path.read_text(encoding='utf-8') != _RTHOOK_SOURCE:
    _rthook_path.write_text(_RTHOOK_SOURCE, encoding='utf-8')

runtime_hooks = [str(_rthook_path)]

# --------------------------------------------------------------------------- #
#  Backend source, bundled as data                                             #
# --------------------------------------------------------------------------- #

# `run_backend.py` puts sys._MEIPASS on sys.path when frozen, so this copy is
# what any path-based import of `backend.*` resolves against. Collected file by
# file rather than as one (src_dir, dest_dir) pair so three things stay out:
#
#   __pycache__/  byte-compiled by PyInstaller's own analysis pass moments
#                 earlier, so bundling it makes the artifact depend on whether
#                 the tree had ever been imported before — the same spec, same
#                 sources, different bytes.
#   tests/        the pytest suite. It imports pytest (excluded below), is
#                 never run from a frozen binary, and reads requirements files
#                 from the source tree, not the bundle.
#   requirement / environment manifests, for the same reason.

_BACKEND_SRC = SPEC_DIR / 'backend'
_SKIP_DIRS = {'__pycache__', 'tests', '.pytest_cache', '.mypy_cache'}
_SKIP_SUFFIXES = {'.pyc', '.pyo'}
_SKIP_NAMES = {'requirements.txt', 'requirements.lock.txt', 'environment.yml'}

backend_source_datas = []
for _root, _subdirs, _files in os.walk(_BACKEND_SRC):
    _subdirs[:] = [d for d in _subdirs if d not in _SKIP_DIRS]
    _dest = Path('backend') / Path(_root).relative_to(_BACKEND_SRC)
    for _name in _files:
        if _name in _SKIP_NAMES or Path(_name).suffix in _SKIP_SUFFIXES:
            continue
        backend_source_datas.append((str(Path(_root) / _name), str(_dest)))

if not backend_source_datas:  # pragma: no cover - build-time guard
    raise SystemExit(f"[helix-spec] no backend sources found under {_BACKEND_SRC}")

# --------------------------------------------------------------------------- #
#  Data files — templates, type stubs, etc. that packages ship                 #
# --------------------------------------------------------------------------- #

datas = [
    *collect_data_files('pydantic'),
    *collect_data_files('certifi'),
    *collect_data_files('meeko'),  # Bundled residue chem templates JSON
    *collect_data_files('rdkit'),  # Wheel layout: feature definitions, descriptors, templates

    # conda layout: the same trees, from $PREFIX/share/RDKit. Empty otherwise.
    *rdkit_share_datas,

    # Include the backend source as data so _MEIPASS-based imports work
    *backend_source_datas,
]

binaries = [
    *collect_dynamic_libs('rdkit'),
]

# --------------------------------------------------------------------------- #
#  Analysis                                                                   #
# --------------------------------------------------------------------------- #

a = Analysis(
    [str(SPEC_DIR / 'run_backend.py')],
    pathex=[str(SPEC_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=runtime_hooks,
    excludes=[
        # GUI frameworks — not needed for headless API server.
        #
        # PIL/Pillow is NOT in this list, though it looks like it belongs:
        # reportlab imports it unconditionally (reportlab.lib.utils), so
        # excluding it makes `from reportlab.platypus import ...` in
        # backend/services/report_builder.py raise ImportError, REPORTLAB_AVAILABLE
        # go False, and every POST /api/report/generate with format=pdf answer
        # 500 "reportlab not installed" from a bundle that does contain
        # reportlab. Verified against a frozen Linux build before this line
        # existed.
        'tkinter', 'matplotlib',
        'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
        'pygame', 'wx', 'gtk',

        # Heavy ML/DL frameworks — NOT used by this app
        'tensorflow', 'tf', 'keras', 'tensorboard', 'tensorrt',
        'torch', 'torchvision', 'torchaudio',
        'onnx', 'onnxruntime', 'onnxruntime_providers_cuda',
        'catboost', 'xgboost', 'lightgbm',
        'transformers', 'tokenizers', 'huggingface_hub',
        'jax', 'jaxlib', 'flax', 'optax',
        'caffe', 'caffe2', 'mxnet', 'paddle', 'paddlepaddle',

        # Computer vision — not needed
        'cv2', 'opencv', 'opencv_python',

        # NLP / large libs
        'spacy', 'gensim', 'nltk', 'stanza',

        # Jupyter / notebook
        'IPython', 'jupyter', 'notebook', 'ipykernel', 'ipywidgets',
        'nbconvert', 'nbformat', 'jupyterlab',

        # Testing / docs
        'pytest', 'sphinx', 'docutils', 'coverage', 'tox',

        # gRPC / protobuf (pulled by TF)
        'grpc', 'grpcio', 'google', 'proto',

        # Other heavy packages
        'pandas',
        'lxml',
        'sympy', 'dask', 'distributed',
        'bokeh', 'plotly', 'seaborn', 'altair',
        'numba', 'llvmlite',
        'pyarrow', 'tables', 'h5py', 'hdf5',
        'sqlalchemy', 'alembic',
        'celery', 'kombu',
        'scrapy', 'selenium',
        'cryptography',
        'Cython',
        'pip',
        'test', 'tests',

        # pywin32 GUI components — not needed for headless API.
        # Absent on Linux/macOS, where excluding them is a no-op.
        'Pythonwin', 'win32ui', 'win32com',
        'pythoncom', 'pywintypes',

        # scipy submodules nothing in the bundle imports.
        #
        # This list used to also hold optimize, stats, cluster, integrate,
        # interpolate, fft and ndimage under the claim that our sklearn
        # operations do not use them. They do — transitively and at import
        # time. Each name below was re-derived by blocking exactly one scipy
        # subpackage with a sys.meta_path finder and importing every dependency
        # the backend actually uses (helix/conda-forge, Python 3.12, scipy
        # 1.15.3, scikit-learn 1.8.0, ProDy 2.6.1):
        #
        #   optimize stats integrate interpolate fft ndimage
        #       -> `from sklearn.ensemble import RandomForestRegressor` raises
        #          ModuleNotFoundError, so backend/routers/oracle.py sets
        #          ML_AVAILABLE = False and /api/oracle/predict silently ignores
        #          a user-supplied model, reporting method="thermodynamic_pKd".
        #   cluster (plus all of the above)
        #       -> `import prody` raises.
        #   signal io odr
        #       -> nothing in the bundle notices. Hence, and only hence, these
        #          three.
        #
        # Re-run that experiment before adding a name here.
        'scipy.signal',
        'scipy.io',
        'scipy.odr',
    ],
    noarchive=False,
)

# --------------------------------------------------------------------------- #
#  Bundle                                                                     #
# --------------------------------------------------------------------------- #

pyz = PYZ(a.pure)

# PyInstaller appends `.exe` on Windows and leaves the name bare elsewhere, so
# this single name yields dist/backend/backend.exe and dist/backend/backend —
# exactly the two paths frontend/electron/main.ts selects between.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=STRIP_SYMBOLS,
    upx=USE_UPX,
    console=True,     # keep console so Electron can capture stdout/stderr
    icon=None,
)

# Strip binaries we don't need. These are Windows artefacts (Pythonwin GUI,
# the MFC runtime pywin32 drags in); the filter is a no-op elsewhere.
if IS_WINDOWS:
    strip_prefixes = ('Pythonwin', 'mfc140u', 'win32ui')
    filtered_binaries = [b for b in a.binaries if not any(b[0].startswith(p) for p in strip_prefixes)]
else:
    filtered_binaries = a.binaries

coll = COLLECT(
    exe,
    filtered_binaries,
    a.zipfiles,
    a.datas,
    strip=STRIP_SYMBOLS,
    upx=USE_UPX,
    upx_exclude=[],
    name='backend',
)
