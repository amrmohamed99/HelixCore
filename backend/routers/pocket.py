"""
Pocket Analyzer router — binding site residues & grid box calculation.
Ported from drug_tool.py: _t_pocket, _t_pocket_grid.
"""

import os
from fastapi import APIRouter, HTTPException

from backend.models.schemas import (
    PocketAnalysisRequest,
    PocketAnalysisResponse,
    GridBox,
    GridBoxResponse,
    DruggabilityRequest,
    DruggabilityResponse,
)
from backend.utils.pdbqt_utils import parse_pdb_atoms

router = APIRouter()


@router.post("/analyze", response_model=PocketAnalysisResponse)
async def analyze_pocket(req: PocketAnalysisRequest):
    """Find residues within 5 Å of a ligand in a protein-ligand complex."""
    if not os.path.isfile(req.pdb_path):
        raise HTTPException(status_code=400, detail="PDB file not found")

    protein_atoms, ligand_atoms = parse_pdb_atoms(
        req.pdb_path,
        req.ligand_name.upper(),
        lig_chain=req.ligand_chain,
        lig_resseq=req.ligand_resseq,
        lig_icode=req.ligand_icode,
    )

    if not ligand_atoms:
        raise HTTPException(
            status_code=400,
            detail="No ligand atoms found matching criteria",
        )

    cutoff_sq = 25.0  # 5 Å squared
    binding_residues: set[str] = set()

    for pa in protein_atoms:
        px, py, pz = pa["coords"]
        for lx, ly, lz in ligand_atoms:
            if (px - lx) ** 2 + (py - ly) ** 2 + (pz - lz) ** 2 <= cutoff_sq:
                binding_residues.add(pa["res"])
                break

    sorted_res = sorted(
        list(binding_residues),
        key=lambda x: int(x.split()[1]) if x.split()[1].isdigit() else 0,
    )

    return PocketAnalysisResponse(
        residues=sorted_res,
        ligand_atom_count=len(ligand_atoms),
        contact_count=len(sorted_res),
        selected_ligand={
            "name": req.ligand_name.upper(),
            "chain": req.ligand_chain,
            "resseq": req.ligand_resseq,
            "icode": req.ligand_icode,
        },
    )


@router.post("/grid", response_model=GridBoxResponse)
async def calculate_grid(req: PocketAnalysisRequest):
    """Calculate a grid box around the binding pocket (< 5 Å from ligand)."""
    if not os.path.isfile(req.pdb_path):
        raise HTTPException(status_code=400, detail="PDB file not found")

    protein_atoms, ligand_atoms = parse_pdb_atoms(
        req.pdb_path,
        req.ligand_name.upper(),
        lig_chain=req.ligand_chain,
        lig_resseq=req.ligand_resseq,
        lig_icode=req.ligand_icode,
    )

    if not ligand_atoms:
        raise HTTPException(
            status_code=400, detail="No ligand atoms found"
        )

    cutoff_sq = 25.0
    pocket_coords: list[tuple[float, float, float]] = []

    for pa in protein_atoms:
        px, py, pz = pa["coords"]
        for lx, ly, lz in ligand_atoms:
            if (px - lx) ** 2 + (py - ly) ** 2 + (pz - lz) ** 2 <= cutoff_sq:
                pocket_coords.append((px, py, pz))
                break

    if not pocket_coords:
        pocket_coords = list(ligand_atoms)

    xs = [c[0] for c in pocket_coords]
    ys = [c[1] for c in pocket_coords]
    zs = [c[2] for c in pocket_coords]

    raw_sizes = {
        "x": (max(xs) - min(xs)) + req.padding,
        "y": (max(ys) - min(ys)) + req.padding,
        "z": (max(zs) - min(zs)) + req.padding,
    }
    oversized = {axis: round(size, 3) for axis, size in raw_sizes.items() if size > 126.0}
    if oversized:
        dimensions = ", ".join(f"{axis}={size} Å" for axis, size in oversized.items())
        raise HTTPException(
            status_code=400,
            detail=f"Pocket grid exceeds AutoDock Vina's 126 Å maximum ({dimensions})",
        )

    grid = GridBox(
        center_x=round((min(xs) + max(xs)) / 2, 3),
        center_y=round((min(ys) + max(ys)) / 2, 3),
        center_z=round((min(zs) + max(zs)) / 2, 3),
        size_x=round(raw_sizes["x"], 3),
        size_y=round(raw_sizes["y"], 3),
        size_z=round(raw_sizes["z"], 3),
    )

    # Save grid file
    out_path = os.path.join(os.path.dirname(req.pdb_path), "grid.txt")
    with open(out_path, "w") as f:
        f.write(f"center_x = {grid.center_x}\n")
        f.write(f"center_y = {grid.center_y}\n")
        f.write(f"center_z = {grid.center_z}\n")
        f.write(f"size_x = {grid.size_x}\n")
        f.write(f"size_y = {grid.size_y}\n")
        f.write(f"size_z = {grid.size_z}\n")

    return GridBoxResponse(
        grid=grid,
        output_path=out_path,
        ligand_atom_count=len(ligand_atoms),
        selected_ligand={
            "name": req.ligand_name.upper(),
            "chain": req.ligand_chain,
            "resseq": req.ligand_resseq,
            "icode": req.ligand_icode,
        },
    )


HYDROPHOBIC_RESIDUES = {"ALA", "VAL", "LEU", "ILE", "PHE", "TRP", "MET", "PRO"}


@router.post("/druggability", response_model=DruggabilityResponse)
async def assess_druggability(req: DruggabilityRequest):
    """Heuristic druggability assessment of a binding pocket."""
    if not os.path.isfile(req.pdb_path):
        raise HTTPException(status_code=400, detail="PDB file not found")

    protein_atoms, ligand_atoms = parse_pdb_atoms(
        req.pdb_path,
        req.ligand_name.upper() if req.ligand_name else "",
        lig_chain=req.ligand_chain,
        lig_resseq=req.ligand_resseq,
        lig_icode=req.ligand_icode,
    )

    if not ligand_atoms and not protein_atoms:
        raise HTTPException(status_code=400, detail="No atoms found")

    cutoff_sq = 25.0
    pocket_residues: set[str] = set()
    pocket_coords: list[tuple[float, float, float]] = []

    if ligand_atoms:
        for pa in protein_atoms:
            px, py, pz = pa["coords"]
            for lx, ly, lz in ligand_atoms:
                if (px - lx) ** 2 + (py - ly) ** 2 + (pz - lz) ** 2 <= cutoff_sq:
                    pocket_residues.add(pa["res"])
                    pocket_coords.append((px, py, pz))
                    break

    residue_count = len(pocket_residues)
    notes: list[str] = []

    hydrophobic_count = sum(
        1 for r in pocket_residues if r.split()[0] in HYDROPHOBIC_RESIDUES
    )
    hydrophobicity_ratio = round(hydrophobic_count / residue_count, 2) if residue_count > 0 else 0

    volume = None
    if pocket_coords:
        xs = [c[0] for c in pocket_coords]
        ys = [c[1] for c in pocket_coords]
        zs = [c[2] for c in pocket_coords]
        dx = max(xs) - min(xs)
        dy = max(ys) - min(ys)
        dz = max(zs) - min(zs)
        volume = round(dx * dy * dz, 1)
        notes.append(f"Bounding box: {round(dx,1)} × {round(dy,1)} × {round(dz,1)} Å")

    # Druggability assessment: 3-factor scoring (Halgren 2009, Cheng et al. 2007)
    # Uses residue count, hydrophobicity, and volume as independent predictors
    score = 0
    if residue_count >= 10:
        score += 1
    if hydrophobicity_ratio >= 0.3:
        score += 1
    if volume and volume >= 300:
        score += 1

    druggable = score >= 2
    confidence = "high" if score == 3 else "medium" if score == 2 else "low"

    if residue_count < 8:
        notes.append("Very small pocket — may be a shallow groove")
    if hydrophobicity_ratio >= 0.5:
        notes.append("Highly hydrophobic pocket — favorable for small-molecule binding")

    return DruggabilityResponse(
        volume=volume,
        hydrophobicity_ratio=hydrophobicity_ratio,
        residue_count=residue_count,
        druggable=druggable,
        confidence=confidence,
        notes=notes,
    )
