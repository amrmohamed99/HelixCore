"""
Converter router — PDB to PDBQT batch conversion via OpenBabel.
Ported from drug_tool.py: _t_conv.
"""

import os
import subprocess
from fastapi import APIRouter, HTTPException

_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

from backend.config import get_obabel
from backend.models.schemas import ConvertRequest, ConvertResponse, ProcessingFailure
from backend.services.job_manager import JobCancelled, job_manager, job_progress_message
from backend.utils.file_order import sorted_matching_files
from backend.utils.paths import get_obabel_env
from backend.utils.pdbqt_utils import validate_ligand_pdbqt

router = APIRouter()


@router.post("/", response_model=ConvertResponse)
async def convert(req: ConvertRequest):
    """Convert all .pdb files in a directory to .pdbqt using OpenBabel."""
    if not os.path.isdir(req.directory):
        raise HTTPException(status_code=400, detail="Directory not found")

    ob = get_obabel()
    env = get_obabel_env()
    out_dir = os.path.join(req.directory, "pdbqt_out")
    os.makedirs(out_dir, exist_ok=True)

    converted = 0
    failed = 0
    failures: list[ProcessingFailure] = []
    files = sorted_matching_files(req.directory, (".pdb", ".sdf", ".mol", ".mol2"))
    job = await job_manager.begin("Format Conversion", total=len(files), message="Preparing PDBQT conversion")

    try:
        last_done: str | None = None
        for idx, fname in enumerate(files):
            await job_manager.checkpoint(
                job.id,
                current=idx,
                total=len(files),
                progress=int((idx / max(len(files), 1)) * 100),
                message=job_progress_message("Converting file", fname, idx, len(files), last_done),
            )
            in_path = os.path.join(req.directory, fname)
            out_path = os.path.join(out_dir, f"{os.path.splitext(fname)[0]}.pdbqt")
            try:
                await job_manager.run_subprocess(
                    job.id,
                    [ob, in_path, "-O", out_path, "--partialcharge", "gasteiger"],
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                    creationflags=_NO_WINDOW,
                )
                validate_ligand_pdbqt(out_path)
                converted += 1
                last_done = fname
            except JobCancelled:
                raise
            except subprocess.CalledProcessError as exc:
                failed += 1
                detail = (exc.stderr or exc.stdout or "").strip()[-300:]
                failures.append(
                    ProcessingFailure(
                        item=fname,
                        reason="conversion_process_failed",
                        detail=detail or f"Open Babel exited with code {exc.returncode}.",
                    )
                )
                last_done = f"{fname} failed"
            except ValueError as exc:
                failed += 1
                failures.append(
                    ProcessingFailure(
                        item=fname,
                        reason="invalid_ligand_pdbqt",
                        detail=str(exc)[:300],
                    )
                )
                last_done = f"{fname} failed"
            except Exception as exc:
                failed += 1
                failures.append(
                    ProcessingFailure(
                        item=fname,
                        reason="conversion_exception",
                        detail=type(exc).__name__,
                    )
                )
                last_done = f"{fname} failed"

        await job_manager.finish(job.id, "completed", f"Conversion complete: {converted} converted, {failed} failed", progress=100)
        return ConvertResponse(
            output_dir=out_dir,
            converted=converted,
            failed=failed,
            failures=failures,
        )
    except JobCancelled:
        await job_manager.finish(job.id, "cancelled", f"Conversion cancelled: {converted} converted, {failed} failed")
        return ConvertResponse(
            output_dir=out_dir,
            converted=converted,
            failed=failed,
            failures=failures,
        )
    except Exception as exc:
        await job_manager.finish(job.id, "error", f"Conversion failed: {exc}")
        raise
