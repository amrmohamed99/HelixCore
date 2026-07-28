# Contributing to Helix Core

Thanks for your interest in Helix Core. Bug reports, reproducible test cases, documentation
fixes, and code contributions are all welcome.

By contributing you agree that your contribution is licensed under the
[MIT License](LICENSE), the same license as the rest of the project.

## Ways to contribute

- **Report a bug** — open an issue with the steps to reproduce, the input files (or a
  minimal substitute), the expected result, and what actually happened. Backend errors are
  much easier to diagnose with the traceback from the terminal running `uvicorn`.
- **Report a scientific problem** — if a result looks chemically or physically wrong,
  say which module produced it and include the structure and parameters used. These reports
  are the most valuable kind.
- **Improve documentation** — corrections to the README, API descriptions, or this file.
- **Submit code** — see the workflow below.

## Development setup

Requirements: Python 3.12+, Node.js 20+, Windows 10/11 (the bundled `tools/` binaries are
Windows builds; see [Bundled Tools](README.md#bundled-tools--third-party-licenses)).

```bash
git clone https://github.com/amrmohamed99/HelixCore.git
cd HelixCore
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
```

Run the backend and frontend in two terminals:

```bash
PYTHONPATH=. python -m uvicorn backend.main:app --host 127.0.0.1 --port 8299 --reload
```

```bash
cd frontend && npm run dev
```

Interactive API docs are served at http://127.0.0.1:8299/docs while the backend is running.

## Before you open a pull request

Both checks must pass:

```bash
python -m pytest backend/tests/ -q
```

```bash
cd frontend && npm run build
```

The end-to-end Playwright suite (`npm run test:e2e` in `frontend/`) is optional locally but
useful when you change UI flows.

## Pull request guidelines

- **One concern per PR.** A bug fix and a refactor in the same branch are hard to review.
- **Add a test** for any behavior change in the backend. New API endpoints should have at
  least one contract test in `backend/tests/`.
- **Match the surrounding code.** The backend is FastAPI with Pydantic schemas in
  `backend/models/schemas.py`; routers stay thin and delegate to `backend/services/`. The
  frontend is React + TypeScript with CSS Modules.
- **Do not add a new runtime dependency** without saying in the PR why an existing one
  cannot do the job, and confirming the new dependency's license is compatible with MIT.
  Any addition must also be recorded in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
- **Never commit secrets**, API keys, credentials, patient or proprietary structure data.
- Describe how you verified the change — which command you ran and what it printed.

## Scientific changes

Helix Core is an orchestration layer over established engines (RDKit, AutoDock Vina,
Open Babel, Meeko). Changes that alter numerical output — scoring, filtering thresholds,
protonation, coordinate handling, descriptor calculation — need more than a passing test
suite:

- State the reference the new behavior follows (paper, engine documentation, or upstream
  default) in the PR description.
- Show the before/after values for at least one concrete structure.
- Do not introduce a new scoring function or predictive claim inside an existing module
  without discussing it in an issue first; the project deliberately makes no claim of
  predictive accuracy beyond what the underlying engines provide.

## Questions

Open an issue for anything that is not obviously a bug — design questions, integration
problems, and "is this the intended result?" are all fine. Conduct in issues and pull
requests is covered by the [Code of Conduct](CODE_OF_CONDUCT.md).
