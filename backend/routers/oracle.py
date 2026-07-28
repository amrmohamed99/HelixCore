"""
Oracle AI router — Vina + ADMET affinity rescoring with optional ML model.
Ported from drug_tool.py: _t_oracle.
"""

import os
import csv
import subprocess
import pickle
from fastapi import APIRouter, HTTPException

_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

from backend.config import get_obabel
from backend.models.schemas import OracleRequest, OraclePrediction, OracleResponse
from backend.services.job_manager import JobCancelled, job_manager, job_progress_message
from backend.utils.paths import get_obabel_env
from backend.utils.pdbqt_utils import parse_vina_score

router = APIRouter()

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, Lipinski
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

try:
    from sklearn.ensemble import RandomForestRegressor
    import numpy as np
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False


@router.post("/predict", response_model=OracleResponse)
async def predict(req: OracleRequest):
    """Run AI-based affinity rescoring on docking results."""
    if not RDKIT_AVAILABLE:
        raise HTTPException(status_code=500, detail="RDKit not installed")

    dock_dir = req.dock_dir
    if not os.path.isdir(dock_dir):
        raise HTTPException(status_code=400, detail="Docking directory not found")

    # Determine actual results dir
    target_dir = dock_dir
    sub = os.path.join(dock_dir, "Docking_Results")
    if os.path.isdir(sub):
        target_dir = sub

    # Load optional model
    model = None
    if req.model_path and os.path.isfile(req.model_path):
        try:
            with open(req.model_path, "rb") as f:
                model = pickle.load(f)
        except Exception:
            model = None

    ob = get_obabel()
    env = get_obabel_env()

    files = [
        f for f in os.listdir(target_dir)
        if f.endswith(".pdbqt") and "_out" in f
    ]

    predictions: list[OraclePrediction] = []
    job = await job_manager.begin("Oracle AI Rescoring", total=len(files), message="Preparing rescoring")

    try:
        last_done: str | None = None
        for idx, fname in enumerate(files):
            await job_manager.checkpoint(
                job.id,
                current=idx,
                total=len(files),
                progress=int((idx / max(len(files), 1)) * 100),
                message=job_progress_message("Rescoring ligand", fname, idx, len(files), last_done),
            )
            name = fname.replace("_out.pdbqt", "")
            path = os.path.join(target_dir, fname)

            vina_score = parse_vina_score(path)

            # Convert to PDB for feature extraction
            temp_pdb = os.path.join(target_dir, "temp_feat.pdb")
            try:
                await job_manager.run_subprocess(
                    job.id,
                    [ob, path, "-O", temp_pdb, "-m"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    capture_output=False,
                    creationflags=_NO_WINDOW,
                )
            except JobCancelled:
                raise
            except Exception:
                pass

            target_pdb = os.path.join(target_dir, "temp_feat1.pdb")
            if not os.path.exists(target_pdb):
                target_pdb = temp_pdb

            features = [0.0] * 6
            if os.path.exists(target_pdb):
                mol = Chem.MolFromPDBFile(target_pdb)
                if mol:
                    features = [
                        Descriptors.MolWt(mol),
                        Descriptors.MolLogP(mol),
                        Descriptors.NumRotatableBonds(mol),
                        Descriptors.TPSA(mol),
                        Lipinski.NumHDonors(mol),
                        Lipinski.NumHAcceptors(mol),
                    ]
                # Clean up temp files
                for tf in [temp_pdb, os.path.join(target_dir, "temp_feat1.pdb")]:
                    try:
                        os.remove(tf)
                    except OSError:
                        pass

            # Predict binding affinity
            method = "thermodynamic_pKd"
            confidence = "low"
            if model and ML_AVAILABLE:
                input_vec = np.array([[vina_score] + features])
                # Warn if features are extreme (possible normalization mismatch)
                mw, logp, _, tpsa = features[0], features[1], features[2], features[3]
                if mw > 900 or mw < 50 or logp > 8 or logp < -5 or tpsa > 200:
                    confidence = "very_low"
                else:
                    confidence = "medium"
                pred = float(model.predict(input_vec)[0])
                method = "ml_model"
            else:
                # Thermodynamic conversion: ΔG = -RT·ln(Kd)
                # At 298K: pKd ≈ -ΔG / (2.303 × RT) = -vina_score / 1.3643
                pred = -vina_score / 1.3643
                confidence = "low"

            predictions.append(
                OraclePrediction(
                    ligand=name,
                    vina_score=vina_score,
                    predicted_pKd=round(pred, 2),
                    confidence=confidence,
                    method=method,
                )
            )
            last_done = f"{name} (pKd {round(pred, 2)})"

        # Save CSV
        csv_path = os.path.join(target_dir, "Oracle_Predictions.csv")
        with open(csv_path, "w", newline="") as csvfile:
            w = csv.writer(csvfile)
            w.writerow(["Ligand", "Vina_Score", "Predicted_pKd", "Confidence", "Method"])
            for p in predictions:
                w.writerow([p.ligand, p.vina_score, p.predicted_pKd, p.confidence, p.method])

        await job_manager.finish(job.id, "completed", f"Oracle rescoring complete: {len(predictions)} predictions", progress=100)
        return OracleResponse(predictions=predictions, csv_path=csv_path)
    except JobCancelled:
        csv_path = os.path.join(target_dir, "Oracle_Predictions.csv")
        if predictions:
            with open(csv_path, "w", newline="") as csvfile:
                w = csv.writer(csvfile)
                w.writerow(["Ligand", "Vina_Score", "Predicted_pKd", "Confidence", "Method"])
                for p in predictions:
                    w.writerow([p.ligand, p.vina_score, p.predicted_pKd, p.confidence, p.method])
        await job_manager.finish(job.id, "cancelled", f"Oracle rescoring cancelled: {len(predictions)} predictions")
        return OracleResponse(predictions=predictions, csv_path=csv_path if predictions else None)
    except Exception as exc:
        await job_manager.finish(job.id, "error", f"Oracle rescoring failed: {exc}")
        raise
