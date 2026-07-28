"""
Pharmacophore Modeling & Screening Router
──────────────────────────────────────────
Endpoints for pharmacophore feature extraction, visualization,
library screening (2D fingerprint or 3D alignment), and
model save/load as JSON.
"""

import os
import json
import glob
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException

from backend.models.schemas import (
    PharmGenerateRequest, PharmGenerateResponse, PharmacophoreFeature,
    PharmScreenRequest, PharmScreenResponse, PharmScreenHit,
    PharmSaveRequest, PharmSaveResponse, PharmLoadResponse,
)
from backend.services.job_manager import JobCancelled, job_manager, job_progress_message

router = APIRouter()
log = logging.getLogger(__name__)

# ── Optional dependency guards ──
try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Draw, rdMolChemicalFeatures, rdMolDescriptors
    from rdkit.Chem.Pharm2D import Gobbi_Pharm2D, Generate
    from rdkit import RDConfig
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

# Conformer embedding seed. 3D alignment scores are only reproducible between
# runs if the distance-geometry search starts from a fixed seed; the same value
# is used by the batch, minimization, and pipeline routes.
EMBED_SEED = 42


def _embed_params():
    """ETKDGv3 parameters with the deterministic embedding seed applied."""
    params = AllChem.ETKDGv3()
    params.randomSeed = EMBED_SEED
    return params


# Pharmacophore feature → color mapping
FEATURE_COLORS = {
    "Donor": {"type": "HBD", "color": "#3B82F6"},           # blue
    "Acceptor": {"type": "HBA", "color": "#EF4444"},        # red
    "Hydrophobe": {"type": "Hydrophobic", "color": "#EAB308"},  # yellow
    "Aromatic": {"type": "Aromatic", "color": "#A855F7"},    # purple
    "PosIonizable": {"type": "PosIonizable", "color": "#22C55E"},  # green
    "NegIonizable": {"type": "NegIonizable", "color": "#F97316"},  # orange
    "LumpedHydrophobe": {"type": "Hydrophobic", "color": "#EAB308"},
}


def _get_feature_factory():
    """Get RDKit chemical feature factory."""
    fdef_path = os.path.join(RDConfig.RDDataDir, "BaseFeatures.fdef")
    return rdMolChemicalFeatures.BuildFeatureFactory(fdef_path)


def _extract_features(mol, include_3d: bool = False) -> list[PharmacophoreFeature]:
    """Extract pharmacophore features from an RDKit mol object."""
    factory = _get_feature_factory()
    feats = factory.GetFeaturesForMol(mol)
    result: list[PharmacophoreFeature] = []
    for feat in feats:
        family = feat.GetFamily()
        mapping = FEATURE_COLORS.get(family)
        if not mapping:
            continue
        atoms = list(feat.GetAtomIds())
        pos = feat.GetPos() if include_3d and mol.GetNumConformers() > 0 else None
        result.append(PharmacophoreFeature(
            type=mapping["type"],
            atoms=atoms,
            x=round(pos.x, 3) if pos else None,
            y=round(pos.y, 3) if pos else None,
            z=round(pos.z, 3) if pos else None,
        ))
    return result


def _generate_svg_with_features(mol, features: list[PharmacophoreFeature]) -> str:
    """Generate 2D SVG of the molecule with colored pharmacophore circles overlaid."""
    from rdkit.Chem import Draw
    from io import BytesIO

    AllChem.Compute2DCoords(mol)
    drawer = Draw.MolDraw2DSVG(450, 350)

    # Highlight atoms by feature type
    atom_colors: dict[int, tuple] = {}
    highlight_atoms: list[int] = []
    type_to_rgb = {
        "HBD": (0.23, 0.51, 0.96),
        "HBA": (0.94, 0.27, 0.27),
        "Hydrophobic": (0.92, 0.70, 0.03),
        "Aromatic": (0.66, 0.33, 0.97),
        "PosIonizable": (0.13, 0.77, 0.37),
        "NegIonizable": (0.98, 0.45, 0.09),
    }

    for feat in features:
        rgb = type_to_rgb.get(feat.type, (0.5, 0.5, 0.5))
        for a in feat.atoms:
            if a < mol.GetNumAtoms():
                atom_colors[a] = rgb
                highlight_atoms.append(a)

    drawer.DrawMolecule(
        mol,
        highlightAtoms=highlight_atoms,
        highlightAtomColors=atom_colors,
        highlightBonds=[],
    )
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


def _read_library(source: str) -> list[tuple[str, str]]:
    """
    Read compound library from .smi/.txt, .sdf, or directory of .mol files.
    Returns list of (name, smiles) tuples.
    """
    compounds: list[tuple[str, str]] = []
    source_path = Path(source)

    if source_path.is_dir():
        # Directory of .mol / .sdf files
        for fp in sorted(glob.glob(str(source_path / "*.mol")) + glob.glob(str(source_path / "*.sdf"))):
            try:
                suppl = Chem.SDMolSupplier(fp, removeHs=True)
                for mol in suppl:
                    if mol:
                        name = mol.GetProp("_Name") if mol.HasProp("_Name") else Path(fp).stem
                        smi = Chem.MolToSmiles(mol)
                        compounds.append((name, smi))
            except Exception:
                continue
    elif source_path.suffix.lower() == ".sdf":
        suppl = Chem.SDMolSupplier(str(source_path), removeHs=True)
        for mol in suppl:
            if mol:
                name = mol.GetProp("_Name") if mol.HasProp("_Name") else "compound"
                smi = Chem.MolToSmiles(mol)
                compounds.append((name, smi))
    else:
        # .smi or .txt — one SMILES per line, optional tab-separated name
        with open(str(source_path), "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                smi = parts[0]
                name = parts[1] if len(parts) > 1 else smi[:30]
                compounds.append((name, smi))

    return compounds


# ──────────────────────────── Endpoints ────────────────────────────

@router.post("/generate", response_model=PharmGenerateResponse)
async def generate_pharmacophore(req: PharmGenerateRequest):
    """Extract pharmacophore features from a SMILES string and return SVG overlay."""
    if not RDKIT_AVAILABLE:
        raise HTTPException(503, "RDKit is not installed — pharmacophore generation unavailable")

    mol = Chem.MolFromSmiles(req.smiles)
    if mol is None:
        raise HTTPException(400, f"Invalid SMILES: {req.smiles}")

    # Generate 3D conformer if requested
    if req.include_3d:
        mol_3d = Chem.AddHs(mol)
        result = AllChem.EmbedMolecule(mol_3d, _embed_params())
        if result == 0:
            AllChem.MMFFOptimizeMolecule(mol_3d, maxIters=200)
            features = _extract_features(mol_3d, include_3d=True)
        else:
            log.warning("3D embedding failed, falling back to 2D features")
            features = _extract_features(mol, include_3d=False)
    else:
        features = _extract_features(mol, include_3d=False)

    svg = _generate_svg_with_features(mol, features)

    # Count features by type
    counts: dict[str, int] = {}
    for f in features:
        counts[f.type] = counts.get(f.type, 0) + 1

    return PharmGenerateResponse(
        smiles=req.smiles,
        features=features,
        svg=svg,
        feature_counts=counts,
        message=f"Extracted {len(features)} pharmacophore features",
    )


@router.post("/screen", response_model=PharmScreenResponse)
async def screen_library(req: PharmScreenRequest):
    """Screen a compound library against a reference pharmacophore."""
    if not RDKIT_AVAILABLE:
        raise HTTPException(503, "RDKit is not installed — pharmacophore screening unavailable")

    ref_mol = Chem.MolFromSmiles(req.reference_smiles)
    if ref_mol is None:
        raise HTTPException(400, f"Invalid reference SMILES: {req.reference_smiles}")

    if not os.path.exists(req.library_source):
        raise HTTPException(404, f"Library source not found: {req.library_source}")

    compounds = _read_library(req.library_source)
    if not compounds:
        raise HTTPException(400, "No valid compounds found in library source")

    warning = None
    if req.mode == "3d" and len(compounds) > 1000:
        warning = f"Large library ({len(compounds)} compounds) — 3D screening may be slow"

    hits: list[PharmScreenHit] = []
    job = await job_manager.begin("Pharmacophore Screening", total=len(compounds), message="Preparing pharmacophore screen")

    try:
        if req.mode == "2d":
            # 2D pharmacophore fingerprint screening
            sig_factory = Gobbi_Pharm2D.factory
            try:
                ref_fp = Generate.Gen2DFingerprint(ref_mol, sig_factory)
            except Exception as e:
                raise HTTPException(500, f"Failed to generate reference fingerprint: {e}")

            last_done: str | None = None
            for idx, (name, smi) in enumerate(compounds):
                await job_manager.checkpoint(
                    job.id,
                    current=idx,
                    total=len(compounds),
                    progress=int((idx / max(len(compounds), 1)) * 100),
                    message=job_progress_message("2D screening compound", name, idx, len(compounds), last_done),
                )
                hit = False
                try:
                    mol = Chem.MolFromSmiles(smi)
                    if mol is None:
                        continue
                    fp = Generate.Gen2DFingerprint(mol, sig_factory)
                    # Dice similarity on pharmacophore fingerprints
                    on_bits_ref = set(ref_fp.GetOnBits())
                    on_bits_mol = set(fp.GetOnBits())
                    if not on_bits_ref and not on_bits_mol:
                        sim = 1.0
                    elif not on_bits_ref or not on_bits_mol:
                        sim = 0.0
                    else:
                        intersection = len(on_bits_ref & on_bits_mol)
                        sim = (2.0 * intersection) / (len(on_bits_ref) + len(on_bits_mol))

                    if sim >= req.threshold:
                        hits.append(PharmScreenHit(
                            name=name, smiles=smi, score=round(sim, 4),
                            matched_features=len(on_bits_ref & on_bits_mol),
                        ))
                        hit = True
                except Exception:
                    last_done = f"{name} failed"
                    continue
                last_done = f"{name} hit" if hit else name

        else:
            # 3D alignment-based scoring
            await job_manager.checkpoint(job.id, progress=3, message="Preparing 3D reference pharmacophore")
            ref_mol_3d = Chem.AddHs(ref_mol)
            if AllChem.EmbedMolecule(ref_mol_3d, _embed_params()) != 0:
                raise HTTPException(500, "Failed to generate 3D conformer for reference molecule")
            AllChem.MMFFOptimizeMolecule(ref_mol_3d, maxIters=200)

            ref_features = _extract_features(ref_mol_3d, include_3d=True)
            ref_feat_count = len(ref_features)

            last_done: str | None = None
            for idx, (name, smi) in enumerate(compounds):
                await job_manager.checkpoint(
                    job.id,
                    current=idx,
                    total=len(compounds),
                    progress=int((idx / max(len(compounds), 1)) * 100),
                    message=job_progress_message("3D aligning compound", name, idx, len(compounds), last_done),
                )
                hit = False
                try:
                    mol = Chem.MolFromSmiles(smi)
                    if mol is None:
                        continue
                    mol_3d = Chem.AddHs(mol)
                    if AllChem.EmbedMolecule(mol_3d, _embed_params()) != 0:
                        continue
                    AllChem.MMFFOptimizeMolecule(mol_3d, maxIters=200)

                    # Compute O3A alignment score
                    try:
                        pyO3A = AllChem.GetO3A(mol_3d, ref_mol_3d)
                        if pyO3A is None:
                            continue
                        score = pyO3A.Score()
                        pyO3A.Align()
                    except Exception:
                        score = 0.0

                    mol_features = _extract_features(mol_3d, include_3d=True)
                    matched = sum(1 for mf in mol_features if any(
                        mf.type == rf.type for rf in ref_features
                    ))

                    # O3A scores are positive: higher = better overlap (Tosco et al. 2011)
                    norm_score = min(1.0, abs(score) / 100.0) if score != 0 else 0.0

                    if norm_score >= req.threshold or matched / max(ref_feat_count, 1) >= req.threshold:
                        hits.append(PharmScreenHit(
                            name=name, smiles=smi,
                            score=round(norm_score, 4),
                            matched_features=matched,
                        ))
                        hit = True
                except Exception:
                    last_done = f"{name} failed"
                    continue
                last_done = f"{name} hit" if hit else name

        hits.sort(key=lambda h: h.score, reverse=True)
        await job_manager.finish(job.id, "completed", f"Pharmacophore screening complete: {len(hits)} hits", progress=100)
        return PharmScreenResponse(
            hits=hits,
            total_screened=len(compounds),
            mode=req.mode,
            warning=warning,
            message=f"Found {len(hits)} hits from {len(compounds)} compounds",
        )
    except JobCancelled:
        hits.sort(key=lambda h: h.score, reverse=True)
        await job_manager.finish(job.id, "cancelled", f"Pharmacophore screening cancelled: {len(hits)} hits")
        return PharmScreenResponse(
            hits=hits,
            total_screened=len(compounds),
            mode=req.mode,
            warning=warning,
            message="Pharmacophore screening cancelled",
        )
    except Exception as exc:
        await job_manager.finish(job.id, "error", f"Pharmacophore screening failed: {exc}")
        raise


@router.post("/save", response_model=PharmSaveResponse)
async def save_pharmacophore(req: PharmSaveRequest):
    """Save a pharmacophore model as JSON."""
    os.makedirs(req.output_dir, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in req.name)
    path = os.path.join(req.output_dir, f"{safe_name}.pharm.json")

    model = {
        "name": req.name,
        "reference_smiles": req.reference_smiles,
        "features": [f.model_dump() for f in req.features],
    }

    with open(path, "w") as f:
        json.dump(model, f, indent=2)

    return PharmSaveResponse(path=path, message=f"Pharmacophore model saved to {path}")


@router.get("/load", response_model=PharmLoadResponse)
async def load_pharmacophore(path: str):
    """Load a pharmacophore model from a JSON file."""
    if not os.path.isfile(path):
        raise HTTPException(404, f"Pharmacophore model not found: {path}")

    with open(path, "r") as f:
        data = json.load(f)

    features = [PharmacophoreFeature(**fd) for fd in data.get("features", [])]

    return PharmLoadResponse(
        name=data.get("name", "Unknown"),
        reference_smiles=data.get("reference_smiles", ""),
        features=features,
        path=path,
    )
