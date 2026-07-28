"""
Receptor Preparation — PDB → cleaned/stripped PDBQT for docking.

Steps:
1. Fetch PDB from RCSB if needed
2. Strip water (HOH), ions, and non-standard residues
3. Select a chain (optional)
4. Prepare a rigid-receptor PDBQT with Meeko
5. Fall back explicitly to Open Babel/Gasteiger preparation if Meeko fails
"""

import os
import subprocess
import requests
from fastapi import APIRouter, HTTPException

from backend.config import get_obabel, WORKSPACE_DIR
from backend.utils.pdb_integrity import analyze_pdb_integrity, compare_integrity
from backend.utils.paths import get_obabel_env
from backend.utils.pdbqt_utils import fix_receptor_pdbqt
from backend.utils.receptor_prep import prepare_receptor_pdbqt

router = APIRouter()
_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

try:
    from rdkit import Chem
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False


from backend.models.schemas import PrepareReceptorRequest, PrepareReceptorResponse, AnalyzePDBRequest


@router.post("/analyze")
async def analyze_pdb(req: AnalyzePDBRequest):
    """Analyze a PDB file — list chains, ligands, waters, and ions."""
    pdb_path = req.pdb_path
    pdb_id = req.pdb_id
    if pdb_id and not pdb_path:
        out_dir = os.path.join(WORKSPACE_DIR, "fetched_pdb")
        os.makedirs(out_dir, exist_ok=True)
        pdb_path = os.path.join(out_dir, f"{pdb_id.upper()}.pdb")
        if not os.path.exists(pdb_path):
            url = f"https://files.rcsb.org/download/{pdb_id.upper()}.pdb"
            r = requests.get(url, timeout=30)
            if r.status_code != 200:
                raise HTTPException(status_code=404, detail=f"PDB {pdb_id} not found on RCSB")
            with open(pdb_path, "w") as f:
                f.write(r.text)

    if not pdb_path:
        raise HTTPException(status_code=400, detail="No PDB path provided")
    if os.path.isdir(pdb_path):
        pdb_files = [f for f in os.listdir(pdb_path) if f.lower().endswith(('.pdb', '_clean.pdb'))]
        if pdb_files:
            raise HTTPException(
                status_code=400,
                detail=f"Path is a directory, not a file. Available PDB files: {', '.join(sorted(pdb_files))}",
            )
        raise HTTPException(status_code=400, detail="Path is a directory and contains no .pdb files")
    if not os.path.isfile(pdb_path):
        raise HTTPException(status_code=400, detail=f"PDB file not found: {os.path.basename(pdb_path)}")

    chains: set[str] = set()
    ligands: set[str] = set()
    water_count = 0
    ion_residues: set[str] = set()
    atom_count = 0
    known_ions = {"NA", "CL", "MG", "ZN", "CA", "FE", "MN", "K", "NI", "CU", "CO", "CD", "HG"}

    # Water residues: HOH/DOD = crystallographic; WAT = legacy PDB; SOL/TIP3/TP3 = MD outputs
    _WATER_RESIDUES = {"HOH", "WAT", "DOD", "SOL", "TIP3", "TP3"}

    with open(pdb_path, "r") as f:
        for line in f:
            if line.startswith(("ATOM  ", "HETATM")):
                atom_count += 1
                chain = line[21].strip()
                if chain:
                    chains.add(chain)
                resname = line[17:20].strip()
                if line.startswith("HETATM"):
                    if resname in _WATER_RESIDUES:
                        water_count += 1
                    elif resname in known_ions:
                        ion_residues.add(resname)
                    else:
                        ligands.add(resname)

    return {
        "pdb_path": pdb_path,
        "chains": sorted(chains),
        "ligands": sorted(ligands),
        "water_count": water_count,
        "ions": sorted(ion_residues),
        "atom_count": atom_count,
        "integrity": analyze_pdb_integrity(pdb_path),
    }


@router.post("/run", response_model=PrepareReceptorResponse)
async def prepare_receptor(req: PrepareReceptorRequest):
    """Clean a PDB and convert to PDBQT for docking."""
    pdb_path = req.pdb_path
    if not os.path.isfile(pdb_path):
        raise HTTPException(status_code=400, detail="PDB file not found")

    out_dir = os.path.join(WORKSPACE_DIR, "prepared_receptors")
    os.makedirs(out_dir, exist_ok=True)

    basename = os.path.splitext(os.path.basename(pdb_path))[0]
    clean_pdb = os.path.join(out_dir, f"{basename}_clean.pdb")
    output_pdbqt = os.path.join(out_dir, f"{basename}.pdbqt")

    # Step 1: Read and clean PDB
    kept_lines: list[str] = []
    removed_waters = 0
    removed_ligands = 0
    removed_ions = 0
    models_detected = 0
    first_model_complete = False
    processing_model = True
    kept_atom_records = 0
    kept_hetero_residues: set[str] = set()
    known_ions = {"NA", "CL", "MG", "ZN", "CA", "FE", "MN", "K", "NI", "CU", "CO", "CD", "HG"}

    with open(pdb_path, "r") as f:
        for line in f:
            tag = line[:6].strip()
            if tag == "MODEL":
                models_detected += 1
                processing_model = models_detected == 1
                continue

            if tag == "ENDMDL":
                if models_detected == 1 and processing_model:
                    first_model_complete = True
                    processing_model = False
                continue

            if first_model_complete and models_detected:
                if tag == "END":
                    kept_lines.append(line)
                continue

            if not processing_model:
                continue

            if not line.startswith(("ATOM  ", "HETATM", "TER", "END")):
                if line.startswith(("HEADER", "TITLE", "REMARK", "CRYST1")):
                    kept_lines.append(line)
                continue

            if line.startswith(("TER", "END")):
                kept_lines.append(line)
                continue

            resname = line[17:20].strip()
            chain = line[21].strip()

            # Filter by chain
            if req.keep_chain and chain != req.keep_chain:
                continue

            # Remove waters (HOH/WAT/DOD/SOL/TIP3/TP3)
            _WATER_RESIDUES = {"HOH", "WAT", "DOD", "SOL", "TIP3", "TP3"}
            if req.remove_water and resname in _WATER_RESIDUES:
                removed_waters += 1
                continue

            # Remove ligands
            if req.remove_ligands and line.startswith("HETATM") and resname not in known_ions and resname not in _WATER_RESIDUES:
                removed_ligands += 1
                continue

            # Remove ions
            if req.remove_ions and resname in known_ions:
                removed_ions += 1
                continue

            if line.startswith(("ATOM  ", "HETATM")):
                kept_atom_records += 1
                if line.startswith("HETATM") and resname not in _WATER_RESIDUES:
                    kept_hetero_residues.add(resname)

            kept_lines.append(line)

    if kept_atom_records == 0:
        raise HTTPException(status_code=400, detail="No atoms remained after cleaning — check filters")

    with open(clean_pdb, "w") as f:
        f.writelines(kept_lines)

    integrity = compare_integrity(pdb_path, clean_pdb)
    warnings: list[str] = []
    if models_detected > 1:
        warnings.append(f"Source contains {models_detected} MODEL sections; only the first model was prepared.")
    if req.keep_chain:
        warnings.append(f"Only chain {req.keep_chain} was retained for receptor preparation.")
    if removed_ligands:
        warnings.append(f"Removed {removed_ligands} ligand/cofactor atom records before docking receptor preparation.")
    if removed_ions:
        warnings.append(f"Removed {removed_ions} ion atom records; metal-dependent sites may require manual treatment.")
    if kept_hetero_residues:
        warnings.append(
            "Kept HETATM residue(s) in the clean PDB, but Meeko receptor PDBQT preparation may omit unsupported cofactors: "
            + ", ".join(sorted(kept_hetero_residues))
        )

    # Step 2: Convert to rigid receptor PDBQT. Prefer Meeko for protein receptors;
    # OpenBabel is retained only as a compatibility fallback.
    prep_engine = "meeko"
    try:
        prep_report = prepare_receptor_pdbqt(clean_pdb, output_pdbqt)
        if prep_report["skipped_residues"]:
            warnings.append("Meeko skipped unsupported residues: " + ", ".join(prep_report["skipped_residues"]))
    except Exception as meeko_error:
        warnings.append(f"Meeko receptor preparation failed; fell back to OpenBabel: {meeko_error}")
        prep_engine = "openbabel_fallback"

        ob = get_obabel()
        env = get_obabel_env()

        cmd = [ob, clean_pdb, "-O", output_pdbqt, "--partialcharge", "gasteiger", "-xr"]
        if req.add_hydrogens:
            cmd.insert(2, "-h")

        try:
            subprocess.run(
                cmd, env=env, check=True, timeout=120,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=_NO_WINDOW,
            )
            fix_receptor_pdbqt(output_pdbqt)
        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=500, detail=f"OpenBabel conversion failed after Meeko failed: {e}")

    if not os.path.isfile(output_pdbqt):
        raise HTTPException(status_code=500, detail="PDBQT output not created")

    return PrepareReceptorResponse(
        output_path=output_pdbqt,
        clean_pdb_path=clean_pdb,
        removed_waters=removed_waters,
        removed_ligands=removed_ligands,
        removed_ions=removed_ions,
        message=(
            f"Receptor prepared with {prep_engine}: removed {removed_waters} waters, {removed_ligands} ligand atoms, {removed_ions} ions"
            + (f", kept first of {models_detected} models" if models_detected > 1 else "")
        ),
        integrity=integrity,
        prep_engine=prep_engine,
        warnings=warnings,
    )
