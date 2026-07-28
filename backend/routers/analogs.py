"""
Analog Generator — BRICS fragmentation, bioisosteric replacement,
and single-atom walk enumeration to expand chemical diversity.
"""

import os
from fastapi import APIRouter, HTTPException

from backend.models.schemas import AnalogRequest, AnalogCompound, AnalogResponse

router = APIRouter()

try:
    from rdkit import Chem, DataStructs
    from rdkit.Chem import BRICS, AllChem, Descriptors, rdMolDescriptors
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False


def _tanimoto(mol1, mol2) -> float | None:
    """Tanimoto similarity between two molecules."""
    if mol1 is None or mol2 is None:
        return None
    try:
        fp1 = AllChem.GetMorganFingerprintAsBitVect(mol1, 2, nBits=2048)
        fp2 = AllChem.GetMorganFingerprintAsBitVect(mol2, 2, nBits=2048)
        return round(DataStructs.TanimotoSimilarity(fp1, fp2), 3)
    except Exception:
        return None


BIOISOSTERE_RULES: list[tuple[str, str]] = [
    ("[OX2H1]", "[NX3H2]"),                    # Hydroxyl → primary amine
    ("[OX2H1]", "[SX2H1]"),                    # Hydroxyl → thiol
    ("[OX2H1]", "[#9]"),                       # Hydroxyl → fluorine (metabolic block)
    ("[NX3;H2;!$(NC=O)]", "[OX2H1]"),          # Primary amine (not amide) → hydroxyl
    ("[#9]", "[#17]"),                          # Fluorine → chlorine
    ("[#17]", "[#9]"),                          # Chlorine → fluorine
    ("[CX3](=O)[OX2H1,OX1-]", "c1nnn[nH]1"),  # Carboxylic acid/carboxylate → tetrazole
    ("c1ccccc1", "c1ccncc1"),                  # Phenyl → pyridine
    ("c1ccccc1", "c1ccoc1"),                   # Phenyl → furan
    ("c1ccccc1", "c1ccsc1"),                   # Phenyl → thiophene
    ("[CX3](=O)[OX2][#6]", "C(=O)N"),         # Ester → amide
    ("[OX2H1;!$(OC=O)]", "OC"),                # Alcohol/phenol → methoxy (excludes carboxylic acid OH)
]

# Per-method Tanimoto similarity floors (Morgan/ECFP4, radius 2, 2048 bits)
_MIN_ANALOG_SIMILARITY = {
    "brics": 0.2,          # Scaffold hops are inherently dissimilar; MW/logP filter provides primary safety
    "bioisostere": 0.3,    # Accommodates large-group swaps on fragments (Patani & LaVoie 1996)
    "walk": 0.5,           # Single-atom swaps preserve most fingerprint bits
}


def _brics_analogs(mol, max_results: int) -> list[str]:
    """Generate analogs via BRICS decomposition and recombination."""
    try:
        frags = list(BRICS.BRICSDecompose(mol))
        if len(frags) < 2:
            return []
        frag_mols = [Chem.MolFromSmiles(f) for f in frags if Chem.MolFromSmiles(f)]
        if not frag_mols:
            return []
        products = BRICS.BRICSBuild(frag_mols)
        parent_smi = Chem.MolToSmiles(mol)
        result: list[str] = []
        for p in products:
            try:
                smi = Chem.MolToSmiles(p)
                if smi and smi != parent_smi:
                    # Basic lead-like bounds filter for BRICS products
                    mw = Descriptors.MolWt(p)
                    logp = Descriptors.MolLogP(p)
                    if 100 < mw < 800 and -2 < logp < 7:
                        result.append(smi)
                        if len(result) >= max_results:
                            break
            except Exception:
                continue
        return result
    except Exception:
        return []


def _bioisostere_analogs(smi: str, max_results: int) -> list[str]:
    """Replace known functional groups with bioisosteric equivalents using SMARTS."""
    results: list[str] = []
    mol = Chem.MolFromSmiles(smi)
    if mol is None:
        return results
    for pattern_smarts, repl_smarts in BIOISOSTERE_RULES:
        pattern = Chem.MolFromSmarts(pattern_smarts)
        repl = Chem.MolFromSmiles(repl_smarts)
        if pattern is None or repl is None:
            continue
        if mol.HasSubstructMatch(pattern):
            try:
                products = AllChem.ReplaceSubstructs(mol, pattern, repl)
                for p in products:
                    try:
                        Chem.SanitizeMol(p)
                        canonical = Chem.MolToSmiles(p)
                        if canonical != smi and canonical not in results:
                            results.append(canonical)
                            if len(results) >= max_results:
                                return results
                    except Exception:
                        continue
            except Exception:
                continue
    return results


def _enumerate_walk(mol, max_results: int) -> list[str]:
    """Single-atom mutation: swap each heavy atom with C, N, O, S."""
    parent_smi = Chem.MolToSmiles(mol)
    results: list[str] = []
    swap_atoms = [6, 7, 8, 16]

    rw = Chem.RWMol(mol)
    for idx in range(rw.GetNumAtoms()):
        original = rw.GetAtomWithIdx(idx).GetAtomicNum()
        if original == 1:
            continue
        for new_z in swap_atoms:
            if new_z == original:
                continue
            rw2 = Chem.RWMol(mol)
            rw2.GetAtomWithIdx(idx).SetAtomicNum(new_z)
            try:
                Chem.SanitizeMol(rw2)
                smi = Chem.MolToSmiles(rw2)
                if smi != parent_smi and smi not in results:
                    results.append(smi)
                    if len(results) >= max_results:
                        return results
            except Exception:
                continue
    return results


@router.post("/generate", response_model=AnalogResponse)
async def generate_analogs(req: AnalogRequest):
    """Generate analogs using multiple enumeration strategies."""
    if not RDKIT_AVAILABLE:
        raise HTTPException(status_code=500, detail="RDKit not installed")

    # Use universal resolver to support SMILES, InChI, names, CAS, MOL blocks
    from backend.routers.resolve import resolve_to_smiles
    try:
        resolved_smiles, input_type, resolved_name = resolve_to_smiles(req.smiles)
        mol = Chem.MolFromSmiles(resolved_smiles)
    except Exception:
        mol = None
    if mol is None:
        raise HTTPException(status_code=400, detail="Could not resolve molecule — try SMILES, InChI, compound name, or CAS number")

    max_per = req.max_analogs if req.max_analogs else 20
    method = req.method if req.method else "fragment"

    all_analogs: list[AnalogCompound] = []

    if method in ("fragment", "all"):
        brics_floor = _MIN_ANALOG_SIMILARITY["brics"]
        for smi in _brics_analogs(mol, max_per):
            m2 = Chem.MolFromSmiles(smi)
            sim = _tanimoto(mol, m2)
            if sim is not None and sim < brics_floor:
                continue
            mw = round(Descriptors.MolWt(m2), 2) if m2 else None
            all_analogs.append(AnalogCompound(
                name=f"brics_{len(all_analogs)}",
                smiles=smi,
                similarity=sim,
                mw=mw,
            ))

    if method in ("bioisostere", "all"):
        bioiso_floor = _MIN_ANALOG_SIMILARITY["bioisostere"]
        for smi in _bioisostere_analogs(req.smiles, max_per):
            if not any(a.smiles == smi for a in all_analogs):
                m2 = Chem.MolFromSmiles(smi)
                sim = _tanimoto(mol, m2)
                if sim is not None and sim < bioiso_floor:
                    continue
                mw = round(Descriptors.MolWt(m2), 2) if m2 else None
                all_analogs.append(AnalogCompound(
                    name=f"bioiso_{len(all_analogs)}",
                    smiles=smi,
                    similarity=sim,
                    mw=mw,
                ))

    if method in ("walk", "all"):
        walk_floor = _MIN_ANALOG_SIMILARITY["walk"]
        for smi in _enumerate_walk(mol, max_per):
            if not any(a.smiles == smi for a in all_analogs):
                m2 = Chem.MolFromSmiles(smi)
                sim = _tanimoto(mol, m2)
                if sim is not None and sim < walk_floor:
                    continue
                mw = round(Descriptors.MolWt(m2), 2) if m2 else None
                all_analogs.append(AnalogCompound(
                    name=f"walk_{len(all_analogs)}",
                    smiles=smi,
                    similarity=sim,
                    mw=mw,
                ))

    unique = all_analogs[:max_per]

    return AnalogResponse(
        parent_smiles=req.smiles,
        analogs=unique,
        count=len(unique),
    )
