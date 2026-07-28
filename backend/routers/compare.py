"""
Comparison router — compare multiple compounds side-by-side.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, Lipinski, Crippen, rdMolDescriptors
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False


class CompareRequest(BaseModel):
    """Given a list of SMILES, compute properties for side-by-side comparison."""
    smiles_list: list[str]
    names: list[str] = []
    ro5_mw: float = 500
    ro5_logp: float = 5
    ro5_hbd: int = 5
    ro5_hba: int = 10
    ro5_max_violations: int = 1


class CompoundProfile(BaseModel):
    """Full profile for one compound."""
    name: str
    smiles: str
    mw: float
    logp: float
    hbd: int
    hba: int
    tpsa: float
    rotatable_bonds: int
    rings: int
    heavy_atoms: int
    qed: float | None = None
    sa_score: float | None = None
    rule_of_5: str
    ro5_violations: int


class CompareResponse(BaseModel):
    """Side-by-side comparison result."""
    compounds: list[CompoundProfile]
    property_ranges: dict


def _ro5_check(mw: float, logp: float, hbd: int, hba: int,
               mw_limit: float = 500, logp_limit: float = 5,
               hbd_limit: int = 5, hba_limit: int = 10,
               max_violations: int = 1) -> tuple[str, int]:
    """Lipinski Rule of Five check."""
    violations = sum([mw > mw_limit, logp > logp_limit, hbd > hbd_limit, hba > hba_limit])
    label = "Pass" if violations <= max_violations else "Fail"
    return label, violations


@router.post("/compare", response_model=CompareResponse)
async def compare_compounds(req: CompareRequest):
    """Compare multiple compounds by computing their molecular properties."""
    if not RDKIT_AVAILABLE:
        raise HTTPException(status_code=503, detail="RDKit not available")
    if len(req.smiles_list) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 SMILES for comparison")
    if len(req.smiles_list) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 compounds for comparison")

    compounds: list[CompoundProfile] = []

    try:
        from rdkit.Chem.QED import qed as calc_qed
    except ImportError:
        calc_qed = None

    for i, smi in enumerate(req.smiles_list):
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            name = req.names[i] if i < len(req.names) else f"Compound_{i + 1}"
            raise HTTPException(status_code=400, detail=f"Invalid SMILES for {name}: {smi}")

        name = req.names[i] if i < len(req.names) else f"Compound_{i + 1}"
        mw = round(Descriptors.ExactMolWt(mol), 2)
        logp = round(Crippen.MolLogP(mol), 2)
        hbd = Lipinski.NumHDonors(mol)
        hba = Lipinski.NumHAcceptors(mol)
        tpsa = round(Descriptors.TPSA(mol), 2)
        rotb = Lipinski.NumRotatableBonds(mol)
        rings = Lipinski.RingCount(mol)
        heavy = mol.GetNumHeavyAtoms()
        qed_val = round(calc_qed(mol), 3) if calc_qed else None
        ro5_label, ro5_viol = _ro5_check(
            mw, logp, hbd, hba,
            req.ro5_mw, req.ro5_logp, req.ro5_hbd, req.ro5_hba, req.ro5_max_violations,
        )

        compounds.append(CompoundProfile(
            name=name,
            smiles=smi,
            mw=mw,
            logp=logp,
            hbd=hbd,
            hba=hba,
            tpsa=tpsa,
            rotatable_bonds=rotb,
            rings=rings,
            heavy_atoms=heavy,
            qed=qed_val,
            sa_score=None,
            rule_of_5=ro5_label,
            ro5_violations=ro5_viol,
        ))

    # Compute property ranges for highlighting
    prop_keys = ['mw', 'logp', 'hbd', 'hba', 'tpsa', 'rotatable_bonds', 'rings', 'heavy_atoms']
    property_ranges: dict = {}
    for key in prop_keys:
        vals = [getattr(c, key) for c in compounds]
        property_ranges[key] = {
            "min": min(vals),
            "max": max(vals),
            "mean": round(sum(vals) / len(vals), 2),
        }

    return CompareResponse(compounds=compounds, property_ranges=property_ranges)
