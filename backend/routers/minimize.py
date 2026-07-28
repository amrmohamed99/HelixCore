"""
Minimization router — geometry optimization with RDKit force fields.
Ported from drug_tool.py: _t_min.
"""

import os
from fastapi import APIRouter, HTTPException

from backend.models.schemas import MinimizeRequest, MinimizeResponse, ProcessingFailure
from backend.services.job_manager import JobCancelled, job_manager, job_progress_message
from backend.utils.file_order import sorted_matching_files

router = APIRouter()

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False


@router.post("/", response_model=MinimizeResponse)
async def minimize(req: MinimizeRequest):
    """Optimize 3D geometry of .sdf/.pdb files using the specified force field."""
    if not RDKIT_AVAILABLE:
        raise HTTPException(status_code=500, detail="RDKit not installed")
    if not os.path.isdir(req.directory):
        raise HTTPException(status_code=400, detail="Directory not found")

    out_dir = os.path.join(req.directory, "rdkit_min")
    os.makedirs(out_dir, exist_ok=True)

    ff = req.force_field
    processed = 0
    failed = 0
    failures: list[ProcessingFailure] = []
    files = sorted_matching_files(req.directory, (".sdf", ".pdb"))
    job = await job_manager.begin("Energy Minimization", total=len(files), message="Preparing minimization")

    try:
        last_done: str | None = None
        for idx, fname in enumerate(files):
            await job_manager.checkpoint(
                job.id,
                current=idx,
                total=len(files),
                progress=int((idx / max(len(files), 1)) * 100),
                message=job_progress_message("Minimizing compound", fname, idx, len(files), last_done),
            )
            fpath = os.path.join(req.directory, fname)
            try:
                if fname.endswith(".sdf"):
                    mol = Chem.SDMolSupplier(fpath)[0]
                else:
                    mol = Chem.MolFromPDBFile(fpath)

                if mol is None:
                    failed += 1
                    failures.append(
                        ProcessingFailure(
                            item=fname,
                            reason="structure_parse_failed",
                            detail="RDKit could not parse the input structure.",
                        )
                    )
                    continue

                mol = Chem.AddHs(mol, addCoords=True)
                # Only re-embed if molecule has no 3D coordinates (preserve docked poses)
                if mol.GetNumConformers() == 0:
                    embed_result = AllChem.EmbedMolecule(mol, randomSeed=42)
                    if embed_result == -1:
                        embed_result = AllChem.EmbedMolecule(mol, useRandomCoords=True, randomSeed=42)
                    if embed_result == -1:
                        failed += 1
                        failures.append(
                            ProcessingFailure(
                                item=fname,
                                reason="embedding_failed",
                                detail="Both deterministic 3D embedding attempts failed.",
                            )
                        )
                        continue

                if ff == "UFF":
                    result = AllChem.UFFOptimizeMolecule(mol, maxIters=500)
                    if result == 1:
                        AllChem.UFFOptimizeMolecule(mol, maxIters=1500)
                elif ff == "MMFF94":
                    result = AllChem.MMFFOptimizeMolecule(mol, mmffVariant="MMFF94", maxIters=500)
                    if result == 1:
                        AllChem.MMFFOptimizeMolecule(mol, mmffVariant="MMFF94", maxIters=1500)
                elif ff == "MMFF94s":
                    result = AllChem.MMFFOptimizeMolecule(mol, mmffVariant="MMFF94s", maxIters=500)
                    if result == 1:
                        AllChem.MMFFOptimizeMolecule(mol, mmffVariant="MMFF94s", maxIters=1500)

                out_path = os.path.join(out_dir, f"{os.path.splitext(fname)[0]}.pdb")
                Chem.MolToPDBFile(mol, out_path)
                processed += 1
                last_done = fname
            except Exception as exc:
                failed += 1
                failures.append(
                    ProcessingFailure(
                        item=fname,
                        reason="minimization_exception",
                        detail=type(exc).__name__,
                    )
                )
                last_done = f"{fname} failed"

        await job_manager.finish(
            job.id,
            "completed",
            f"Minimization complete: {processed} processed, {failed} failed",
            progress=100,
        )
        return MinimizeResponse(
            output_dir=out_dir,
            processed=processed,
            failed=failed,
            failures=failures,
        )
    except JobCancelled:
        await job_manager.finish(
            job.id,
            "cancelled",
            f"Minimization cancelled: {processed} processed, {failed} failed",
        )
        return MinimizeResponse(
            output_dir=out_dir,
            processed=processed,
            failed=failed,
            failures=failures,
        )
    except Exception as exc:
        await job_manager.finish(job.id, "error", f"Minimization failed: {exc}")
        raise
