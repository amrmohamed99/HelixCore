"""
Results Explorer router — load, export, and generate reports.
Ported from drug_tool.py: load_results_data, _t_export_top_hits, _t_process_hits.
"""

import os
import csv
import shutil
import subprocess
import urllib.request
import json as json_mod
from fastapi import APIRouter, HTTPException, Query

_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

from backend.config import get_obabel
from backend.models.schemas import (
    Candidate,
    LoadResultsResponse,
    ExportTopRequest,
    CSVReportRequest,
    CSVRow,
    CSVReportResponse,
    ConsensusRequest,
    ConsensusResult,
    ConsensusResponse,
    IUPACResponse,
)
from backend.utils.paths import get_obabel_env
from backend.utils.pdbqt_utils import parse_vina_score, parse_vina_log_score

router = APIRouter()

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, Lipinski
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False


@router.get("/load", response_model=LoadResultsResponse)
async def load_results(dir: str = Query(...)):
    """Scan a results directory and return ranked candidates."""
    if not os.path.isdir(dir):
        raise HTTPException(status_code=400, detail="Directory not found")

    target_dir = dir
    sub = os.path.join(dir, "Docking_Results")
    if os.path.isdir(sub):
        target_dir = sub

    candidates: list[Candidate] = []

    # Method 1: from log files
    for fname in os.listdir(target_dir):
        if fname.endswith("_log.log"):
            base_name = fname.replace("_log.log", "")
            score = parse_vina_log_score(os.path.join(target_dir, fname))
            candidates.append(
                Candidate(name=base_name, score=score, dir=target_dir)
            )

    # Method 2: fallback to _out.pdbqt REMARK
    if not candidates:
        for fname in os.listdir(target_dir):
            if fname.endswith("_out.pdbqt"):
                base_name = fname.replace("_out.pdbqt", "")
                score = parse_vina_score(os.path.join(target_dir, fname))
                candidates.append(
                    Candidate(name=base_name, score=score, dir=target_dir)
                )

    candidates.sort(key=lambda c: c.score)
    return LoadResultsResponse(candidates=candidates)


@router.post("/export-top")
async def export_top_hits(req: ExportTopRequest):
    """Export top N docked results + original ligands into separate folders."""
    if not os.path.isdir(req.results_dir):
        raise HTTPException(status_code=400, detail="Results directory not found")
    if not os.path.isdir(req.src_dir):
        raise HTTPException(status_code=400, detail="Source ligands directory not found")
    if req.top_n < 1:
        raise HTTPException(status_code=400, detail="Top N must be at least 1")

    # Load candidates
    resp = await load_results(dir=req.results_dir)
    hits = resp.candidates[: req.top_n]

    if not hits:
        raise HTTPException(status_code=404, detail="No candidates found")

    results_dir = hits[0].dir
    parent_dir = (
        os.path.dirname(results_dir)
        if os.path.basename(results_dir) == "Docking_Results"
        else results_dir
    )

    top_hits_dir = os.path.join(parent_dir, "Top_Hits")
    top_originals_dir = os.path.join(top_hits_dir, "Original_Ligands")
    if os.path.isdir(top_hits_dir):
        shutil.rmtree(top_hits_dir)
    os.makedirs(top_hits_dir, exist_ok=True)
    os.makedirs(top_originals_dir, exist_ok=True)

    exported = 0
    missing: list[str] = []
    copied_docked = 0
    copied_logs = 0

    for hit in hits:
        name = hit.name

        # Copy docked output
        docked = os.path.join(results_dir, f"{name}_out.pdbqt")
        if os.path.exists(docked):
            shutil.copy2(docked, os.path.join(top_hits_dir, f"{name}_out.pdbqt"))
            copied_docked += 1

        # Copy log
        log = os.path.join(results_dir, f"{name}_log.log")
        if os.path.exists(log):
            shutil.copy2(log, os.path.join(top_hits_dir, f"{name}_log.log"))
            copied_logs += 1

        # Copy original
        original = os.path.join(req.src_dir, f"{name}.pdbqt")
        if os.path.exists(original):
            shutil.copy2(
                original,
                os.path.join(top_originals_dir, f"{name}.pdbqt"),
            )
            exported += 1
        else:
            missing.append(name)

    # Summary CSV
    summary_path = os.path.join(top_hits_dir, "Top_Hits_Summary.csv")
    with open(summary_path, "w", newline="") as csvf:
        w = csv.writer(csvf)
        w.writerow(["Rank", "Ligand", "Score (kcal/mol)", "Original PDBQT Found"])
        for rank, hit in enumerate(hits, 1):
            found = "YES" if hit.name not in missing else "MISSING"
            w.writerow([rank, hit.name, hit.score, found])

    return {
        "top_hits_dir": top_hits_dir,
        "originals_dir": top_originals_dir,
        "output_dir": top_hits_dir,
        "exported": copied_docked,
        "originals_exported": exported,
        "logs_exported": copied_logs,
        "total": len(hits),
        "missing": missing,
    }


@router.post("/csv-report", response_model=CSVReportResponse)
async def csv_report(req: CSVReportRequest):
    """Generate a CSV report with docking scores + ADMET properties."""
    if not os.path.isdir(req.res_dir):
        raise HTTPException(status_code=400, detail="Results directory not found")

    res_dir = req.res_dir
    sub = os.path.join(res_dir, "Docking_Results")
    if os.path.isdir(sub):
        res_dir = sub

    # Gather hits from logs
    hits: list[tuple[str, float]] = []
    for fname in os.listdir(res_dir):
        if fname.endswith("_log.log"):
            score = parse_vina_log_score(os.path.join(res_dir, fname))
            hits.append((fname.replace("_log.log", ""), score))

    if not hits:
        for fname in os.listdir(res_dir):
            if fname.endswith("_out.pdbqt"):
                score = parse_vina_score(os.path.join(res_dir, fname))
                hits.append((fname.replace("_out.pdbqt", ""), score))

    hits.sort(key=lambda x: x[1])
    top = hits[: req.top_n]

    ob = get_obabel()
    env = get_obabel_env()

    rows: list[CSVRow] = []

    for rank, (name, score) in enumerate(top, 1):
        mw = logp = tpsa = None
        hbd = hba = None
        rule5 = "Unknown"
        mol = None

        # Try loading from source
        if req.src_dir:
            src_f = os.path.join(req.src_dir, f"{name}.pdb")
            if os.path.exists(src_f) and RDKIT_AVAILABLE:
                mol = Chem.MolFromPDBFile(src_f)

        # Fallback: convert docked output
        if mol is None and RDKIT_AVAILABLE:
            docked_file = os.path.join(res_dir, f"{name}_out.pdbqt")
            if os.path.exists(docked_file):
                temp_pdb = os.path.join(res_dir, "temp_calc.pdb")
                try:
                    subprocess.run(
                        [ob, docked_file, "-O", temp_pdb],
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=_NO_WINDOW,
                    )
                    if os.path.exists(temp_pdb):
                        mol = Chem.MolFromPDBFile(temp_pdb)
                        os.remove(temp_pdb)
                except Exception:
                    pass

        if mol and RDKIT_AVAILABLE:
            try:
                mw = round(Descriptors.MolWt(mol), 2)
                logp = round(Descriptors.MolLogP(mol), 2)
                hbd = Lipinski.NumHDonors(mol)
                hba = Lipinski.NumHAcceptors(mol)
                tpsa = round(Descriptors.TPSA(mol), 2)
                violations = 0
                if mw and mw > req.ro5.mw:
                    violations += 1
                if logp and logp > req.ro5.logp:
                    violations += 1
                if hbd and hbd > req.ro5.hbd:
                    violations += 1
                if hba and hba > req.ro5.hba:
                    violations += 1
                rule5 = "PASS" if violations <= req.ro5.max_violations else f"FAIL ({violations})"
            except Exception:
                pass

        rows.append(
            CSVRow(
                rank=rank,
                ligand=name,
                score=score,
                mw=mw,
                logp=logp,
                hbd=hbd,
                hba=hba,
                tpsa=tpsa,
                rule_of_5=rule5,
            )
        )

    # Save CSV
    out_dir = os.path.join(res_dir, "Analysis")
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "Report.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Rank", "Ligand", "Score", "MW", "LogP", "HBD", "HBA", "TPSA", "Rule of 5"])
        for row in rows:
            w.writerow([
                row.rank, row.ligand, row.score,
                row.mw or "N/A", row.logp or "N/A",
                row.hbd or "N/A", row.hba or "N/A",
                row.tpsa or "N/A", row.rule_of_5,
            ])

    return CSVReportResponse(rows=rows, csv_path=csv_path)


@router.get("/load-csv", response_model=CSVReportResponse)
async def load_csv(path: str = Query(...)):
    """Load and parse an existing Report CSV for charting."""
    if not os.path.isfile(path):
        raise HTTPException(status_code=400, detail="CSV file not found")

    rows: list[CSVRow] = []
    with open(path, "r") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            try:
                score = float(row.get("Score", 0))
                mw_raw = row.get("MW", "N/A")
                logp_raw = row.get("LogP", "N/A")
                hbd_raw = row.get("HBD", "N/A")
                hba_raw = row.get("HBA", "N/A")
                tpsa_raw = row.get("TPSA", "N/A")

                rows.append(
                    CSVRow(
                        rank=int(row.get("Rank", i + 1)),
                        ligand=row.get("Ligand", f"Lig_{i}"),
                        score=score,
                        mw=float(mw_raw) if mw_raw != "N/A" else None,
                        logp=float(logp_raw) if logp_raw != "N/A" else None,
                        hbd=int(hbd_raw) if hbd_raw != "N/A" else None,
                        hba=int(hba_raw) if hba_raw != "N/A" else None,
                        tpsa=float(tpsa_raw) if tpsa_raw != "N/A" else None,
                        rule_of_5=row.get("Rule of 5", "Unknown"),
                    )
                )
            except Exception:
                pass

    return CSVReportResponse(rows=rows)


@router.post("/consensus", response_model=ConsensusResponse)
async def consensus_scoring(req: ConsensusRequest):
    """Multi-method consensus ranking: Vina score + MMFF energy + contact count."""
    if not os.path.isdir(req.results_dir):
        raise HTTPException(status_code=400, detail="Results directory not found")

    res_dir = req.results_dir
    sub = os.path.join(res_dir, "Docking_Results")
    if os.path.isdir(sub):
        res_dir = sub

    hits: dict[str, ConsensusResult] = {}

    for fname in os.listdir(res_dir):
        if fname.endswith("_log.log"):
            name = fname.replace("_log.log", "")
            score = parse_vina_log_score(os.path.join(res_dir, fname))
            hits[name] = ConsensusResult(ligand=name, vina_score=score)

    if not hits:
        for fname in os.listdir(res_dir):
            if fname.endswith("_out.pdbqt"):
                name = fname.replace("_out.pdbqt", "")
                score = parse_vina_score(os.path.join(res_dir, fname))
                hits[name] = ConsensusResult(ligand=name, vina_score=score)

    if not hits:
        raise HTTPException(status_code=404, detail="No docking results found")

    if RDKIT_AVAILABLE and req.src_dir and os.path.isdir(req.src_dir):
        for name in hits:
            src_f = os.path.join(req.src_dir, f"{name}.pdb")
            if not os.path.exists(src_f):
                src_f = os.path.join(req.src_dir, f"{name}.sdf")
            if os.path.exists(src_f):
                try:
                    mol = (
                        Chem.MolFromPDBFile(src_f)
                        if src_f.endswith(".pdb")
                        else Chem.MolFromMolFile(src_f)
                    )
                    if mol:
                        from rdkit.Chem import AllChem
                        ff = AllChem.MMFFGetMoleculeForceField(mol, AllChem.MMFFGetMoleculeProperties(mol))
                        if ff:
                            hits[name].mmff_energy = round(ff.CalcEnergy(), 2)
                except Exception:
                    pass

    sorted_by_vina = sorted(hits.values(), key=lambda x: x.vina_score if x.vina_score is not None else 999)
    for rank, r in enumerate(sorted_by_vina, 1):
        r.vina_rank = rank

    # Note: MMFF energy is computed from source (pre-docking) conformation,
    # reflecting ligand internal strain, not binding-pose energy.
    sorted_by_energy = sorted(
        [h for h in hits.values() if h.mmff_energy is not None],
        key=lambda x: x.mmff_energy,
    )
    for rank, r in enumerate(sorted_by_energy, 1):
        r.energy_rank = rank

    for r in hits.values():
        # contact_rank is reserved for future protein-ligand contact counting;
        # currently unimplemented, so consensus uses vina_rank + energy_rank only.
        ranks = [r2 for r2 in [r.vina_rank, r.energy_rank, r.contact_rank] if r2 is not None]
        r.consensus_rank = round(sum(ranks) / len(ranks), 2) if ranks else None

    results = sorted(hits.values(), key=lambda x: x.consensus_rank if x.consensus_rank is not None else 999)

    csv_path = os.path.join(res_dir, "consensus_ranking.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Ligand", "Vina", "VinaRank", "MMFF", "EnergyRank", "ConsensusRank"])
        for r in results:
            w.writerow([r.ligand, r.vina_score, r.vina_rank, r.mmff_energy, r.energy_rank, r.consensus_rank])

    return ConsensusResponse(results=list(results), csv_path=csv_path)


@router.get("/iupac", response_model=IUPACResponse)
async def resolve_iupac(smiles: str = Query(...)):
    """Resolve SMILES to IUPAC/common name via PubChem."""
    try:
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/{urllib.request.quote(smiles)}/property/IUPACName/JSON"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json_mod.loads(resp.read())
            iupac = data.get("PropertyTable", {}).get("Properties", [{}])[0].get("IUPACName")
    except Exception:
        iupac = None

    common = None
    try:
        url2 = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/{urllib.request.quote(smiles)}/synonyms/JSON"
        req2 = urllib.request.Request(url2, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            data2 = json_mod.loads(resp2.read())
            synonyms = data2.get("InformationList", {}).get("Information", [{}])[0].get("Synonym", [])
            if synonyms:
                common = synonyms[0]
    except Exception:
        pass

    return IUPACResponse(smiles=smiles, iupac_name=iupac, common_name=common)


@router.post("/export-sdf")
async def export_sdf(req: dict):
    """Convert a list of compounds from a source directory to a combined SDF file.

    Body: { "names": ["mol1", "mol2"], "src_dir": "path" }
    Returns: { "sdf_path": "...", "count": N }
    """
    names: list[str] = req.get("names", [])
    src_dir: str = req.get("src_dir", "")
    if not src_dir or not os.path.isdir(src_dir):
        raise HTTPException(status_code=400, detail="Source directory not found")

    ob = get_obabel()
    env = get_obabel_env()

    out_dir = os.path.join(src_dir, "Export")
    os.makedirs(out_dir, exist_ok=True)
    sdf_path = os.path.join(out_dir, "compounds.sdf")

    count = 0
    temp_sdfs: list[str] = []

    search_names = names if names else [
        f.replace("_out.pdbqt", "").replace(".pdbqt", "").replace(".pdb", "")
        for f in os.listdir(src_dir)
        if f.endswith((".pdbqt", ".pdb"))
    ]

    for name in search_names:
        # Try multiple source formats
        for ext in ["_out.pdbqt", ".pdbqt", ".pdb", ".sdf", ".mol2"]:
            src_file = os.path.join(src_dir, f"{name}{ext}")
            if os.path.exists(src_file):
                temp_sdf = os.path.join(out_dir, f"{name}_temp.sdf")
                try:
                    subprocess.run(
                        [ob, src_file, "-O", temp_sdf],
                        env=env, check=True, timeout=30,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=_NO_WINDOW,
                    )
                    if os.path.exists(temp_sdf):
                        temp_sdfs.append(temp_sdf)
                        count += 1
                except Exception:
                    pass
                break

    # Combine all temp SDFs
    with open(sdf_path, "w") as out:
        for tf in temp_sdfs:
            with open(tf, "r") as f:
                out.write(f.read())
            os.remove(tf)

    if count == 0:
        raise HTTPException(status_code=404, detail="No compounds could be converted to SDF")

    return {"sdf_path": sdf_path, "count": count}
