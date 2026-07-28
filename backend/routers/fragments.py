"""
Fragment-Based Drug Design — BRICS / RECAP decomposition, fragment linking,
fragment growing, and curated fragment library browsing.
"""

import json
import os
from fastapi import APIRouter, HTTPException

from backend.models.schemas import (
    FragmentDecomposeRequest, FragmentDecomposeResponse,
    FragmentLinkRequest, FragmentLinkResponse,
    FragmentGrowRequest, FragmentGrowResponse,
    FragmentLibraryEntry, FragmentLibraryResponse,
)

router = APIRouter()

try:
    from rdkit import Chem
    from rdkit.Chem import BRICS, AllChem, Descriptors, rdMolDescriptors
    from rdkit.Chem.Scaffolds import MurckoScaffold
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

# Path to curated fragment library
_LIBRARY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "fragment_library.json")


def _check_rdkit():
    """Guard that raises if RDKit is unavailable."""
    if not RDKIT_AVAILABLE:
        raise HTTPException(status_code=503, detail="RDKit is not available on this system")


def _passes_rule_of_3(mol) -> bool:
    """Check Astex Rule-of-Three for fragment-likeness."""
    try:
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        hbd = rdMolDescriptors.CalcNumHBD(mol)
        hba = rdMolDescriptors.CalcNumHBA(mol)
        rotatable = rdMolDescriptors.CalcNumRotatableBonds(mol)
        return mw <= 300 and logp <= 3 and hbd <= 3 and hba <= 3 and rotatable <= 3
    except Exception:
        return False


@router.post("/decompose", response_model=FragmentDecomposeResponse)
async def decompose_molecule(req: FragmentDecomposeRequest):
    """Decompose a molecule into fragments using BRICS, RECAP, or Murcko scaffolding."""
    _check_rdkit()

    mol = Chem.MolFromSmiles(req.smiles)
    if mol is None:
        raise HTTPException(status_code=400, detail=f"Invalid SMILES: {req.smiles}")

    method = req.method.lower()
    fragments: list[str] = []

    if method == "brics":
        raw = BRICS.BRICSDecompose(mol)
        fragments = sorted(set(raw))
    elif method == "recap":
        # RECAP leaf decomposition via rdkit
        try:
            from rdkit.Chem import Recap
            tree = Recap.RecapDecompose(mol)
            leaves = tree.GetLeaves()
            fragments = sorted(leaves.keys()) if leaves else []
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"RECAP failed: {exc}")
    elif method == "murcko":
        try:
            core = MurckoScaffold.GetScaffoldForMol(mol)
            fw = MurckoScaffold.MakeScaffoldGeneric(core)
            fragments = [Chem.MolToSmiles(core), Chem.MolToSmiles(fw)]
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Murcko failed: {exc}")
    else:
        raise HTTPException(status_code=400, detail=f"Unknown method: {method}. Use 'brics', 'recap', or 'murcko'.")

    return FragmentDecomposeResponse(
        smiles=req.smiles,
        fragments=fragments,
        method=method,
        count=len(fragments),
        message=f"Decomposed into {len(fragments)} fragments via {method}"
    )


@router.post("/link", response_model=FragmentLinkResponse)
async def link_fragments(req: FragmentLinkRequest):
    """Link two or more fragments together using BRICS rules."""
    _check_rdkit()

    frag_mols = []
    for smi in req.fragments:
        m = Chem.MolFromSmiles(smi)
        if m is None:
            raise HTTPException(status_code=400, detail=f"Invalid fragment SMILES: {smi}")
        frag_mols.append(m)

    try:
        products_gen = BRICS.BRICSBuild(frag_mols)
        products: list[str] = []
        seen: set[str] = set()
        for p in products_gen:
            try:
                smi = Chem.MolToSmiles(p)
                if smi and smi not in seen:
                    seen.add(smi)
                    products.append(smi)
                    if len(products) >= req.max_results:
                        break
            except Exception:
                continue
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Fragment linking failed: {exc}")

    return FragmentLinkResponse(
        products=products,
        count=len(products),
        message=f"Generated {len(products)} linked products from {len(req.fragments)} fragments"
    )


@router.post("/grow", response_model=FragmentGrowResponse)
async def grow_fragment(req: FragmentGrowRequest):
    """Grow a core fragment by adding common substituents at attachment points."""
    _check_rdkit()

    core = Chem.MolFromSmiles(req.core)
    if core is None:
        raise HTTPException(status_code=400, detail=f"Invalid core SMILES: {req.core}")

    # Common growth substituents
    substituents = [
        "C", "CC", "CCC", "C(C)C", "C1CC1", "c1ccccc1", "c1ccncc1",
        "c1ccoc1", "c1ccsc1", "C(=O)O", "C(=O)N", "C(F)(F)F", "OC",
        "N", "NC", "N(C)C", "O", "F", "Cl", "Br", "C#N", "S(=O)(=O)N",
        "C(=O)NC", "c1cnc2ccccc2n1",
    ]

    grown: list[str] = []
    seen: set[str] = set()
    core_smi = Chem.MolToSmiles(core)

    # Decompose core with BRICS to find attachment points, then rebuild with substituents
    try:
        core_frags = list(BRICS.BRICSDecompose(core))
        if not core_frags:
            core_frags = [core_smi]

        for sub_smi in substituents:
            sub = Chem.MolFromSmiles(sub_smi)
            if sub is None:
                continue
            try:
                combo_mols = [core] + [sub]
                for p in BRICS.BRICSBuild([Chem.MolFromSmiles(f) for f in core_frags if Chem.MolFromSmiles(f)] + [sub]):
                    try:
                        result_smi = Chem.MolToSmiles(p)
                        if result_smi and result_smi != core_smi and result_smi not in seen:
                            seen.add(result_smi)
                            grown.append(result_smi)
                            if len(grown) >= req.max_results:
                                break
                    except Exception:
                        continue
            except Exception:
                continue
            if len(grown) >= req.max_results:
                break
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Fragment growing failed: {exc}")

    return FragmentGrowResponse(
        grown=grown,
        count=len(grown),
        message=f"Grew {len(grown)} analogs from core fragment"
    )


@router.get("/library", response_model=FragmentLibraryResponse)
async def get_fragment_library(category: str | None = None, limit: int = 200):
    """Return the curated fragment library, optionally filtered by category."""
    entries: list[FragmentLibraryEntry] = []

    # Try loading from JSON file
    if os.path.exists(_LIBRARY_PATH):
        try:
            with open(_LIBRARY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                entries.append(FragmentLibraryEntry(**item))
        except Exception:
            pass

    # If no file or empty, return a built-in minimal library
    if not entries:
        entries = _builtin_library()

    if category:
        entries = [e for e in entries if e.category.lower() == category.lower()]

    entries = entries[:limit]
    categories = sorted(set(e.category for e in entries if e.category))

    return FragmentLibraryResponse(
        fragments=entries,
        total=len(entries),
        categories=categories,
    )


def _builtin_library() -> list[FragmentLibraryEntry]:
    """A minimal built-in fragment library for when no JSON file is available."""
    frags = [
        ("c1ccccc1", "Benzene", "Aromatic"),
        ("c1ccncc1", "Pyridine", "Aromatic"),
        ("c1ccoc1", "Furan", "Aromatic"),
        ("c1ccsc1", "Thiophene", "Aromatic"),
        ("c1cc[nH]c1", "Pyrrole", "Aromatic"),
        ("c1cnc2ccccc2n1", "Quinazoline", "Aromatic"),
        ("c1ccc2[nH]ccc2c1", "Indole", "Aromatic"),
        ("c1ccc2ncccc2c1", "Quinoline", "Aromatic"),
        ("C1CCNCC1", "Piperidine", "Aliphatic"),
        ("C1CCNC1", "Pyrrolidine", "Aliphatic"),
        ("C1CNCCN1", "Piperazine", "Aliphatic"),
        ("C1CCOCC1", "Tetrahydropyran", "Aliphatic"),
        ("C1CCOC1", "Tetrahydrofuran", "Aliphatic"),
        ("C1CC1", "Cyclopropane", "Aliphatic"),
        ("C1CCC1", "Cyclobutane", "Aliphatic"),
        ("O=CO", "Formate", "Functional"),
        ("O=CN", "Formamide", "Functional"),
        ("S(=O)(=O)N", "Sulfonamide", "Functional"),
        ("c1nnn[nH]1", "Tetrazole", "Heterocyclic"),
        ("c1nonn1", "Furazan", "Heterocyclic"),
        ("c1nn[nH]n1", "1,2,4-Triazole", "Heterocyclic"),
        ("c1ccnnc1", "Pyridazine", "Heterocyclic"),
        ("c1cncnc1", "Pyrimidine", "Heterocyclic"),
        ("c1cnccn1", "Pyrazine", "Heterocyclic"),
        ("c1coc(=O)[nH]1", "Isoxazolinone", "Heterocyclic"),
        ("C(F)(F)F", "Trifluoromethyl", "Halogenated"),
        ("c1cc(F)ccc1", "Fluorobenzene", "Halogenated"),
        ("c1cc(Cl)ccc1", "Chlorobenzene", "Halogenated"),
    ]

    entries: list[FragmentLibraryEntry] = []
    for smi, name, cat in frags:
        mw = 0.0
        ro3 = False
        if RDKIT_AVAILABLE:
            mol = Chem.MolFromSmiles(smi)
            if mol:
                mw = round(Descriptors.MolWt(mol), 1)
                ro3 = _passes_rule_of_3(mol)
        entries.append(FragmentLibraryEntry(
            smiles=smi, name=name, category=cat, mw=mw, rule_of_3=ro3,
        ))
    return entries
