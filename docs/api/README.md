<!--
  GENERATED FILE — do not edit by hand.
  Regenerate with:  python docs/generate_api_reference.py
  Source of truth:  backend/main.py (FastAPI app.openapi())
-->

# Helix Core HTTP API reference

`Helix Core Backend` v`3.0.0`. Generated from the OpenAPI 3.1.0 document
emitted by the application itself, not written by hand.

The machine-readable schema is committed alongside this file at
[`openapi.json`](openapi.json). Point any OpenAPI client generator at it.

While the backend is running, the same schema is served live and rendered
interactively:

| | |
|---|---|
| Swagger UI | <http://127.0.0.1:8299/docs> |
| ReDoc | <http://127.0.0.1:8299/redoc> |
| Raw schema | <http://127.0.0.1:8299/openapi.json> |

Everything is local. The backend binds `127.0.0.1` by default, there is no
authentication layer, and no telemetry is sent anywhere. Endpoints that reach
the network do so to named public services only: RCSB PDB, UniProt, ChEMBL, and
PubChem.

## Conventions

- Every path below is relative to `http://127.0.0.1:8299`.
- Request and response bodies are JSON unless stated otherwise.
- **File paths in requests are paths on the machine running the backend**, not
  uploads. `pdb_path`, `ligands_dir`, `receptor`, `results_dir` and friends are
  read and written directly by the server process.
- Long-running operations (docking, batch generation, conversion, pipeline runs)
  register with the job manager and can be paused, resumed, or terminated
  through `/api/jobs/*` while they run.

## Streaming endpoints

These carry no OpenAPI operation — the specification cannot describe a WebSocket,
and the SSE routes stream `text/event-stream` rather than a JSON body.

| Kind | Endpoint | Purpose |
|---|---|---|
| WebSocket | `/api/ws/progress` | Live job progress. Declared with `@router.websocket` in `backend/routers/ws.py`, so it cannot appear in the OpenAPI document. |
| SSE | `POST /api/pipeline/run-stream` | Server-sent events for a single-target pipeline run (`backend/routers/pipeline.py`). |
| SSE | `POST /api/pipeline/batch-stream` | Server-sent events for a batch pipeline run (`backend/routers/pipeline.py`). |

## Contents

- [Activity Log](#activity-log) — 4 operations
- [ADMET Profiler](#admet-profiler) — 2 operations
- [Analog Generator](#analog-generator) — 1 operation
- [Auto-Pipeline](#auto-pipeline) — 4 operations
- [Batch Generator](#batch-generator) — 1 operation
- [Chemical Clustering](#chemical-clustering) — 1 operation
- [Compound Comparison](#compound-comparison) — 1 operation
- [Compound Filters](#compound-filters) — 1 operation
- [Compound Watchlist](#compound-watchlist) — 4 operations
- [Converter](#converter) — 1 operation
- [Fragment Design](#fragment-design) — 4 operations
- [Interaction Profiler](#interaction-profiler) — 2 operations
- [Jobs](#jobs) — 4 operations
- [Minimization](#minimization) — 1 operation
- [Molecule Resolver](#molecule-resolver) — 2 operations
- [Oracle AI](#oracle-ai) — 1 operation
- [PDB Fetcher](#pdb-fetcher) — 3 operations
- [Pharmacophore](#pharmacophore) — 4 operations
- [Pocket Analyzer](#pocket-analyzer) — 3 operations
- [Project Management](#project-management) — 4 operations
- [Receptor Preparation](#receptor-preparation) — 2 operations
- [Report Generation](#report-generation) — 2 operations
- [Results Explorer](#results-explorer) — 7 operations
- [Scaffold Hopping](#scaffold-hopping) — 1 operation
- [Similarity Search](#similarity-search) — 1 operation
- [System](#system) — 3 operations
- [Virtual Screening](#virtual-screening) — 5 operations
- [General](#general) — 1 operation

70 HTTP operations in 28 groups, plus 3 streaming endpoints.

---

## Activity Log

### `POST /api/activity/clear`

**Clear Activity**

Clear all activity log entries.

Responses: `200`

### `GET /api/activity/export`

**Export Activity**

Return the raw JSONL content for download.

Responses: `200`

### `GET /api/activity/list`

**List Activities**

Read activity entries with pagination and optional page filter.

| Parameter | In | Type | Required | Notes |
|---|---|---|---|---|
| `page` | query | `integer` | no |  |
| `per_page` | query | `integer` | no |  |
| `filterPage` | query | `string`, optional | no |  |

Responses: `200`, `422`

### `POST /api/activity/log`

**Log Activity**

Append an activity entry to the log file.

<details><summary>Request body — <code>ActivityEntry</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `action` | `string` | yes | — | Short action description |
| `page` | `string` | no | `""` | Page where the action occurred |
| `details` | `object`, optional | no | — | Additional structured data |
| `duration_ms` | `integer`, optional | no | — | Duration of the action in ms |

</details>

Responses: `200`, `422`

---

## ADMET Profiler

### `POST /api/admet/batch`

**Batch Admet**

Compute ADMET profiles for a list of SMILES strings.

Expects ``{"smiles_list": ["CCO", "c1ccccc1", ...]}``

Responses: `200`, `422`

### `POST /api/admet/profile`

**Compute Admet**

Compute extended ADMET profile for SMILES or a file of molecules.

<details><summary>Request body — <code>ADMETRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `smiles` | `string`, optional | no | — |  |
| `file_path` | `string`, optional | no | — |  |
| `ro5` | `Ro5Thresholds` | no | `{"mw": 500.0, "logp": 5.0, "hbd": 5, "hba": 10, "max_violations": 1}` |  |

</details>

Responses: `200`, `422`

---

## Analog Generator

### `POST /api/analogs/generate`

**Generate Analogs**

Generate analogs using multiple enumeration strategies.

<details><summary>Request body — <code>AnalogRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `smiles` | `string` | yes | — |  |
| `name` | `string` | no | `"parent"` |  |
| `method` | `string` | no | `"fragment"` |  |
| `max_analogs` | `integer` | no | `20` |  |

</details>

Responses: `200`, `422`

---

## Auto-Pipeline

### `POST /api/pipeline/batch`

**Batch Pipeline**

Batch pipeline: SMILES file → 3D gen → minimize → convert → dock all.

<details><summary>Request body — <code>BatchPipelineRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `smiles_file` | `string` | yes | — |  |
| `receptor` | `string` | yes | — |  |
| `config` | `string` | yes | — |  |
| `force_field` | `string` | no | `"MMFF94"` |  |
| `run_filters` | `boolean` | no | `false` |  |
| `run_admet` | `boolean` | no | `false` |  |

</details>

Responses: `200`, `422`

### `POST /api/pipeline/batch-stream`

**Batch Pipeline Stream**

SSE-streamed batch pipeline with per-compound progress.

<details><summary>Request body — <code>BatchPipelineRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `smiles_file` | `string` | yes | — |  |
| `receptor` | `string` | yes | — |  |
| `config` | `string` | yes | — |  |
| `force_field` | `string` | no | `"MMFF94"` |  |
| `run_filters` | `boolean` | no | `false` |  |
| `run_admet` | `boolean` | no | `false` |  |

</details>

Responses: `200`, `422`

### `POST /api/pipeline/run`

**Run Pipeline**

Full end-to-end pipeline: SMILES → 3D PDB → PDBQT → Vina docking.

<details><summary>Request body — <code>PipelineRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `smiles` | `string` | yes | — |  |
| `name` | `string` | no | `"ligand"` |  |
| `receptor` | `string` | yes | — |  |
| `config` | `string` | yes | — |  |

</details>

Responses: `200`, `422`

### `POST /api/pipeline/run-stream`

**Run Pipeline Stream**

SSE-streamed single pipeline: SMILES → 3D → PDBQT → Vina docking with live progress.

<details><summary>Request body — <code>PipelineRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `smiles` | `string` | yes | — |  |
| `name` | `string` | no | `"ligand"` |  |
| `receptor` | `string` | yes | — |  |
| `config` | `string` | yes | — |  |

</details>

Responses: `200`, `422`

---

## Batch Generator

### `POST /api/batch/generate`

**Generate Batch**

Generate 3D PDB files from a SMILES list.

<details><summary>Request body — <code>BatchRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `smiles_file` | `string` | yes | — |  |

</details>

Responses: `200`, `422`

---

## Chemical Clustering

### `POST /api/cluster/analyze`

**Cluster Compounds**

Cluster docking results by Tanimoto similarity and pick diverse representatives.

<details><summary>Request body — <code>ClusterRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `results_dir` | `string` | yes | — |  |
| `src_dir` | `string` | no | `""` |  |
| `method` | `string` | no | `"Morgan"` |  |
| `cutoff` | `number` | no | `0.4` |  |

</details>

Responses: `200`, `422`

---

## Compound Comparison

### `POST /api/compare/compare`

**Compare Compounds**

Compare multiple compounds by computing their molecular properties.

<details><summary>Request body — <code>CompareRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `smiles_list` | array of `string` | yes | — |  |
| `names` | array of `string` | no | `[]` |  |
| `ro5_mw` | `number` | no | `500` |  |
| `ro5_logp` | `number` | no | `5` |  |
| `ro5_hbd` | `integer` | no | `5` |  |
| `ro5_hba` | `integer` | no | `10` |  |
| `ro5_max_violations` | `integer` | no | `1` |  |

</details>

Responses: `200`, `422`

---

## Compound Filters

### `POST /api/filters/scan`

**Scan Compounds**

Scan compounds for PAINS and structural alerts.

<details><summary>Request body — <code>FilterRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `input_path` | `string` | yes | — |  |
| `covalent_mode` | `boolean` | no | `false` |  |

</details>

Responses: `200`, `422`

---

## Compound Watchlist

### `POST /api/watchlist/add`

**Add To Watchlist**

Add a compound to the watchlist.

<details><summary>Request body — <code>WatchlistItem</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `id` | `string` | no | `""` |  |
| `name` | `string` | yes | — |  |
| `smiles` | `string`, optional | no | — |  |
| `score` | `number`, optional | no | — |  |
| `source` | `string` | no | `""` |  |
| `notes` | `string` | no | `""` |  |
| `added` | `string` | no | `""` |  |

</details>

Responses: `200`, `422`

### `GET /api/watchlist/list`

**List Watchlist**

Return all items on the watchlist.

Responses: `200`

### `DELETE /api/watchlist/remove/{item_id}`

**Remove From Watchlist**

Remove a compound from the watchlist by ID.

| Parameter | In | Type | Required | Notes |
|---|---|---|---|---|
| `item_id` | path | `string` | yes |  |

Responses: `200`, `422`

### `PUT /api/watchlist/update`

**Update Watchlist Item**

Update an existing watchlist item (notes, tags, flag).

<details><summary>Request body — <code>WatchlistItem</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `id` | `string` | no | `""` |  |
| `name` | `string` | yes | — |  |
| `smiles` | `string`, optional | no | — |  |
| `score` | `number`, optional | no | — |  |
| `source` | `string` | no | `""` |  |
| `notes` | `string` | no | `""` |  |
| `added` | `string` | no | `""` |  |

</details>

Responses: `200`, `422`

---

## Converter

### `POST /api/convert/`

**Convert**

Convert all .pdb files in a directory to .pdbqt using OpenBabel.

<details><summary>Request body — <code>ConvertRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `directory` | `string` | yes | — |  |

</details>

Responses: `200`, `422`

---

## Fragment Design

### `POST /api/fragments/decompose`

**Decompose Molecule**

Decompose a molecule into fragments using BRICS, RECAP, or Murcko scaffolding.

<details><summary>Request body — <code>FragmentDecomposeRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `smiles` | `string` | yes | — | SMILES of molecule to decompose |
| `method` | `string` | no | `"brics"` | 'brics' \| 'recap' \| 'murcko' |

</details>

Responses: `200`, `422`

### `POST /api/fragments/grow`

**Grow Fragment**

Grow a core fragment by adding common substituents at attachment points.

<details><summary>Request body — <code>FragmentGrowRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `core` | `string` | yes | — | Core fragment SMILES |
| `growth_vectors` | `integer` | no | `3` | Number of growth directions |
| `max_results` | `integer` | no | `50` |  |

</details>

Responses: `200`, `422`

### `GET /api/fragments/library`

**Get Fragment Library**

Return the curated fragment library, optionally filtered by category.

| Parameter | In | Type | Required | Notes |
|---|---|---|---|---|
| `category` | query | `string`, optional | no |  |
| `limit` | query | `integer` | no |  |

Responses: `200`, `422`

### `POST /api/fragments/link`

**Link Fragments**

Link two or more fragments together using BRICS rules.

<details><summary>Request body — <code>FragmentLinkRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `fragments` | array of `string` | yes | — | SMILES of fragments to link |
| `max_results` | `integer` | no | `50` |  |

</details>

Responses: `200`, `422`

---

## Interaction Profiler

### `POST /api/interactions/analyze`

**Analyze Interactions**

Detect protein-ligand interactions from PDBQT pose files.

<details><summary>Request body — <code>InteractionRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `receptor_path` | `string` | yes | — |  |
| `ligand_path` | `string` | yes | — |  |
| `cutoff` | `number` | no | `4.0` |  |

</details>

Responses: `200`, `422`

### `POST /api/interactions/network`

**Interaction Network**

Build a force-directed graph from protein-ligand interactions.

<details><summary>Request body — <code>InteractionRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `receptor_path` | `string` | yes | — |  |
| `ligand_path` | `string` | yes | — |  |
| `cutoff` | `number` | no | `4.0` |  |

</details>

Responses: `200`, `422`

---

## Jobs

### `GET /api/jobs/current`

**Current Job**

Return the active or just-finished global task.

Responses: `200`

### `POST /api/jobs/{job_id}/pause`

**Pause Job**

Pause the active task at the next safe checkpoint.

| Parameter | In | Type | Required | Notes |
|---|---|---|---|---|
| `job_id` | path | `string` | yes |  |

Responses: `200`, `422`

### `POST /api/jobs/{job_id}/resume`

**Resume Job**

Resume a paused task.

| Parameter | In | Type | Required | Notes |
|---|---|---|---|---|
| `job_id` | path | `string` | yes |  |

Responses: `200`, `422`

### `POST /api/jobs/{job_id}/terminate`

**Terminate Job**

Terminate the active task and keep any files already produced.

| Parameter | In | Type | Required | Notes |
|---|---|---|---|---|
| `job_id` | path | `string` | yes |  |

Responses: `200`, `422`

---

## Minimization

### `POST /api/minimize/`

**Minimize**

Optimize 3D geometry of .sdf/.pdb files using the specified force field.

<details><summary>Request body — <code>MinimizeRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `directory` | `string` | yes | — |  |
| `force_field` | `string` | no | `"MMFF94"` |  |

</details>

Responses: `200`, `422`

---

## Molecule Resolver

### `POST /api/resolve/batch`

**Resolve Batch**

Resolve multiple molecular identifiers in one call.

Request body: { "inputs": ["aspirin", "InChI=1S/...", "CC(=O)O", "50-78-2"] }
Returns: { "results": [...], "resolved": N, "failed": N }

Responses: `200`, `422`

### `POST /api/resolve/molecule`

**Resolve Molecule**

Resolve a molecular identifier (SMILES, InChI, name, CAS, MOL block) to canonical SMILES.

<details><summary>Request body — <code>ResolveRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `input` | `string` | yes | — | SMILES, InChI, compound name, CAS number, or MOL block |

</details>

Responses: `200`, `422`

---

## Oracle AI

### `POST /api/oracle/predict`

**Predict**

Run AI-based affinity rescoring on docking results.

<details><summary>Request body — <code>OracleRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `dock_dir` | `string` | yes | — |  |
| `model_path` | `string`, optional | no | — |  |

</details>

Responses: `200`, `422`

---

## PDB Fetcher

### `GET /api/fetch/controls/{pdb_id}`

**Find Drug Controls**

Search ChEMBL for approved drugs or high-affinity binders.

| Parameter | In | Type | Required | Notes |
|---|---|---|---|---|
| `pdb_id` | path | `string` | yes |  |

Responses: `200`, `422`

### `POST /api/fetch/pdb`

**Fetch Pdb**

Download a PDB from RCSB and save the unmodified structure.

<details><summary>Request body — <code>FetchPDBRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `pdb_id` | `string` | yes | — | 4-character PDB accession code |
| `output_dir` | `string` | yes | — |  |

</details>

Responses: `200`, `422`

### `GET /api/fetch/uniprot/{pdb_id}`

**Get Uniprot Info**

Fetch UniProt data for a PDB accession.

| Parameter | In | Type | Required | Notes |
|---|---|---|---|---|
| `pdb_id` | path | `string` | yes |  |

Responses: `200`, `422`

---

## Pharmacophore

### `POST /api/pharmacophore/generate`

**Generate Pharmacophore**

Extract pharmacophore features from a SMILES string and return SVG overlay.

<details><summary>Request body — <code>PharmGenerateRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `smiles` | `string` | yes | — | SMILES string of the reference molecule |
| `include_3d` | `boolean` | no | `false` | Generate 3D conformer and extract 3D features |

</details>

Responses: `200`, `422`

### `GET /api/pharmacophore/load`

**Load Pharmacophore**

Load a pharmacophore model from a JSON file.

| Parameter | In | Type | Required | Notes |
|---|---|---|---|---|
| `path` | query | `string` | yes |  |

Responses: `200`, `422`

### `POST /api/pharmacophore/save`

**Save Pharmacophore**

Save a pharmacophore model as JSON.

<details><summary>Request body — <code>PharmSaveRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `name` | `string` | yes | — | Pharmacophore model name |
| `reference_smiles` | `string` | yes | — |  |
| `features` | array of `PharmacophoreFeature` | no | `[]` |  |
| `output_dir` | `string` | yes | — |  |

</details>

Responses: `200`, `422`

### `POST /api/pharmacophore/screen`

**Screen Library**

Screen a compound library against a reference pharmacophore.

<details><summary>Request body — <code>PharmScreenRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `reference_smiles` | `string` | yes | — | SMILES of the reference compound |
| `library_source` | `string` | yes | — | .smi/.sdf file path or directory of .mol files |
| `mode` | `string` | no | `"2d"` | '2d' (fingerprint) or '3d' (alignment) |
| `threshold` | `number` | no | `0.5` | Similarity threshold for hits |

</details>

Responses: `200`, `422`

---

## Pocket Analyzer

### `POST /api/pocket/analyze`

**Analyze Pocket**

Find residues within 5 Å of a ligand in a protein-ligand complex.

<details><summary>Request body — <code>PocketAnalysisRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `pdb_path` | `string` | yes | — |  |
| `ligand_name` | `string` | no | `""` |  |
| `ligand_chain` | `string` | no | `""` | Optional exact ligand chain ID |
| `ligand_resseq` | `integer`, optional | no | — | Optional exact ligand residue sequence number |
| `ligand_icode` | `string` | no | `""` | Optional ligand insertion code |
| `padding` | `number` | no | `8.0` |  |

</details>

Responses: `200`, `422`

### `POST /api/pocket/druggability`

**Assess Druggability**

Heuristic druggability assessment of a binding pocket.

<details><summary>Request body — <code>DruggabilityRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `pdb_path` | `string` | yes | — |  |
| `ligand_name` | `string` | no | `""` |  |
| `ligand_chain` | `string` | no | `""` |  |
| `ligand_resseq` | `integer`, optional | no | — |  |
| `ligand_icode` | `string` | no | `""` |  |

</details>

Responses: `200`, `422`

### `POST /api/pocket/grid`

**Calculate Grid**

Calculate a grid box around the binding pocket (< 5 Å from ligand).

<details><summary>Request body — <code>PocketAnalysisRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `pdb_path` | `string` | yes | — |  |
| `ligand_name` | `string` | no | `""` |  |
| `ligand_chain` | `string` | no | `""` | Optional exact ligand chain ID |
| `ligand_resseq` | `integer`, optional | no | — | Optional exact ligand residue sequence number |
| `ligand_icode` | `string` | no | `""` | Optional ligand insertion code |
| `padding` | `number` | no | `8.0` |  |

</details>

Responses: `200`, `422`

---

## Project Management

### `DELETE /api/projects/delete/{project_id}`

**Delete Project**

Delete a project by ID.

| Parameter | In | Type | Required | Notes |
|---|---|---|---|---|
| `project_id` | path | `string` | yes |  |

Responses: `200`, `422`

### `GET /api/projects/list`

**List Projects**

List all saved projects.

Responses: `200`

### `GET /api/projects/load/{project_id}`

**Load Project**

Load a single project by ID.

| Parameter | In | Type | Required | Notes |
|---|---|---|---|---|
| `project_id` | path | `string` | yes |  |

Responses: `200`, `422`

### `POST /api/projects/save`

**Save Project**

Create or overwrite a named project.

<details><summary>Request body — <code>Project</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `id` | `string` | no | `""` |  |
| `name` | `string` | yes | — |  |
| `target_name` | `string` | no | `""` |  |
| `pdb_id` | `string` | no | `""` |  |
| `receptor_path` | `string` | no | `""` |  |
| `grid_config` | `string` | no | `""` |  |
| `ligand_source` | `string` | no | `""` |  |
| `notes` | `string` | no | `""` |  |
| `created` | `string` | no | `""` |  |
| `updated` | `string` | no | `""` |  |
| `pipeline_state` | `object` | no | `{}` |  |
| `page_inputs` | `object` | no | `{}` |  |
| `session_data` | `object` | no | `{}` |  |

</details>

Responses: `200`, `422`

---

## Receptor Preparation

### `POST /api/prepare/analyze`

**Analyze Pdb**

Analyze a PDB file — list chains, ligands, waters, and ions.

<details><summary>Request body — <code>AnalyzePDBRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `pdb_path` | `string` | no | `""` |  |
| `pdb_id` | `string` | no | `""` |  |

</details>

Responses: `200`, `422`

### `POST /api/prepare/run`

**Prepare Receptor**

Clean a PDB and convert to PDBQT for docking.

<details><summary>Request body — <code>PrepareReceptorRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `pdb_path` | `string` | yes | — |  |
| `keep_chain` | `string` | no | `""` |  |
| `remove_water` | `boolean` | no | `true` |  |
| `remove_ligands` | `boolean` | no | `true` |  |
| `remove_ions` | `boolean` | no | `true` |  |
| `add_hydrogens` | `boolean` | no | `true` |  |

</details>

Responses: `200`, `422`

---

## Report Generation

### `GET /api/report/download`

**Download Report**

Download a generated report file.

| Parameter | In | Type | Required | Notes |
|---|---|---|---|---|
| `path` | query | `string` | yes |  |

Responses: `200`, `422`

### `POST /api/report/generate`

**Generate Report**

Generate a PDF or HTML report from screening results.

<details><summary>Request body — <code>ReportRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `title` | `string`, optional | no | — | Report title |
| `format` | `string` | no | `"both"` | 'pdf' \| 'html' \| 'both' |
| `results_dir` | `string`, optional | no | — | Auto-collect from docking results dir |
| `sections` | array of `object`, optional | no | — | Custom sections to include |
| `output_dir` | `string`, optional | no | — | Directory to save reports |
| `project_name` | `string`, optional | no | — |  |
| `author` | `string`, optional | no | — |  |
| `custom_text` | `string`, optional | no | — | Free-form notes to include |

</details>

Responses: `200`, `422`

---

## Results Explorer

### `POST /api/results/consensus`

**Consensus Scoring**

Multi-method consensus ranking: Vina score + MMFF energy + contact count.

<details><summary>Request body — <code>ConsensusRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `results_dir` | `string` | yes | — |  |
| `src_dir` | `string` | no | `""` |  |

</details>

Responses: `200`, `422`

### `POST /api/results/csv-report`

**Csv Report**

Generate a CSV report with docking scores + ADMET properties.

<details><summary>Request body — <code>CSVReportRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `res_dir` | `string` | yes | — |  |
| `src_dir` | `string` | no | `""` |  |
| `top_n` | `integer` | no | `10` |  |
| `ro5` | `Ro5Thresholds` | no | `{"mw": 500.0, "logp": 5.0, "hbd": 5, "hba": 10, "max_violations": 1}` |  |

</details>

Responses: `200`, `422`

### `POST /api/results/export-sdf`

**Export Sdf**

Convert a list of compounds from a source directory to a combined SDF file.

Body: { "names": ["mol1", "mol2"], "src_dir": "path" }
Returns: { "sdf_path": "...", "count": N }

Responses: `200`, `422`

### `POST /api/results/export-top`

**Export Top Hits**

Export top N docked results + original ligands into separate folders.

<details><summary>Request body — <code>ExportTopRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `top_n` | `integer` | no | `10` |  |
| `src_dir` | `string` | yes | — |  |
| `results_dir` | `string` | yes | — |  |

</details>

Responses: `200`, `422`

### `GET /api/results/iupac`

**Resolve Iupac**

Resolve SMILES to IUPAC/common name via PubChem.

| Parameter | In | Type | Required | Notes |
|---|---|---|---|---|
| `smiles` | query | `string` | yes |  |

Responses: `200`, `422`

### `GET /api/results/load`

**Load Results**

Scan a results directory and return ranked candidates.

| Parameter | In | Type | Required | Notes |
|---|---|---|---|---|
| `dir` | query | `string` | yes |  |

Responses: `200`, `422`

### `GET /api/results/load-csv`

**Load Csv**

Load and parse an existing Report CSV for charting.

| Parameter | In | Type | Required | Notes |
|---|---|---|---|---|
| `path` | query | `string` | yes |  |

Responses: `200`, `422`

---

## Scaffold Hopping

### `POST /api/scaffold/hop`

**Scaffold Hop**

Perform scaffold hopping using the specified method.

<details><summary>Request body — <code>ScaffoldHopRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `smiles` | `string` | yes | — | SMILES of the reference compound |
| `method` | `string` | no | `"murcko"` | 'murcko' \| 'mcs' \| 'rgroup' \| 'mmp' |
| `library_path` | `string`, optional | no | — | Path to library .smi/.sdf file |
| `max_results` | `integer` | no | `50` |  |

</details>

Responses: `200`, `422`

---

## Similarity Search

### `POST /api/similarity/search`

**Similarity Search**

Run similarity search against PubChem, ChEMBL, or local database.

<details><summary>Request body — <code>SimilarityRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `query` | `string` | yes | — |  |
| `method` | `string` | no | `"Morgan"` |  |
| `database` | `string` | no | `"PubChem"` |  |
| `local_db_path` | `string`, optional | no | — |  |

</details>

Responses: `200`, `422`

---

## System

### `GET /api/system/mol-svg`

**Molecule Svg**

Render a molecule as SVG — accepts SMILES, InChI, compound name, or CAS number.

| Parameter | In | Type | Required | Notes |
|---|---|---|---|---|
| `smiles` | query | `string` | yes | SMILES string to render |
| `width` | query | `integer` | no |  |
| `height` | query | `integer` | no |  |

Responses: `200`, `422`

### `GET /api/system/stats`

**System Stats**

Return CPU and RAM utilization.

Responses: `200`

### `GET /api/system/structure-file`

**Serve Structure File**

Serve a local structure file (PDB/PDBQT/MOL2/SDF/CIF) as plain text for the 3D viewer.

| Parameter | In | Type | Required | Notes |
|---|---|---|---|---|
| `path` | query | `string` | yes | Absolute path to a structure file |

Responses: `200`, `422`

---

## Virtual Screening

### `POST /api/docking/auto-grid`

**Auto Calculate Grid**

Calculate grid box from all ATOM/HETATM coordinates in a receptor file.

<details><summary>Request body — <code>AutoGridRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `receptor_path` | `string` | yes | — |  |
| `padding` | `number` | no | `10.0` |  |

</details>

Responses: `200`, `422`

### `POST /api/docking/decompose`

**Decompose Pose**

Parse a Vina log file and extract energy decomposition components.

<details><summary>Request body — <code>PoseDecompRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `log_path` | `string` | yes | — |  |

</details>

Responses: `200`, `422`

### `POST /api/docking/multi-target`

**Multi Target Docking**

Dock ligands against multiple receptors and build a selectivity matrix.

<details><summary>Request body — <code>MultiTargetRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `ligands_dir` | `string` | yes | — | Directory of PDBQT ligand files |
| `receptors` | array of `string` | yes | — | List of receptor file paths |
| `config_paths` | array of `string`, optional | no | — | Config per receptor (or single shared) |
| `grids` | array of `object`, optional | no | — |  |
| `exhaustiveness` | `integer` | no | `8` |  |
| `seed` | `integer` | no | `42` | Deterministic AutoDock Vina random seed |
| `mode` | `string` | no | `"sequential"` | 'sequential' \| 'parallel' |

</details>

Responses: `200`, `422`

### `POST /api/docking/run`

**Run Docking**

Run sequential Vina docking on all .pdbqt ligands in a folder.

<details><summary>Request body — <code>DockingRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `ligands_dir` | `string` | yes | — |  |
| `receptor` | `string` | yes | — |  |
| `config_path` | `string`, optional | no | — |  |
| `grid` | `GridBox`, optional | no | — |  |
| `exhaustiveness` | `integer` | no | `8` |  |
| `seed` | `integer` | no | `42` | Deterministic AutoDock Vina random seed |

</details>

Responses: `200`, `422`

### `POST /api/docking/run-ws`

**Run Docking Ws**

Run Vina docking with real-time WebSocket progress updates.

Same as /run but emits per-ligand progress via the WS manager.
The task_id is returned in the response so the client can track it.

<details><summary>Request body — <code>DockingRequest</code></summary>

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `ligands_dir` | `string` | yes | — |  |
| `receptor` | `string` | yes | — |  |
| `config_path` | `string`, optional | no | — |  |
| `grid` | `GridBox`, optional | no | — |  |
| `exhaustiveness` | `integer` | no | `8` |  |
| `seed` | `integer` | no | `42` | Deterministic AutoDock Vina random seed |

</details>

Responses: `200`, `422`

---

## General

### `GET /api/health`

**Health Check**

Health check endpoint used by the Electron shell.

Responses: `200`

---

## Schemas

The OpenAPI document defines 104 component schemas. They are not reproduced here — read them in [`openapi.json`](openapi.json), or browse them with the type-aware rendering at <http://127.0.0.1:8299/redoc> while the backend runs.
