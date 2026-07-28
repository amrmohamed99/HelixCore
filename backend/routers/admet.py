"""
Extended ADMET router — QED, SA Score, ESOL solubility, BBB triage, Bertz complexity.
Optional deep property profiling beyond basic Lipinski Ro5.

The blood-brain-barrier output is a **triage flag**, not a permeability
prediction: three descriptor thresholds are applied and the verdict, the
thresholds and the descriptor values are all returned so the user can see what
produced it.  See :data:`BBB_TRIAGE_CAVEAT`.
"""

import os
import csv
from fastapi import APIRouter, HTTPException

from backend.models.schemas import (
    ADMETRequest,
    ADMETProfile,
    ADMETResponse,
    BBBTriage,
    BBBTriageCriterion,
    BBB_TRIAGE_CAVEAT,
    Ro5Thresholds,
)
from backend.services.job_manager import JobCancelled, job_manager, job_progress_message

router = APIRouter()

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, Lipinski, QED as QEDModule, AllChem
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False


def _esol_logS(mol) -> float:
    """ESOL aqueous solubility model (Delaney 2004)."""
    logp = Descriptors.MolLogP(mol)
    mw = Descriptors.MolWt(mol)
    rb = Descriptors.NumRotatableBonds(mol)
    ap = (
        len(mol.GetAromaticAtoms()) / mol.GetNumHeavyAtoms()
        if mol.GetNumHeavyAtoms() > 0
        else 0
    )
    return 0.16 - 0.63 * logp - 0.0062 * mw + 0.066 * rb - 0.74 * ap


# ── BBB triage thresholds (Lipinski + Clark 2003 guidelines) ──
# These are the *only* inputs to the flag.  They are surfaced in the API
# response and in the UI so the verdict is never an unexplained black box.
BBB_MW_MAX = 450.0      # Da, exclusive
BBB_TPSA_MAX = 90.0     # Å², exclusive
BBB_LOGP_MIN = 0.5      # inclusive
BBB_LOGP_MAX = 4.5      # inclusive


def _bbb_triage(mol) -> BBBTriage:
    """Apply the three BBB triage thresholds and report each one individually.

    This is a descriptor filter, not a trained model.  It has known false
    negatives (caffeine); the caveat travels with the result.
    """
    mw = Descriptors.MolWt(mol)
    tpsa = Descriptors.TPSA(mol)
    logp = Descriptors.MolLogP(mol)

    criteria = [
        BBBTriageCriterion(
            name="MW", value=round(float(mw), 2), operator="<",
            threshold=f"{BBB_MW_MAX:g}", passed=mw < BBB_MW_MAX,
        ),
        BBBTriageCriterion(
            name="TPSA", value=round(float(tpsa), 2), operator="<",
            threshold=f"{BBB_TPSA_MAX:g}", passed=tpsa < BBB_TPSA_MAX,
        ),
        BBBTriageCriterion(
            name="LogP", value=round(float(logp), 2), operator="within",
            threshold=f"[{BBB_LOGP_MIN:g}, {BBB_LOGP_MAX:g}]",
            passed=BBB_LOGP_MIN <= logp <= BBB_LOGP_MAX,
        ),
    ]

    return BBBTriage(
        flag=all(c.passed for c in criteria),
        criteria=criteria,
        caveat=BBB_TRIAGE_CAVEAT,
    )


def _bbb_triage_flag(mol) -> bool:
    """Verdict of the three-threshold BBB triage filter."""
    return _bbb_triage(mol).flag


def _bbb_permeable(mol) -> bool:
    """Deprecated alias of :func:`_bbb_triage_flag`.

    Kept so callers written against the old "BBB permeable" name keep working;
    the name overstates what the filter does.
    """
    return _bbb_triage_flag(mol)


def _sa_score(mol) -> float:
    """Synthetic Accessibility Score (1 = easy, 10 = hard). Falls back to heuristic."""
    try:
        from rdkit.Chem import RDConfig
        import sys
        sa_path = os.path.join(RDConfig.RDContribDir, "SA_Score")
        if sa_path not in sys.path:
            sys.path.insert(0, sa_path)
        import sascorer
        return round(sascorer.calculateScore(mol), 2)
    except Exception:
        nrings = Descriptors.RingCount(mol)
        natoms = mol.GetNumHeavyAtoms()
        nchiral = len(Chem.FindMolChiralCenters(mol, includeUnassigned=True))
        # Heuristic fallback: ring term subtracts because common ring systems
        # (benzene, pyridine, piperidine) are commercially available building blocks,
        # empirically offsetting the heavy-atom inflation. Does not model
        # fused/bridged/spiro ring complexity (Ertl & Schuffenhauer 2009).
        score = 3.0 + (nchiral * 0.5) + max(0, (natoms - 20) * 0.1) - min(nrings, 3) * 0.3
        return round(max(1.0, min(10.0, score)), 2)


def _profile_mol(mol, name: str, ro5: Ro5Thresholds = Ro5Thresholds()) -> ADMETProfile:
    """Compute full ADMET profile for a molecule."""
    smi = Chem.MolToSmiles(mol)
    mw = round(Descriptors.MolWt(mol), 2)
    logp = round(Descriptors.MolLogP(mol), 2)
    hbd = Lipinski.NumHDonors(mol)
    hba = Lipinski.NumHAcceptors(mol)
    tpsa = round(Descriptors.TPSA(mol), 2)
    rb = Descriptors.NumRotatableBonds(mol)

    violations = sum([mw > ro5.mw, logp > ro5.logp, hbd > ro5.hbd, hba > ro5.hba])
    ro5_label = "PASS" if violations <= ro5.max_violations else f"FAIL ({violations})"

    try:
        qed = round(QEDModule.qed(mol), 3)
    except Exception:
        qed = None

    sa = _sa_score(mol)
    bertz = round(Descriptors.BertzCT(mol), 2)
    esol = round(_esol_logS(mol), 3)
    bbb = _bbb_triage(mol)

    return ADMETProfile(
        name=name, smiles=smi, mw=mw, logp=logp, hbd=hbd, hba=hba,
        tpsa=tpsa, rotatable_bonds=rb, qed=qed, sa_score=sa,
        bertz_ct=bertz, esol_logS=esol,
        bbb_triage_flag=bbb.flag, bbb_triage=bbb,
        bbb_permeable=bbb.flag,  # deprecated alias, same value
        rule_of_5=ro5_label, ro5_violations=violations,
    )


def _bbb_basis(profile: ADMETProfile) -> str:
    """One-line, human-readable record of why the triage flag came out as it did."""
    if profile.bbb_triage is None:
        return ""
    return "; ".join(
        f"{c.name}={c.value} {c.operator} {c.threshold} "
        f"{'PASS' if c.passed else 'FAIL'}"
        for c in profile.bbb_triage.criteria
    )


@router.post("/profile", response_model=ADMETResponse)
async def compute_admet(req: ADMETRequest):
    """Compute extended ADMET profile for SMILES or a file of molecules."""
    if not RDKIT_AVAILABLE:
        raise HTTPException(status_code=500, detail="RDKit not installed")

    profiles: list[ADMETProfile] = []

    if req.smiles:
        # Use universal resolver to support SMILES, InChI, names, CAS, MOL blocks
        from backend.routers.resolve import resolve_to_smiles
        try:
            resolved_smiles, _, resolved_name = resolve_to_smiles(req.smiles)
            mol = Chem.MolFromSmiles(resolved_smiles)
        except Exception:
            mol = None
        if mol is None:
            raise HTTPException(status_code=400, detail="Could not resolve molecule — try SMILES, InChI, compound name, or CAS number")
        name = resolved_name or "query"
        profiles.append(_profile_mol(mol, name, req.ro5))
        return ADMETResponse(profiles=profiles, csv_path=None)

    if not req.file_path:
        raise HTTPException(status_code=400, detail="Provide smiles or file_path")

    if not os.path.exists(req.file_path):
        raise HTTPException(status_code=400, detail="File not found")

    candidates: list[tuple[str, str, str]] = []
    if os.path.isdir(req.file_path):
        for fname in sorted(os.listdir(req.file_path)):
            if fname.endswith((".pdb", ".sdf", ".mol")):
                candidates.append(("file", fname, os.path.join(req.file_path, fname)))
    else:
        with open(req.file_path, "r") as f:
            for i, line in enumerate(f):
                parts = line.strip().split()
                if parts:
                    name = parts[1] if len(parts) > 1 else f"mol_{i}"
                    candidates.append(("smiles", name, parts[0]))

    job = await job_manager.begin("ADMET Profiling", total=len(candidates), message="Preparing ADMET profiling")
    try:
        last_done: str | None = None
        for idx, (kind, name, value) in enumerate(candidates):
            await job_manager.checkpoint(
                job.id,
                current=idx,
                total=len(candidates),
                progress=int((idx / max(len(candidates), 1)) * 100),
                message=job_progress_message("Profiling ADMET", name, idx, len(candidates), last_done),
            )
            added = False
            if kind == "file":
                mol = (
                    Chem.MolFromPDBFile(value)
                    if value.endswith(".pdb")
                    else Chem.MolFromMolFile(value)
                )
                if mol:
                    profiles.append(_profile_mol(mol, os.path.splitext(name)[0], req.ro5))
                    added = True
            else:
                mol = Chem.MolFromSmiles(value)
                if mol:
                    profiles.append(_profile_mol(mol, name, req.ro5))
                    added = True
            last_done = name if added else f"{name} skipped"
    except JobCancelled:
        await job_manager.finish(job.id, "cancelled", f"ADMET profiling cancelled: {len(profiles)} profiles")
    except Exception as exc:
        await job_manager.finish(job.id, "error", f"ADMET profiling failed: {exc}")
        raise
    else:
        await job_manager.finish(job.id, "completed", f"ADMET profiling complete: {len(profiles)} profiles", progress=100)

    out_dir = req.file_path if os.path.isdir(req.file_path) else os.path.dirname(req.file_path)
    csv_path = os.path.join(out_dir, "admet_profiles.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "Name", "SMILES", "MW", "LogP", "HBD", "HBA", "TPSA",
            "RotBonds", "QED", "SA_Score", "BertzCT", "ESOL_logS",
            "BBB_Triage_Flag", "BBB_Triage_Basis", "Ro5",
        ])
        for p in profiles:
            w.writerow([
                p.name, p.smiles, p.mw, p.logp, p.hbd, p.hba, p.tpsa,
                p.rotatable_bonds, p.qed, p.sa_score, p.bertz_ct,
                p.esol_logS, p.bbb_triage_flag, _bbb_basis(p), p.rule_of_5,
            ])

    return ADMETResponse(profiles=profiles, csv_path=csv_path)


@router.post("/batch", response_model=ADMETResponse)
async def batch_admet(req: dict):
    """Compute ADMET profiles for a list of SMILES strings.

    Expects ``{"smiles_list": ["CCO", "c1ccccc1", ...]}``
    """
    if not RDKIT_AVAILABLE:
        raise HTTPException(status_code=500, detail="RDKit not installed")

    smiles_list: list[str] = req.get("smiles_list", [])
    if not smiles_list:
        raise HTTPException(status_code=400, detail="Provide a non-empty smiles_list")

    profiles: list[ADMETProfile] = []
    job = await job_manager.begin("Batch ADMET Profiling", total=len(smiles_list), message="Preparing ADMET batch")
    try:
        last_done: str | None = None
        for idx, smi in enumerate(smiles_list):
            item_name = smi[:36]
            await job_manager.checkpoint(
                job.id,
                current=idx,
                total=len(smiles_list),
                progress=int((idx / max(len(smiles_list), 1)) * 100),
                message=job_progress_message("Profiling ADMET", item_name, idx, len(smiles_list), last_done),
            )
            mol = Chem.MolFromSmiles(smi)
            if mol:
                profiles.append(_profile_mol(mol, smi))
                last_done = item_name
            else:
                last_done = f"{item_name} skipped"
    except JobCancelled:
        await job_manager.finish(job.id, "cancelled", f"Batch ADMET cancelled: {len(profiles)} profiles")
        return ADMETResponse(profiles=profiles, csv_path=None)
    except Exception as exc:
        await job_manager.finish(job.id, "error", f"Batch ADMET failed: {exc}")
        raise
    else:
        await job_manager.finish(job.id, "completed", f"Batch ADMET complete: {len(profiles)} profiles", progress=100)

    return ADMETResponse(profiles=profiles, csv_path=None)
