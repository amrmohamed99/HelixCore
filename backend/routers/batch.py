"""
Batch Generator router — mass 3D ligand generation from SMILES list.
Ported from drug_tool.py: _t_batch.
"""

import os
from fastapi import APIRouter, HTTPException

from backend.models.schemas import BatchRequest, BatchResponse, ProcessingFailure
from backend.services.job_manager import JobCancelled, job_manager, job_progress_message

router = APIRouter()

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False


@router.post("/generate", response_model=BatchResponse)
async def generate_batch(req: BatchRequest):
    """Generate 3D PDB files from a SMILES list."""
    if not RDKIT_AVAILABLE:
        raise HTTPException(status_code=500, detail="RDKit not installed")
    if not os.path.isfile(req.smiles_file):
        raise HTTPException(status_code=400, detail="SMILES file not found")

    out_dir = os.path.join(os.path.dirname(req.smiles_file), "Batch_3D")
    os.makedirs(out_dir, exist_ok=True)

    with open(req.smiles_file, "r") as f:
        lines = f.readlines()

    generated = 0
    failed = 0
    failures: list[ProcessingFailure] = []
    work_items = [line.strip() for line in lines if line.strip()]
    job = await job_manager.begin("Batch 3D Generation", total=len(work_items), message="Preparing ligand generation")

    try:
        last_done: str | None = None
        for i, line in enumerate(work_items):
            parts = line.split()
            item_name = parts[1] if len(parts) > 1 else parts[0][:32]
            await job_manager.checkpoint(
                job.id,
                current=i,
                total=len(work_items),
                progress=int((i / max(len(work_items), 1)) * 100),
                message=job_progress_message("Generating 3D compound", item_name, i, len(work_items), last_done),
            )
            try:
                smiles = parts[0]
                name = parts[1] if len(parts) > 1 else f"Lig_{i}"
                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    failed += 1
                    failures.append(
                        ProcessingFailure(
                            item=name,
                            reason="invalid_smiles",
                            detail="RDKit could not parse the supplied SMILES.",
                        )
                    )
                    continue
                mol = Chem.AddHs(mol)
                result = AllChem.EmbedMolecule(mol, randomSeed=42)
                if result == -1:
                    result = AllChem.EmbedMolecule(mol, useRandomCoords=True, randomSeed=42)
                if result == -1:
                    failed += 1
                    failures.append(
                        ProcessingFailure(
                            item=name,
                            reason="embedding_failed",
                            detail="Both deterministic 3D embedding attempts failed.",
                        )
                    )
                    continue
                ff_result = AllChem.MMFFOptimizeMolecule(mol, maxIters=500)
                if ff_result == 1:
                    AllChem.MMFFOptimizeMolecule(mol, maxIters=1500)
                Chem.MolToPDBFile(mol, os.path.join(out_dir, f"{name}.pdb"))
                generated += 1
                last_done = name
            except Exception as exc:
                failed += 1
                failures.append(
                    ProcessingFailure(
                        item=item_name,
                        reason="generation_exception",
                        detail=type(exc).__name__,
                    )
                )
                last_done = f"{item_name} failed"

        await job_manager.finish(
            job.id,
            "completed",
            f"Batch generation complete: {generated} generated, {failed} failed",
            progress=100,
        )
        return BatchResponse(
            output_dir=out_dir,
            generated=generated,
            failed=failed,
            failures=failures,
        )
    except JobCancelled:
        await job_manager.finish(
            job.id,
            "cancelled",
            f"Batch generation cancelled: {generated} generated, {failed} failed",
        )
        return BatchResponse(
            output_dir=out_dir,
            generated=generated,
            failed=failed,
            failures=failures,
        )
    except Exception as exc:
        await job_manager.finish(job.id, "error", f"Batch generation failed: {exc}")
        raise
