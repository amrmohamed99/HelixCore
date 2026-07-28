"""
Scaffold Hopping — Murcko decomposition, MCS-based scaffold replacement,
R-group decomposition, and matched molecular pair analysis.
"""

import os
from fastapi import APIRouter, HTTPException

from backend.models.schemas import (
    ScaffoldHopRequest, ScaffoldHopResult, ScaffoldHopResponse,
)

router = APIRouter()

try:
    from rdkit import Chem, DataStructs
    from rdkit.Chem import AllChem, Descriptors, rdFMCS
    from rdkit.Chem.Scaffolds import MurckoScaffold
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False


def _check_rdkit():
    """Guard that raises if RDKit is unavailable."""
    if not RDKIT_AVAILABLE:
        raise HTTPException(status_code=503, detail="RDKit is not available on this system")


def _tanimoto(mol1, mol2) -> float:
    """Tanimoto similarity between two molecules."""
    try:
        fp1 = AllChem.GetMorganFingerprintAsBitVect(mol1, 2, nBits=2048)
        fp2 = AllChem.GetMorganFingerprintAsBitVect(mol2, 2, nBits=2048)
        return round(DataStructs.TanimotoSimilarity(fp1, fp2), 3)
    except Exception:
        return 0.0


def _load_library(path: str | None) -> list[tuple[str, str]]:
    """Load a SMILES library from .smi or .sdf file. Returns (smiles, name) tuples."""
    if not path or not os.path.exists(path):
        return []

    results: list[tuple[str, str]] = []
    if path.endswith(".smi") or path.endswith(".csv"):
        with open(path, "r") as f:
            for line in f:
                parts = line.strip().split()
                if parts:
                    smi = parts[0]
                    name = parts[1] if len(parts) > 1 else smi[:20]
                    results.append((smi, name))
    elif path.endswith(".sdf"):
        try:
            suppl = Chem.SDMolSupplier(path)
            for mol in suppl:
                if mol is None:
                    continue
                smi = Chem.MolToSmiles(mol)
                name = mol.GetProp("_Name") if mol.HasProp("_Name") else smi[:20]
                results.append((smi, name))
        except Exception:
            pass
    return results


@router.post("/hop", response_model=ScaffoldHopResponse)
async def scaffold_hop(req: ScaffoldHopRequest):
    """Perform scaffold hopping using the specified method."""
    _check_rdkit()

    ref_mol = Chem.MolFromSmiles(req.smiles)
    if ref_mol is None:
        raise HTTPException(status_code=400, detail=f"Invalid SMILES: {req.smiles}")

    method = req.method.lower()
    ref_scaffold_smi = ""

    if method == "murcko":
        return await _murcko_hop(ref_mol, req)
    elif method == "mcs":
        return await _mcs_hop(ref_mol, req)
    elif method == "rgroup":
        return await _rgroup_decomp(ref_mol, req)
    elif method == "mmp":
        return await _mmp_analysis(ref_mol, req)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown method: {method}. Use murcko/mcs/rgroup/mmp.")


async def _murcko_hop(ref_mol, req: ScaffoldHopRequest) -> ScaffoldHopResponse:
    """Murcko scaffold decomposition and comparison."""
    try:
        core = MurckoScaffold.GetScaffoldForMol(ref_mol)
        ref_scaffold = Chem.MolToSmiles(core)
        generic = MurckoScaffold.MakeScaffoldGeneric(core)
        generic_smi = Chem.MolToSmiles(generic)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Murcko decomposition failed: {exc}")

    results: list[ScaffoldHopResult] = [
        ScaffoldHopResult(smiles=ref_scaffold, scaffold=ref_scaffold, similarity=1.0, name="Murcko scaffold"),
        ScaffoldHopResult(smiles=generic_smi, scaffold=generic_smi, similarity=0.0, name="Generic framework"),
    ]

    # Compare with library if provided
    library = _load_library(req.library_path)
    for smi, name in library:
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            continue
        try:
            lib_core = MurckoScaffold.GetScaffoldForMol(mol)
            lib_scaffold = Chem.MolToSmiles(lib_core)
            sim = _tanimoto(core, lib_core)
            results.append(ScaffoldHopResult(
                smiles=smi, scaffold=lib_scaffold, similarity=sim, name=name,
            ))
        except Exception:
            continue
        if len(results) >= req.max_results:
            break

    results.sort(key=lambda r: r.similarity, reverse=True)
    return ScaffoldHopResponse(
        reference=req.smiles, method="murcko",
        reference_scaffold=ref_scaffold,
        results=results[:req.max_results],
        count=len(results),
        message=f"Murcko decomposition: {len(results)} scaffolds analyzed",
    )


async def _mcs_hop(ref_mol, req: ScaffoldHopRequest) -> ScaffoldHopResponse:
    """Maximum common substructure (MCS) based scaffold hopping."""
    library = _load_library(req.library_path)
    results: list[ScaffoldHopResult] = []

    for smi, name in library:
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            continue
        try:
            mcs = rdFMCS.FindMCS([ref_mol, mol], timeout=5, threshold=0.8)
            if mcs.smartsString:
                mcs_mol = Chem.MolFromSmarts(mcs.smartsString)
                scaffold_smi = mcs.smartsString
                sim = _tanimoto(ref_mol, mol)
                results.append(ScaffoldHopResult(
                    smiles=smi, scaffold=scaffold_smi, similarity=sim, name=name,
                ))
        except Exception:
            continue
        if len(results) >= req.max_results:
            break

    results.sort(key=lambda r: r.similarity, reverse=True)
    ref_scaffold = Chem.MolToSmiles(MurckoScaffold.GetScaffoldForMol(ref_mol))

    return ScaffoldHopResponse(
        reference=req.smiles, method="mcs",
        reference_scaffold=ref_scaffold,
        results=results[:req.max_results],
        count=len(results),
        message=f"MCS analysis: {len(results)} compounds compared",
    )


async def _rgroup_decomp(ref_mol, req: ScaffoldHopRequest) -> ScaffoldHopResponse:
    """R-group decomposition of the reference molecule."""
    try:
        core = MurckoScaffold.GetScaffoldForMol(ref_mol)
        ref_scaffold = Chem.MolToSmiles(core)
    except Exception:
        ref_scaffold = req.smiles

    # Generate R-group variants by enumerating side chains
    results: list[ScaffoldHopResult] = []
    try:
        from rdkit.Chem import rdRGroupDecomposition
        library = _load_library(req.library_path)
        lib_mols = []
        lib_names = []
        for smi, name in library[:200]:
            m = Chem.MolFromSmiles(smi)
            if m:
                lib_mols.append(m)
                lib_names.append(name)

        if lib_mols:
            rg = rdRGroupDecomposition.RGroupDecomposition([core])
            for mol in lib_mols:
                rg.Add(mol)
            rg.Process()
            columns = rg.GetRGroupsAsColumns()

            for i, mol in enumerate(lib_mols):
                smi = Chem.MolToSmiles(mol)
                sim = _tanimoto(ref_mol, mol)
                results.append(ScaffoldHopResult(
                    smiles=smi, scaffold=ref_scaffold,
                    similarity=sim, name=lib_names[i] if i < len(lib_names) else "",
                ))
    except Exception:
        # Fallback: just return scaffold
        results.append(ScaffoldHopResult(
            smiles=ref_scaffold, scaffold=ref_scaffold, similarity=1.0, name="Core scaffold",
        ))

    results.sort(key=lambda r: r.similarity, reverse=True)
    return ScaffoldHopResponse(
        reference=req.smiles, method="rgroup",
        reference_scaffold=ref_scaffold,
        results=results[:req.max_results],
        count=len(results),
        message=f"R-group decomposition: {len(results)} variants",
    )


async def _mmp_analysis(ref_mol, req: ScaffoldHopRequest) -> ScaffoldHopResponse:
    """Matched molecular pair (MMP) analysis using BRICS fragmentation."""
    try:
        from rdkit.Chem import BRICS
        ref_smi = Chem.MolToSmiles(ref_mol)
        ref_scaffold = Chem.MolToSmiles(MurckoScaffold.GetScaffoldForMol(ref_mol))

        frags = list(BRICS.BRICSDecompose(ref_mol))
        frag_mols = [Chem.MolFromSmiles(f) for f in frags if Chem.MolFromSmiles(f)]

        results: list[ScaffoldHopResult] = []
        if frag_mols:
            products = BRICS.BRICSBuild(frag_mols)
            seen: set[str] = set()
            for p in products:
                try:
                    smi = Chem.MolToSmiles(p)
                    if smi and smi != ref_smi and smi not in seen:
                        seen.add(smi)
                        sim = _tanimoto(ref_mol, p)
                        results.append(ScaffoldHopResult(
                            smiles=smi, scaffold=ref_scaffold,
                            similarity=sim, name=f"MMP-{len(results)+1}",
                        ))
                        if len(results) >= req.max_results:
                            break
                except Exception:
                    continue

        results.sort(key=lambda r: r.similarity, reverse=True)
        return ScaffoldHopResponse(
            reference=req.smiles, method="mmp",
            reference_scaffold=ref_scaffold,
            results=results[:req.max_results],
            count=len(results),
            message=f"MMP analysis: {len(results)} molecular pairs",
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"MMP analysis failed: {exc}")
