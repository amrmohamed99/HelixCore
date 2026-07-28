"""
Compound Filters router — PAINS, structural alerts, and drug-likeness pre-screening.
Optional pre-docking triage to remove problematic compounds.
"""

import os
import csv
import logging
from fastapi import APIRouter, HTTPException

from backend.models.schemas import FilterRequest, FilterResponse, FilteredCompound

router = APIRouter()
logger = logging.getLogger(__name__)

try:
    from rdkit import Chem
    from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

_pains_catalog = None
if RDKIT_AVAILABLE:
    try:
        params = FilterCatalogParams()
        params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
        _pains_catalog = FilterCatalog(params)
    except Exception:
        logger.warning("Failed to load PAINS filter catalog — PAINS screening will be skipped")

_STRUCTURAL_ALERTS = {
    "Epoxide": "C1OC1",
    "Aldehyde": "[CX3H1](=O)[#6]",
    "Michael_Acceptor": "[CX3]=[CX3][CX3](=[OX1])",  # α,β-unsaturated carbonyl
    "Vinyl_Sulfone": "[CX3]=[CX3][SX4](=[OX1])(=[OX1])",
    "Acyl_Halide": "[CX3](=[OX1])[F,Cl,Br,I]",
    "Sulfonyl_Halide": "[SX4](=[OX1])(=[OX1])[F,Cl,Br,I]",
    "Peroxide": "[OX2][OX2]",
    "Azide": "[$([NX1]=[NX2]=[NX2]),$([NX1]=[NX2]=[NX1])]",
    "Isocyanate": "[NX2]=C=O",
    "Acid_Anhydride": "[CX3](=[OX1])[OX2][CX3](=[OX1])",
    "Nitro_Aromatic": "[$([NX3](=O)=O),$([NX3+](=O)[O-])][c]",
    # Amine N-oxides are tetravalent N+; aromatic N-oxides are three-connected n+.
    # An [NX3+] pattern matches neither and never fired.
    "N_Oxide": "[$([NX4+][OX1-]),$([nX3+][OX1-])]",
    # Matches R-N=N-R (both aromatic and aliphatic azo); does NOT match hydrazones (R2C=N-NX3R2)
    "Azo_Compound": "[NX2]=[NX2]",
    "Thiocarbonyl": "[#6](=[SX1])",
    "Vinyl_Nitrile": "[CX3]=[CX3][CX2]#[NX1]",   # α,β-unsaturated nitrile (Michael acceptor)
    "Maleimide": "O=C1C=CC(=O)[NX3]1",            # Reactive Michael acceptor (Cys-targeting)
}

# Alerts for intentional covalent warheads — suppressed when covalent_mode=True
_COVALENT_WARHEAD_ALERTS = {"Michael_Acceptor", "Vinyl_Sulfone", "Vinyl_Nitrile", "Maleimide"}


def _check_compound(mol, covalent_mode: bool = False) -> dict:
    """Run all filters on an RDKit Mol object."""
    result = {"pains_free": True, "pains_matches": [], "alert_free": True, "alerts": []}

    if _pains_catalog:
        entry = _pains_catalog.GetFirstMatch(mol)
        if entry:
            result["pains_free"] = False
            result["pains_matches"].append(entry.GetDescription())

    for name, smarts in _STRUCTURAL_ALERTS.items():
        if covalent_mode and name in _COVALENT_WARHEAD_ALERTS:
            continue
        pattern = Chem.MolFromSmarts(smarts)
        if pattern and mol.HasSubstructMatch(pattern):
            result["alert_free"] = False
            result["alerts"].append(name)

    return result


@router.post("/scan", response_model=FilterResponse)
async def scan_compounds(req: FilterRequest):
    """Scan compounds for PAINS and structural alerts."""
    if not RDKIT_AVAILABLE:
        raise HTTPException(status_code=500, detail="RDKit not installed")

    smiles_list: list[tuple[str, str]] = []

    if os.path.isfile(req.input_path):
        with open(req.input_path, "r") as f:
            for line in f:
                parts = line.strip().split()
                if parts:
                    smi = parts[0]
                    name = parts[1] if len(parts) > 1 else f"mol_{len(smiles_list)}"
                    smiles_list.append((name, smi))
    elif os.path.isdir(req.input_path):
        for fname in sorted(os.listdir(req.input_path)):
            if fname.endswith((".pdb", ".sdf", ".mol")):
                fpath = os.path.join(req.input_path, fname)
                mol = (
                    Chem.MolFromPDBFile(fpath)
                    if fname.endswith(".pdb")
                    else Chem.MolFromMolFile(fpath)
                )
                if mol:
                    smiles_list.append(
                        (os.path.splitext(fname)[0], Chem.MolToSmiles(mol))
                    )
    else:
        raise HTTPException(status_code=400, detail="Input path not found")

    compounds: list[FilteredCompound] = []
    passed = flagged = 0

    for name, smi in smiles_list:
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            compounds.append(
                FilteredCompound(name=name, smiles=smi, passed=False, pains_free=False)
            )
            flagged += 1
            continue

        checks = _check_compound(mol, covalent_mode=req.covalent_mode)
        is_clean = checks["pains_free"] and checks["alert_free"]
        if is_clean:
            passed += 1
        else:
            flagged += 1

        compounds.append(
            FilteredCompound(
                name=name,
                smiles=smi,
                pains_free=checks["pains_free"],
                pains_matches=checks["pains_matches"],
                alert_free=checks["alert_free"],
                alerts=checks["alerts"],
                passed=is_clean,
            )
        )

    report_dir = (
        os.path.dirname(req.input_path)
        if os.path.isfile(req.input_path)
        else req.input_path
    )
    csv_path = os.path.join(report_dir, "filter_report.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            ["Name", "SMILES", "PAINS_Free", "PAINS_Matches", "Alert_Free", "Alerts", "Passed"]
        )
        for c in compounds:
            w.writerow([
                c.name, c.smiles, c.pains_free,
                "; ".join(c.pains_matches), c.alert_free,
                "; ".join(c.alerts), c.passed,
            ])

    return FilterResponse(
        compounds=compounds,
        total=len(compounds),
        passed=passed,
        flagged=flagged,
        report_path=csv_path,
    )
