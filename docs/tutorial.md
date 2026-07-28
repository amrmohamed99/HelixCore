# Tutorial — a complete run against trypsin (PDB 3PTB)

This is the whole application, start to finish, on a target small enough to finish
in under a minute of compute: **bovine β-trypsin with benzamidine bound**, PDB entry
[3PTB](https://www.rcsb.org/structure/3PTB).

You will fetch the structure, clean it into a docking-ready receptor, find the
binding pocket and derive a grid box from the crystallographic ligand, build 3D
ligands from SMILES, dock eight compounds, profile them, and produce a report.

3PTB is the right first target for a reason: its native ligand, benzamidine, sits in
a well-defined S1 specificity pocket anchored by Asp189. If your setup is correct,
benzamidine and its analogues come out on top and the deliberately included
non-binders come out at the bottom. That gives you a **sanity check with a known
answer**, not just an output file.

**Time:** about 10 minutes of reading and clicking. Under 20 seconds of compute.
**Prerequisites:** a working install — see [installation.md](installation.md) —
and a network connection for step 1 (RCSB download).

Every number, path, and message below was produced by running exactly these steps.
Where a value depends on your machine, it says so.

---

## Contents

- [Conventions](#conventions)
- [Step 0 — set up a working folder](#step-0--set-up-a-working-folder)
- [Step 1 — fetch 3PTB](#step-1--fetch-3ptb)
- [Step 2 — inspect the structure](#step-2--inspect-the-structure)
- [Step 3 — prepare the receptor](#step-3--prepare-the-receptor)
- [Step 4 — analyse the pocket and derive a grid box](#step-4--analyse-the-pocket-and-derive-a-grid-box)
- [Step 5 — build 3D ligands from SMILES](#step-5--build-3d-ligands-from-smiles)
- [Step 6 — convert ligands to PDBQT](#step-6--convert-ligands-to-pdbqt)
- [Step 7 — dock](#step-7--dock)
- [Step 8 — ADMET profile](#step-8--admet-profile)
- [Step 9 — rank and report](#step-9--rank-and-report)
- [Optional — interaction profile of the top pose](#optional--interaction-profile-of-the-top-pose)
- [What was reproducible, and what was not](#what-was-reproducible-and-what-was-not)
- [Where everything ended up](#where-everything-ended-up)

---

## Conventions

Each step is given twice.

- **In the GUI** — the page in the left sidebar, the fields to fill, the button to
  press. Button labels are quoted exactly as they appear.
- **Through the API** — a `curl` call against `http://127.0.0.1:8299`. Use this if
  you are scripting, running headless, or in the container.

The two are the same code path; the GUI is a client of the API.

**File paths in API requests are paths on the machine running the backend**, not
uploads. In the GUI they come from a native file picker.

`$WS` below is your workspace root. It defaults to `workspace/` inside the checkout;
Electron overrides it per-user (see
[Configuration reference](installation.md#configuration-reference)). Substitute your
own absolute path — on Windows, forward slashes work fine in JSON.

```bash
WS=/absolute/path/to/your/workspace
```

<!-- SCREENSHOT: the application at first launch, Dashboard page, sidebar visible.
     Shows the five workflow groups the tutorial walks through. -->

---

## Step 0 — set up a working folder

Copy the bundled example ligand set into the workspace. **Do not run the tutorial
directly out of `examples/`**: several steps write output directories next to their
input file (`Batch_3D/` next to the SMILES file, `pdbqt_out/` next to the PDBs), and
you do not want generated files landing inside the repository.

```bash
mkdir -p "$WS/tutorial"
cp examples/trypsin_ligands.smi "$WS/tutorial/"
```

The file holds eight compounds — see [`examples/README.md`](../examples/README.md)
for what each one is and why it is there. Six are trypsin-like cations expected to
occupy the S1 pocket; two (aspirin, caffeine) are negative controls that should not.

---

## Step 1 — fetch 3PTB

**In the GUI:** sidebar → **PDB Fetch**. Type `3PTB` into *PDB ID*, choose your
`tutorial` folder as *Output Directory*, press **🔬 Fetch PDB**.

**Through the API:**

```bash
curl -s -X POST http://127.0.0.1:8299/api/fetch/pdb \
  -H 'Content-Type: application/json' \
  -d "{\"pdb_id\":\"3PTB\",\"output_dir\":\"$WS/tutorial\"}"
```

**Expected output**

```json
{
  "pdb_path": "…/tutorial/3PTB.pdb",
  "message": "PDB saved: …/tutorial/3PTB.pdb"
}
```

The file is downloaded from `files.rcsb.org` **unmodified**. Nothing is stripped or
rewritten at this stage — cleaning is step 3, and keeping the two separate means you
always have the original to go back to.

<!-- SCREENSHOT: PDB Fetch page after a successful fetch, showing the resolved path
     and the structure summary card. -->

---

## Step 2 — inspect the structure

Look before you clean. This step tells you what is actually in the file and what
you are about to throw away.

**In the GUI:** sidebar → **Prepare Receptor**. Enter `3PTB` in *PDB ID*, or pick
the file you just downloaded in *Local PDB File*. Press **🔍 Analyze PDB**.

**Through the API:**

```bash
curl -s -X POST http://127.0.0.1:8299/api/prepare/analyze \
  -H 'Content-Type: application/json' \
  -d "{\"pdb_path\":\"$WS/tutorial/3PTB.pdb\"}"
```

**Expected output**

| Field | Value |
|---|---|
| `chains` | `["A"]` |
| `ligands` | `["BEN"]` |
| `water_count` | `62` |
| `ions` | `["CA"]` |
| `atom_count` | `1701` |

`BEN` is benzamidine, the crystallographic ligand. `CA` is a structural calcium.
The 62 waters are ordinary crystallographic solvent.

The response also carries an **integrity report**, and 3PTB is a good example of why
it exists rather than a formality:

```json
"integrity": {
  "status": "warning",
  "residue_count": 223,
  "sequence_gaps": [
    {"chain": "A", "from": 34,  "to": 37,  "missing_count": 2},
    {"chain": "A", "from": 67,  "to": 69,  "missing_count": 1},
    {"chain": "A", "from": 125, "to": 127, "missing_count": 1},
    {"chain": "A", "from": 130, "to": 132, "missing_count": 1},
    {"chain": "A", "from": 204, "to": 209, "missing_count": 4},
    {"chain": "A", "from": 217, "to": 219, "missing_count": 1}
  ],
  "ca_breaks": [],
  "missing_backbone": [],
  "warnings": ["6 residue numbering gap(s)"]
}
```

**Read this correctly.** Six numbering gaps, but `ca_breaks` is empty — no two
consecutive Cα atoms are further apart than a peptide bond allows. The chain is
continuous *in space*; only the *numbers* skip. That is the chymotrypsinogen
numbering convention that trypsin structures conventionally use (it is also why you
will see a residue labelled `ALA 221A` in the next step). Nothing is missing and
nothing needs modelling in.

Contrast that with a report showing populated `ca_breaks` or `missing_backbone`:
that is genuine missing density, and docking into it without repairing the loop
first will give you a pocket with a hole in it. The tool reports the two
separately so you can tell them apart.

<!-- SCREENSHOT: Prepare Receptor step 2, showing the four stat cards
     (Chains / Ligands / Waters / Ion Types) and the ProteinIntegrityReport panel. -->

---

## Step 3 — prepare the receptor

**In the GUI:** still on **Prepare Receptor**, now on the *Cleaning Options* card.
Leave all four boxes ticked — *Remove waters (62)*, *Remove ligands (1)*,
*Remove ions (1)*, *Add hydrogens*. Press **🧹 Prepare Receptor**.

**Through the API:**

```bash
curl -s -X POST http://127.0.0.1:8299/api/prepare/run \
  -H 'Content-Type: application/json' \
  -d "{\"pdb_path\":\"$WS/tutorial/3PTB.pdb\",
       \"remove_water\":true,\"remove_ligands\":true,
       \"remove_ions\":true,\"add_hydrogens\":true}"
```

**Expected output**

```json
{
  "output_path":    "…/prepared_receptors/3PTB.pdbqt",
  "clean_pdb_path": "…/prepared_receptors/3PTB_clean.pdb",
  "removed_waters": 62,
  "removed_ligands": 9,
  "removed_ions": 1,
  "prep_engine": "meeko",
  "message": "Receptor prepared with meeko: removed 62 waters, 9 ligand atoms, 1 ions",
  "warnings": [
    "Removed 9 ligand/cofactor atom records before docking receptor preparation.",
    "Removed 1 ion atom records; metal-dependent sites may require manual treatment."
  ]
}
```

Notes worth absorbing:

- `removed_ligands: 9` counts **atoms**, not molecules. Benzamidine has 9 heavy
  atoms. Removing it is the point: we are about to dock ligands back into the site
  it occupied, so it must not still be sitting there.
- `prep_engine: "meeko"` tells you which path ran. Meeko is preferred; if it fails,
  the router falls back to Open Babel with Gasteiger charges and reports that here
  rather than silently. **Check this field.** A run you thought was Meeko-prepared
  but was not is a difference you want to know about.
- The calcium warning is not boilerplate. If your target's chemistry depends on a
  metal, stripping it is wrong and you should re-run with `remove_ions: false`.
  Trypsin's calcium is structural and far from S1, so removing it is fine here.
- Two files are written: the cleaned PDB (human-readable, viewable, re-runnable)
  and the PDBQT that Vina actually reads.

<!-- SCREENSHOT: Prepare Receptor step 3 "Preparation Complete" card, with the
     removed-counts stats grid and both output paths. -->

---

## Step 4 — analyse the pocket and derive a grid box

Both calls here take the **original** `3PTB.pdb`, not the cleaned receptor — they
need the crystallographic ligand to locate the site.

**In the GUI:** sidebar → **Pocket Analysis**. Set *PDB File* to
`tutorial/3PTB.pdb`, *Ligand Name* to `BEN`, leave *Padding* at `8`. Press
**🎯 Analyze Pocket**.

**Through the API:**

```bash
curl -s -X POST http://127.0.0.1:8299/api/pocket/analyze \
  -H 'Content-Type: application/json' \
  -d "{\"pdb_path\":\"$WS/tutorial/3PTB.pdb\",\"ligand_name\":\"BEN\",\"padding\":8.0}"
```

**Expected output** — 17 residues within 5 Å of benzamidine, 9 ligand atoms:

```
ALA 221A, ASP 189, SER 190, CYS 191, GLN 192, SER 195, VAL 213, SER 214,
TRP 215, GLY 216, SER 217, GLY 219, CYS 220, PRO 225, GLY 226, VAL 227, TYR 228
```

**This is your correctness check, and it is a strong one.** `ASP 189` is the S1
specificity residue whose carboxylate pairs with benzamidine's amidinium — the
entire reason trypsin cleaves after arginine and lysine. `SER 195` is the catalytic
serine. `TRP 215` and `GLY 216` line the substrate groove. If those residues are in
your list, you have found trypsin's active site and not a surface crevice. If they
are not, stop and check that you passed the un-cleaned PDB and the right ligand code.

Now the grid box:

```bash
curl -s -X POST http://127.0.0.1:8299/api/pocket/grid \
  -H 'Content-Type: application/json' \
  -d "{\"pdb_path\":\"$WS/tutorial/3PTB.pdb\",\"ligand_name\":\"BEN\",\"padding\":8.0}"
```

**Expected output**

```json
{
  "grid": {
    "center_x": -1.874, "center_y": 13.215, "center_z": 17.032,
    "size_x":   18.425, "size_y":   18.133, "size_z":   20.969
  },
  "output_path": "…/tutorial/grid.txt",
  "ligand_atom_count": 9
}
```

These six numbers are **purely geometric** — derived from atom coordinates in the
PDB file. They do not depend on your OS, CPU, or engine version, so if you get
different values, something upstream differs (a different PDB revision, a different
ligand selection) and it is worth finding out what before you dock.

The box is the bounding box of the pocket residues plus `padding` Å on each
dimension. Vina refuses boxes above 126 Å and the endpoint rejects them up front;
docking accuracy also degrades above roughly 80 Å, which the docking router warns
about. At ~19 Å per side this is a tight, well-posed box.

A copy is written to `grid.txt` beside the PDB, in Vina config format, so you can
feed it to `vina --config` directly.

<!-- SCREENSHOT: Pocket Analysis results, showing the residue list and the computed
     grid box card. -->

---

## Step 5 — build 3D ligands from SMILES

SMILES are 2D. Vina needs 3D coordinates.

**In the GUI:** sidebar → **Batch Generate**. Pick
`tutorial/trypsin_ligands.smi` as *SMILES File* and run it.

**Through the API:**

```bash
curl -s -X POST http://127.0.0.1:8299/api/batch/generate \
  -H 'Content-Type: application/json' \
  -d "{\"smiles_file\":\"$WS/tutorial/trypsin_ligands.smi\"}"
```

**Expected output**

```json
{
  "output_dir": "…/tutorial/Batch_3D",
  "generated": 8,
  "failed": 0,
  "failures": []
}
```

Eight `.pdb` files named from the second column of the SMILES file:
`benzamidine.pdb`, `4-aminobenzamidine.pdb`, and so on.

Each molecule gets explicit hydrogens, an ETKDG embedding with `randomSeed=42`, and
MMFF optimisation. The fixed seed is what makes conformer generation reproducible;
if the first embedding fails, a random-coordinate retry runs — also seeded.

> **SMILES file format.** One record per line, `SMILES` then whitespace then an
> optional name. The name becomes the output filename, so keep it filesystem-safe.
> **Comment lines are not supported** — every non-blank line is parsed as a
> molecule, so a `#` line is reported as an invalid SMILES rather than skipped.
> Anything that fails to parse or embed is listed individually in `failures` with a
> reason; the run does not abort.

---

## Step 6 — convert ligands to PDBQT

**In the GUI:** sidebar → **Format Convert**. Set *Directory with PDB Files* to
`tutorial/Batch_3D` and run it.

**Through the API:**

```bash
curl -s -X POST http://127.0.0.1:8299/api/convert/ \
  -H 'Content-Type: application/json' \
  -d "{\"directory\":\"$WS/tutorial/Batch_3D\"}"
```

**Expected output**

```json
{
  "output_dir": "…/tutorial/Batch_3D/pdbqt_out",
  "converted": 8,
  "failed": 0,
  "failures": []
}
```

Open Babel assigns Gasteiger partial charges and writes AutoDock atom types. Every
output file is validated as a *ligand* PDBQT before being counted as converted — a
file that came out structurally wrong is reported as a failure here rather than
becoming a mysterious docking error three steps later.

---

## Step 7 — dock

**In the GUI:** sidebar → **Docking**. Set *Ligands Directory (PDBQT)* to
`tutorial/Batch_3D/pdbqt_out`, *Receptor File* to
`prepared_receptors/3PTB.pdbqt`, type the six grid numbers from step 4 into the grid
fields and press **✓ Apply Grid**, then press **🧲 Run Docking**.

**Through the API:**

```bash
curl -s -X POST http://127.0.0.1:8299/api/docking/run \
  -H 'Content-Type: application/json' \
  -d "{\"ligands_dir\":\"$WS/tutorial/Batch_3D/pdbqt_out\",
       \"receptor\":\"$WS/prepared_receptors/3PTB.pdbqt\",
       \"grid\":{\"center_x\":-1.874,\"center_y\":13.215,\"center_z\":17.032,
                 \"size_x\":18.425,\"size_y\":18.133,\"size_z\":20.969},
       \"exhaustiveness\":8,\"seed\":42}"
```

**Expected output** — all eight `ok`, ranked best to worst:

| Ligand | Vina score (kcal/mol) |
|---|---:|
| 4-aminobenzamidine | −6.382 |
| 4-hydroxybenzamidine | −6.313 |
| 4-methylbenzamidine | −6.236 |
| benzamidine | −6.080 |
| phenylguanidine | −5.830 |
| aspirin | −5.294 |
| caffeine | −5.260 |
| benzylamine | −5.043 |

**Read the ranking, not the numbers.** The five amidine/guanidine cations occupy the
top five places; the two negative controls and the weakly-binding benzylamine
occupy the bottom three. That separation is the result the tutorial exists to
demonstrate, and it is what tells you your receptor, grid, and ligands are all
correct. The absolute scores are Vina's empirical function and should not be read as
predicted affinities.

Docking took **11–12 seconds** for all eight ligands (Windows 11, 20 logical CPUs,
exhaustiveness 8). Timing scales with exhaustiveness, ligand flexibility, box
volume, and thread count.

Outputs land in `pdbqt_out/Docking_Results/` — a `<name>_out.pdbqt` holding the
poses and a `<name>_log.log` holding Vina's own output for every ligand. The log
begins with the engine banner, which is the record of exactly what produced the
score:

```
AutoDock Vina v1.2.6-56-gc28e340
...
Rigid receptor: …/prepared_receptors/3PTB.pdbqt
Grid center: X -1.874 Y 13.215 Z 17.032
Grid size  : X 18.425 Y 18.133 Z 20.969
Exhaustiveness: 8
CPU: 8
```

Thread count is chosen automatically as `min(cpu_count − 1, 8)`. See
[reproducibility](#what-was-reproducible-and-what-was-not) for why that matters.

While the run is in progress, the floating job tracker shows per-ligand progress and
the job can be paused, resumed, or terminated — through the tracker in the GUI, or
via `POST /api/jobs/{job_id}/pause|resume|terminate`.

<!-- SCREENSHOT: Docking page mid-run, floating job tracker visible with per-ligand
     progress; and a second shot of the completed score-distribution chart. -->

---

## Step 8 — ADMET profile

Docking says "does it fit". This says "is it a plausible molecule".

**In the GUI:** sidebar → **ADMET**. Choose *File / Directory*, select
`tutorial/trypsin_ligands.smi`, press **💊 Run ADMET Profile**.

**Through the API:**

```bash
curl -s -X POST http://127.0.0.1:8299/api/admet/profile \
  -H 'Content-Type: application/json' \
  -d "{\"file_path\":\"$WS/tutorial/trypsin_ligands.smi\"}"
```

**Expected output** — 8 profiles, plus `admet_profiles.csv` beside the input:

| Name | MW | LogP | TPSA | QED | SA | ESOL logS | Ro5 | BBB flag |
|---|---:|---:|---:|---:|---:|---:|:--:|:--:|
| benzamidine | 120.15 | 0.97 | 49.87 | 0.421 | 1.47 | −1.624 | PASS (0) | true |
| 4-aminobenzamidine | 135.17 | 0.55 | 75.89 | 0.299 | 1.83 | −1.404 | PASS (0) | true |
| 4-hydroxybenzamidine | 136.15 | 0.68 | 70.10 | 0.392 | 1.77 | −1.488 | PASS (0) | true |
| 4-methylbenzamidine | 134.18 | 1.28 | 49.87 | 0.441 | 1.55 | −1.856 | PASS (0) | true |
| phenylguanidine | 135.17 | 0.99 | 61.90 | 0.397 | 1.74 | −1.681 | PASS (0) | true |
| benzylamine | 107.16 | 1.15 | 26.02 | 0.572 | 1.22 | −1.715 | PASS (0) | true |
| aspirin | 180.16 | 1.31 | 63.60 | 0.550 | 1.58 | −1.992 | PASS (0) | true |
| caffeine | 194.19 | −1.03 | 61.82 | 0.538 | 2.30 | −0.871 | PASS (0) | **false** |

Every compound passes Lipinski with zero violations, which is unsurprising for
fragments this small and is exactly why Ro5 alone is a weak filter.

### The BBB output is a triage flag, not a prediction

Look at the last column. **Caffeine is flagged as non-permeant.** Caffeine is one of
the most reliably CNS-active molecules there is.

This is not a bug, and it is not hidden. The BBB output is a **three-threshold
descriptor filter** — MW < 450, TPSA < 90, LogP within [0.5, 4.5] — and caffeine's
LogP of −1.03 falls below the floor. It is not a trained permeability model, does
not claim to be one, and this specific false negative is named in the caveat the API
itself returns:

> BBB triage flag — a three-threshold descriptor filter (MW, TPSA, LogP), not a
> trained blood-brain-barrier permeability model. It is a coarse triage aid with
> known false negatives: caffeine is CNS-active yet falls below the LogP floor and
> is flagged as non-permeant. Do not report it as a permeability prediction.

The response returns the flag, all three criteria with their values, operators,
thresholds, and individual pass/fail, and that caveat string — so the verdict is
never an unexplained number. Caffeine is in the example set deliberately, so that
the limitation is the first thing you see rather than something you discover after
building an argument on it.

<!-- SCREENSHOT: ADMET Profiler results table with the BBB triage column and the
     expanded criteria breakdown for caffeine. -->

---

## Step 9 — rank and report

**In the GUI:** sidebar → **Results**. Set *Results Directory* to
`tutorial/Batch_3D/pdbqt_out/Docking_Results`, press **📋 Load Results**, then
**📄 Report**.

**Through the API:**

```bash
# Ranked candidates — note the query parameter is `dir`
curl -s "http://127.0.0.1:8299/api/results/load?dir=$WS/tutorial/Batch_3D/pdbqt_out/Docking_Results"

# HTML + PDF report
curl -s -X POST http://127.0.0.1:8299/api/report/generate \
  -H 'Content-Type: application/json' \
  -d "{\"results_dir\":\"$WS/tutorial/Batch_3D/pdbqt_out/Docking_Results\",
       \"format\":\"both\",
       \"title\":\"Trypsin (3PTB) tutorial\",
       \"project_name\":\"3PTB tutorial\"}"
```

**Expected output** — the same eight candidates in ranked order, then:

```json
{
  "paths": [
    "…/reports/report_<timestamp>.pdf",
    "…/reports/report_<timestamp>.html"
  ],
  "message": "Generated 2 report(s)"
}
```

The report auto-collects from the results directory: a summary block (total
candidates, best score, counts at ≤ −6 and ≤ −8 kcal/mol) and the full ranked table.
Use `"format": "html"` or `"pdf"` for one of the two.

Other things this page can do, all against the same directory: **📊 Generate CSV**
(scores joined to ADMET descriptors), **📦 Export Top N** (copies the best poses and
their source ligands to a separate folder — this one also needs *Source Directory*),
and **🏆 Consensus Rank** (combines Vina score, MMFF energy, and contact count).

<!-- SCREENSHOT: Results Explorer with candidates loaded, score-distribution chart
     visible; plus the first page of the generated HTML report. -->

---

## Optional — interaction profile of the top pose

Worth doing once, because it closes the loop back to step 4.

```bash
curl -s -X POST http://127.0.0.1:8299/api/interactions/analyze \
  -H 'Content-Type: application/json' \
  -d "{\"receptor_path\":\"$WS/prepared_receptors/3PTB.pdbqt\",
       \"ligand_path\":\"$WS/tutorial/Batch_3D/pdbqt_out/Docking_Results/benzamidine_out.pdbqt\",
       \"cutoff\":4.0}"
```

Counts for the docked benzamidine pose: 20 H-bonds, 142 hydrophobic contacts, 162
total, 0 salt bridges. The first three contacts listed are

| Type | Residue | Ligand atom | Receptor atom | Distance |
|---|---|---|---|---|
| H-bond | ASP189 | N1 | OD1 | 2.98 Å |
| H-bond | SER190 | N1 | O | 3.13 Å |
| H-bond | GLY219 | N1 | O | 2.86 Å |

The amidine nitrogen hydrogen-bonded to Asp189 OD1 at 2.98 Å is the canonical
trypsin S1 interaction. Docking put the ligand back where crystallography found it.

**Why zero salt bridges?** Because the ligand was built from a *neutral* amidine
SMILES. Salt-bridge detection requires the ligand nitrogen to carry a Gasteiger
partial charge above +0.2, and in the neutral form Open Babel assigns N1 a charge of
**−0.343**, so the contact is classified as a hydrogen bond instead. At physiological
pH benzamidine is protonated and this really is an ionic interaction. If you want it
labelled as one, build the ligand from a charged SMILES such as
`NC(=[NH2+])c1ccccc1`. This is a genuine consequence of preparing ligands from
neutral SMILES, and it applies to every basic ligand you dock, not just this one.

Counts are **multi-label**: one atom pair can be both an H-bond and a salt bridge and
is counted in both. `total_single_label` and `salt_bridges_single_label` reproduce
the older one-label-per-pair numbers for continuity with previously published
figures.

---

## What was reproducible, and what was not

Run the tutorial twice on this machine and the docking scores were **bit-identical**
across all eight ligands — verified, not assumed. That comes from three explicit
choices: the ETKDG conformer seed is fixed at 42, the Vina seed defaults to 42 and is
passed on the command line, and the ligand file order is sorted deterministically
rather than left to filesystem enumeration order.

Reproducibility across machines is a weaker claim, and the docs will not pretend
otherwise:

| Layer | Stable across machines? |
|---|---|
| Pocket residues, grid box | **Yes** — pure geometry from the PDB file. |
| RDKit descriptors, ADMET table | **Yes**, for a given RDKit version (2025.03.2 here). |
| 3D conformers | Yes for a given RDKit version; ETKDG changes between RDKit releases. |
| PDBQT charges | Yes for a given Open Babel version (3.1.1 here). |
| **Vina scores** | **Not guaranteed.** |

Vina's thread count is derived from your CPU: `min(cpu_count − 1, 8)`, so a machine
with fewer cores runs a different number of Monte-Carlo threads. Same seed, different
thread count, different search — and possibly a different final pose. Add a different
Vina build and the scores are not comparable at all, which is the whole reason the
[engine guard](engine-guard.md) exists.

For a measurement you intend to publish: fix the engine, record the thread count and
exhaustiveness, and run replicate seeds. The tutorial's exhaustiveness of 8 is Vina's
default and is chosen here for speed; controlled work in this repository uses 32 with
three seeds.

---

## Where everything ended up

```
$WS/
├── tutorial/
│   ├── 3PTB.pdb                        ← step 1, unmodified from RCSB
│   ├── grid.txt                        ← step 4, Vina config format
│   ├── trypsin_ligands.smi             ← step 0, copied from examples/
│   ├── admet_profiles.csv              ← step 8
│   └── Batch_3D/
│       ├── *.pdb                       ← step 5, 8 files
│       └── pdbqt_out/
│           ├── *.pdbqt                 ← step 6, 8 files
│           ├── auto_config.txt         ← step 7, the grid Vina was given
│           └── Docking_Results/
│               ├── *_out.pdbqt         ← step 7, poses
│               └── *_log.log           ← step 7, Vina output incl. engine banner
├── prepared_receptors/
│   ├── 3PTB_clean.pdb                  ← step 3
│   └── 3PTB.pdbqt                      ← step 3, the docking receptor
└── reports/
    └── report_<timestamp>.{html,pdf}   ← step 9
```

To start over, delete `$WS/tutorial` and `$WS/prepared_receptors/3PTB*`. Nothing
outside the workspace was modified.

---

## Next

- Same pipeline in one call: **Auto Pipeline** in the sidebar, or
  `POST /api/pipeline/run` (`/run-stream` for server-sent progress events).
- Every endpoint used above, with full request schemas:
  [API reference](api/README.md).
- Something did not match? [Troubleshooting](troubleshooting.md).
