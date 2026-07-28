"""
Auto-Pipeline router — SMILES → 3D → PDBQT → Vina Docking.
Ported from drug_tool.py: _t_pipeline.
Includes SSE streaming variants for real-time progress.
"""

import asyncio
import json
import os
import subprocess
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

from backend.config import find_vina, get_obabel
from backend.models.schemas import PipelineRequest, PipelineResponse, BatchPipelineRequest, BatchPipelineStep, BatchPipelineResponse
from backend.services.job_manager import JobCancelled, job_manager, job_progress_message
from backend.utils.paths import get_obabel_env
from backend.utils.pdbqt_utils import parse_vina_process_score, validate_ligand_pdbqt, validate_receptor_pdbqt
from backend.services.sse import ProgressEmitter

router = APIRouter()
_VINA_CPU = str(max(1, min((os.cpu_count() or 4) - 1, 8)))

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False


@router.post("/run", response_model=PipelineResponse)
async def run_pipeline(req: PipelineRequest):
    """Full end-to-end pipeline: SMILES → 3D PDB → PDBQT → Vina docking."""
    if not RDKIT_AVAILABLE:
        raise HTTPException(status_code=500, detail="RDKit not installed")

    vina = find_vina()
    if not vina:
        raise HTTPException(status_code=500, detail="Vina executable not found")
    if not os.path.isfile(req.receptor):
        raise HTTPException(status_code=400, detail="Receptor not found")
    if not os.path.isfile(req.config):
        raise HTTPException(status_code=400, detail="Config file not found")
    try:
        validate_receptor_pdbqt(req.receptor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid receptor PDBQT: {exc}") from exc

    name = req.name or "ligand"

    # Work directory = same as config file location
    work_dir = os.path.dirname(req.config) or os.path.dirname(req.receptor) or "."
    pdb_path = os.path.join(work_dir, f"{name}.pdb")
    pdbqt_path = os.path.join(work_dir, f"{name}.pdbqt")
    out_path = os.path.join(work_dir, f"{name}_out.pdbqt")
    job = await job_manager.begin("Auto Pipeline", total=3, message="Preparing pipeline")

    try:
        # Step 1: Generate 3D from SMILES (supports SMILES, InChI, name, CAS, MOL block)
        await job_manager.checkpoint(
            job.id,
            current=0,
            total=3,
            progress=5,
            message=job_progress_message("Pipeline step", f"Generate 3D for {name}", 0, 3),
        )
        from backend.routers.resolve import resolve_to_smiles
        resolved_smiles, _, _ = resolve_to_smiles(req.smiles)
        mol = Chem.MolFromSmiles(resolved_smiles)
        if mol is None:
            raise ValueError("Could not parse resolved SMILES")
        mol = Chem.AddHs(mol)
        embed_result = AllChem.EmbedMolecule(mol, randomSeed=42)
        if embed_result == -1:
            embed_result = AllChem.EmbedMolecule(mol, useRandomCoords=True, randomSeed=42)
        if embed_result == -1:
            raise ValueError("3D embedding failed — molecule may be too constrained")
        AllChem.MMFFOptimizeMolecule(mol)
        Chem.MolToPDBFile(mol, pdb_path)

        # Step 2: Convert PDB → PDBQT
        await job_manager.checkpoint(
            job.id,
            current=1,
            total=3,
            progress=35,
            message=job_progress_message("Pipeline step", f"Convert {os.path.basename(pdb_path)} to PDBQT", 1, 3, "3D generation"),
        )
        ob = get_obabel()
        env = get_obabel_env()
        await job_manager.run_subprocess(
            job.id,
            [ob, pdb_path, "-O", pdbqt_path, "--partialcharge", "gasteiger"],
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            capture_output=False,
            creationflags=_NO_WINDOW,
        )
        validate_ligand_pdbqt(pdbqt_path)

        # Step 3: Run Vina
        await job_manager.checkpoint(
            job.id,
            current=2,
            total=3,
            progress=65,
            message=job_progress_message("Pipeline step", f"Dock {os.path.basename(pdbqt_path)}", 2, 3, "PDBQT conversion"),
        )
        cmd = [
            vina,
            "--config", req.config,
            "--receptor", req.receptor,
            "--ligand", pdbqt_path,
            "--out", out_path,
            "--cpu", _VINA_CPU,
        ]

        p = await job_manager.run_subprocess(
            job.id,
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            creationflags=_NO_WINDOW,
        )
        if p.returncode != 0:
            detail = (p.stderr or p.stdout or "").strip()[-500:]
            raise RuntimeError(detail or f"Vina exited with code {p.returncode}")
        score_value = parse_vina_process_score(p.stdout, p.stderr, out_path)
        if score_value is None:
            raise RuntimeError("Vina completed without a parseable score")
        score = str(score_value)

        await job_manager.finish(job.id, "completed", f"Pipeline complete. Best score: {score} kcal/mol", progress=100)
        return PipelineResponse(
            score=score,
            output_path=out_path,
            message=f"Pipeline complete. Best score: {score} kcal/mol",
        )
    except JobCancelled:
        await job_manager.finish(job.id, "cancelled", "Pipeline cancelled; produced files were kept")
        return PipelineResponse(score=None, output_path=out_path if os.path.exists(out_path) else None, message="Pipeline cancelled")
    except subprocess.TimeoutExpired:
        await job_manager.finish(job.id, "error", "Vina timed out")
        raise HTTPException(status_code=504, detail="Vina timed out (10 min)")
    except HTTPException as exc:
        await job_manager.finish(job.id, "error", str(exc.detail))
        raise
    except Exception as e:
        await job_manager.finish(job.id, "error", f"Pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {e}")


@router.post("/batch", response_model=BatchPipelineResponse)
async def batch_pipeline(req: BatchPipelineRequest):
    """Batch pipeline: SMILES file → 3D gen → minimize → convert → dock all."""
    if not RDKIT_AVAILABLE:
        raise HTTPException(status_code=500, detail="RDKit not installed")
    if not os.path.isfile(req.smiles_file):
        raise HTTPException(status_code=400, detail="SMILES file not found")
    if not os.path.isfile(req.receptor):
        raise HTTPException(status_code=400, detail="Receptor not found")
    if not os.path.isfile(req.config):
        raise HTTPException(status_code=400, detail="Config file not found")
    try:
        validate_receptor_pdbqt(req.receptor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid receptor PDBQT: {exc}") from exc

    vina = find_vina()
    if not vina:
        raise HTTPException(status_code=500, detail="Vina not found")

    ob = get_obabel()
    env = get_obabel_env()

    work_dir = os.path.dirname(req.smiles_file)
    pdb_dir = os.path.join(work_dir, "Batch_3D")
    pdbqt_dir = os.path.join(work_dir, "Batch_PDBQT")
    results_dir = os.path.join(work_dir, "Batch_Docking_Results")
    os.makedirs(pdb_dir, exist_ok=True)
    os.makedirs(pdbqt_dir, exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)

    steps: list[BatchPipelineStep] = []

    entries: list[tuple[str, str]] = []
    with open(req.smiles_file, "r") as f:
        for i, line in enumerate(f):
            parts = line.strip().split()
            if parts:
                smi = parts[0]
                name = parts[1] if len(parts) > 1 else f"mol_{i}"
                entries.append((smi, name))

    total_units = max(1, len(entries) * 3)
    completed_units = 0
    job = await job_manager.begin("Batch Auto Pipeline", total=total_units, message="Preparing batch pipeline")
    gen_count = 0
    conv_count = 0
    dock_count = 0
    dock_failed = 0
    best_score = None

    try:
        last_done: str | None = None
        for idx, (smi, name) in enumerate(entries):
            await job_manager.checkpoint(
                job.id,
                current=completed_units,
                total=total_units,
                progress=int((completed_units / total_units) * 100),
                message=job_progress_message("Generating 3D compound", name, idx, len(entries), last_done),
            )
            try:
                mol = Chem.MolFromSmiles(smi)
                if mol is None:
                    completed_units += 1
                    continue
                mol = Chem.AddHs(mol)
                embed_result = AllChem.EmbedMolecule(mol, randomSeed=42)
                if embed_result == -1:
                    embed_result = AllChem.EmbedMolecule(mol, useRandomCoords=True, randomSeed=42)
                if embed_result == -1:
                    completed_units += 1
                    continue
                if req.force_field == "MMFF94":
                    AllChem.MMFFOptimizeMolecule(mol)
                else:
                    AllChem.UFFOptimizeMolecule(mol)
                pdb_path = os.path.join(pdb_dir, f"{name}.pdb")
                Chem.MolToPDBFile(mol, pdb_path)
                gen_count += 1
                last_done = name
            except Exception:
                last_done = f"{name} failed"
                pass
            completed_units += 1

        steps.append(BatchPipelineStep(step="3D Generation", status="done", count=gen_count))

        pdb_files = [f for f in os.listdir(pdb_dir) if f.endswith(".pdb")]
        last_done = None
        for idx, fname in enumerate(pdb_files):
            await job_manager.checkpoint(
                job.id,
                current=completed_units,
                total=total_units,
                progress=int((completed_units / total_units) * 100),
                message=job_progress_message("Converting ligand", fname, idx, len(pdb_files), last_done),
            )
            pdb_f = os.path.join(pdb_dir, fname)
            pdbqt_f = os.path.join(pdbqt_dir, fname.replace(".pdb", ".pdbqt"))
            try:
                await job_manager.run_subprocess(
                    job.id,
                    [ob, pdb_f, "-O", pdbqt_f, "--partialcharge", "gasteiger"],
                    env=env, check=True, timeout=60,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    capture_output=False,
                    creationflags=_NO_WINDOW,
                )
                validate_ligand_pdbqt(pdbqt_f)
                conv_count += 1
                last_done = fname
            except JobCancelled:
                raise
            except Exception:
                last_done = f"{fname} failed"
                pass
            completed_units += 1

        steps.append(BatchPipelineStep(step="Format Conversion", status="done", count=conv_count))

        pdbqt_files = [f for f in os.listdir(pdbqt_dir) if f.endswith(".pdbqt")]
        last_done = None
        for idx, fname in enumerate(pdbqt_files):
            await job_manager.checkpoint(
                job.id,
                current=completed_units,
                total=total_units,
                progress=int((completed_units / total_units) * 100),
                message=job_progress_message("Docking ligand", fname, idx, len(pdbqt_files), last_done),
            )
            lig_path = os.path.join(pdbqt_dir, fname)
            out_path = os.path.join(results_dir, fname.replace(".pdbqt", "_out.pdbqt"))
            log_path = os.path.join(results_dir, fname.replace(".pdbqt", "_log.log"))

            cmd = [
                vina, "--config", req.config,
                "--receptor", req.receptor,
                "--ligand", lig_path,
                "--out", out_path,
                "--cpu", _VINA_CPU,
            ]
            try:
                p = await job_manager.run_subprocess(
                    job.id,
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=600,
                    creationflags=_NO_WINDOW,
                )
                with open(log_path, "w") as lf:
                    lf.write(p.stdout)
                    if p.stderr:
                        lf.write("\n--- STDERR ---\n")
                        lf.write(p.stderr)
                score = parse_vina_process_score(p.stdout, p.stderr, out_path)
                if p.returncode != 0 or score is None:
                    dock_failed += 1
                    last_done = f"{fname} failed"
                    continue
                if best_score is None or score < best_score:
                    best_score = score
                dock_count += 1
                last_done = f"{fname} ({best_score} best)"
            except JobCancelled:
                raise
            except Exception:
                last_done = f"{fname} failed"
                pass
            completed_units += 1

        steps.append(BatchPipelineStep(step="Docking", status="done", count=dock_count))
        await job_manager.finish(
            job.id,
            "completed",
            f"Batch complete: {dock_count}/{len(entries)} docked, {dock_failed} failed. Best: {best_score} kcal/mol",
            progress=100,
        )
        return BatchPipelineResponse(
            steps=steps,
            results_dir=results_dir,
            total_docked=dock_count,
            failed_docked=dock_failed,
            best_score=best_score,
            message=f"Batch complete: {dock_count}/{len(entries)} docked, {dock_failed} failed. Best: {best_score} kcal/mol",
        )
    except JobCancelled:
        await job_manager.finish(job.id, "cancelled", f"Batch pipeline cancelled: {dock_count} docked")
        return BatchPipelineResponse(
            steps=steps,
            results_dir=results_dir,
            total_docked=dock_count,
            failed_docked=dock_failed,
            best_score=best_score,
            message="Batch pipeline cancelled",
        )
    except Exception as exc:
        await job_manager.finish(job.id, "error", f"Batch pipeline failed: {exc}")
        raise


# ──────────────────────────────────────────────────────────────
# SSE Streaming Variants
# ──────────────────────────────────────────────────────────────

def _sse_format(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


@router.post("/run-stream")
async def run_pipeline_stream(req: PipelineRequest):
    """SSE-streamed single pipeline: SMILES → 3D → PDBQT → Vina docking with live progress."""
    if not RDKIT_AVAILABLE:
        raise HTTPException(status_code=500, detail="RDKit not installed")
    vina = find_vina()
    if not vina:
        raise HTTPException(status_code=500, detail="Vina executable not found")
    if not os.path.isfile(req.receptor):
        raise HTTPException(status_code=400, detail="Receptor not found")
    if not os.path.isfile(req.config):
        raise HTTPException(status_code=400, detail="Config file not found")
    try:
        validate_receptor_pdbqt(req.receptor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid receptor PDBQT: {exc}") from exc

    emitter = ProgressEmitter()

    async def _work():
        try:
            name = req.name or "ligand"
            work_dir = os.path.dirname(req.config) or os.path.dirname(req.receptor) or "."
            pdb_path = os.path.join(work_dir, f"{name}.pdb")
            pdbqt_path = os.path.join(work_dir, f"{name}.pdbqt")
            out_path = os.path.join(work_dir, f"{name}_out.pdbqt")

            # Step 1: 3D generation
            emitter.emit("generate_3d", "Generating 3D structure from SMILES…", progress=10)
            await asyncio.sleep(0)  # yield control

            from backend.routers.resolve import resolve_to_smiles
            resolved_smiles, _, _ = resolve_to_smiles(req.smiles)
            mol = Chem.MolFromSmiles(resolved_smiles)
            if mol is None:
                emitter.error("Could not parse resolved SMILES")
                return
            mol = Chem.AddHs(mol)
            embed_result = AllChem.EmbedMolecule(mol, randomSeed=42)
            if embed_result == -1:
                embed_result = AllChem.EmbedMolecule(mol, useRandomCoords=True, randomSeed=42)
            if embed_result == -1:
                emitter.error("3D embedding failed — molecule may be too constrained")
                return
            AllChem.MMFFOptimizeMolecule(mol)
            Chem.MolToPDBFile(mol, pdb_path)
            emitter.emit("generate_3d", "3D structure generated", progress=30)

            # Step 2: Convert
            emitter.emit("convert", "Converting PDB → PDBQT…", progress=40)
            await asyncio.sleep(0)

            ob = get_obabel()
            env = get_obabel_env()
            proc = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    [ob, pdb_path, "-O", pdbqt_path, "--partialcharge", "gasteiger"],
                    env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=_NO_WINDOW,
                )
            )
            validate_ligand_pdbqt(pdbqt_path)
            emitter.emit("convert", "Format conversion complete", progress=50)

            # Step 3: Dock
            emitter.emit("dock", "Running Vina docking…", progress=60)
            await asyncio.sleep(0)

            cmd = [vina, "--config", req.config, "--receptor", req.receptor,
                   "--ligand", pdbqt_path, "--out", out_path, "--cpu", str(max(1, min((os.cpu_count() or 4) - 1, 8)))]

            p = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=600, creationflags=_NO_WINDOW)
            )

            if p.returncode != 0:
                detail = (p.stderr or p.stdout or "").strip()[-500:]
                emitter.error(detail or f"Vina exited with code {p.returncode}")
                return
            score_value = parse_vina_process_score(p.stdout, p.stderr, out_path)
            if score_value is None:
                emitter.error("Vina completed without a parseable score")
                return
            score = str(score_value)

            emitter.emit("done", f"Pipeline complete. Best score: {score} kcal/mol", progress=100,
                         detail={"score": score, "output_path": out_path})
        except Exception as e:
            emitter.error(str(e))
        finally:
            emitter.close()

    asyncio.create_task(_work())

    async def _generate():
        async for evt in emitter.stream():
            yield _sse_format(evt)

    return StreamingResponse(_generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/batch-stream")
async def batch_pipeline_stream(req: BatchPipelineRequest):
    """SSE-streamed batch pipeline with per-compound progress."""
    if not RDKIT_AVAILABLE:
        raise HTTPException(status_code=500, detail="RDKit not installed")
    if not os.path.isfile(req.smiles_file):
        raise HTTPException(status_code=400, detail="SMILES file not found")
    if not os.path.isfile(req.receptor):
        raise HTTPException(status_code=400, detail="Receptor not found")
    if not os.path.isfile(req.config):
        raise HTTPException(status_code=400, detail="Config file not found")
    try:
        validate_receptor_pdbqt(req.receptor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid receptor PDBQT: {exc}") from exc

    vina = find_vina()
    if not vina:
        raise HTTPException(status_code=500, detail="Vina not found")

    emitter = ProgressEmitter()

    async def _work():
        try:
            ob = get_obabel()
            env = get_obabel_env()

            work_dir = os.path.dirname(req.smiles_file)
            pdb_dir = os.path.join(work_dir, "Batch_3D")
            pdbqt_dir = os.path.join(work_dir, "Batch_PDBQT")
            results_dir = os.path.join(work_dir, "Batch_Docking_Results")
            os.makedirs(pdb_dir, exist_ok=True)
            os.makedirs(pdbqt_dir, exist_ok=True)
            os.makedirs(results_dir, exist_ok=True)

            # Parse entries
            entries: list[tuple[str, str]] = []
            with open(req.smiles_file, "r") as f:
                for i, line in enumerate(f):
                    parts = line.strip().split()
                    if parts:
                        smi = parts[0]
                        name = parts[1] if len(parts) > 1 else f"mol_{i}"
                        entries.append((smi, name))

            total = len(entries)
            emitter.emit("parse", f"Parsed {total} compounds from SMILES file", progress=5, total=total)

            # Step 1: 3D generation
            gen_count = 0
            for idx, (smi, name) in enumerate(entries):
                try:
                    mol = Chem.MolFromSmiles(smi)
                    if mol is None:
                        continue
                    mol = Chem.AddHs(mol)
                    embed_result = AllChem.EmbedMolecule(mol, randomSeed=42)
                    if embed_result == -1:
                        embed_result = AllChem.EmbedMolecule(mol, useRandomCoords=True, randomSeed=42)
                    if embed_result == -1:
                        continue
                    if req.force_field == "MMFF94":
                        AllChem.MMFFOptimizeMolecule(mol)
                    else:
                        AllChem.UFFOptimizeMolecule(mol)
                    pdb_path = os.path.join(pdb_dir, f"{name}.pdb")
                    Chem.MolToPDBFile(mol, pdb_path)
                    gen_count += 1
                except Exception:
                    continue

                if (idx + 1) % 5 == 0 or idx == total - 1:
                    pct = int(5 + (idx + 1) / total * 25)
                    emitter.emit("generate_3d", f"3D generation: {gen_count}/{idx + 1}",
                                 progress=pct, count=gen_count, total=total)
                    await asyncio.sleep(0)

            emitter.emit("generate_3d", f"3D generation complete: {gen_count} molecules", progress=30, count=gen_count)

            # Step 2: Conversion
            pdb_files = [f for f in os.listdir(pdb_dir) if f.endswith(".pdb")]
            conv_count = 0
            for idx, fname in enumerate(pdb_files):
                pdb_f = os.path.join(pdb_dir, fname)
                pdbqt_f = os.path.join(pdbqt_dir, fname.replace(".pdb", ".pdbqt"))
                try:
                    subprocess.run(
                        [ob, pdb_f, "-O", pdbqt_f, "--partialcharge", "gasteiger"],
                        env=env, check=True, timeout=60,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=_NO_WINDOW,
                    )
                    validate_ligand_pdbqt(pdbqt_f)
                    conv_count += 1
                except Exception:
                    continue

                if (idx + 1) % 5 == 0 or idx == len(pdb_files) - 1:
                    pct = int(30 + (idx + 1) / len(pdb_files) * 20)
                    emitter.emit("convert", f"Conversion: {conv_count}/{idx + 1}",
                                 progress=pct, count=conv_count, total=len(pdb_files))
                    await asyncio.sleep(0)

            emitter.emit("convert", f"Conversion complete: {conv_count} files", progress=50, count=conv_count)

            # Step 3: Docking
            pdbqt_files = [f for f in os.listdir(pdbqt_dir) if f.endswith(".pdbqt")]
            dock_count = 0
            dock_failed = 0
            best_score = None

            for idx, fname in enumerate(pdbqt_files):
                lig_path = os.path.join(pdbqt_dir, fname)
                out_path = os.path.join(results_dir, fname.replace(".pdbqt", "_out.pdbqt"))

                cmd = [vina, "--config", req.config, "--receptor", req.receptor,
                       "--ligand", lig_path, "--out", out_path, "--cpu", str(max(1, min((os.cpu_count() or 4) - 1, 8)))]
                try:
                    p = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda c=cmd: subprocess.run(
                            c, capture_output=True, text=True, timeout=600, creationflags=_NO_WINDOW
                        )
                    )
                    score = parse_vina_process_score(p.stdout, p.stderr, out_path)
                    if p.returncode != 0 or score is None:
                        dock_failed += 1
                        continue
                    if best_score is None or score < best_score:
                        best_score = score
                    dock_count += 1
                except Exception:
                    continue

                pct = int(50 + (idx + 1) / len(pdbqt_files) * 45)
                emitter.emit("dock", f"Docking: {dock_count}/{idx + 1} — {fname}",
                             progress=pct, count=dock_count, total=len(pdbqt_files),
                             detail={"ligand": fname, "best_score": best_score})
                await asyncio.sleep(0)

            emitter.emit("done",
                         f"Batch complete: {dock_count}/{total} docked, {dock_failed} failed. Best: {best_score} kcal/mol",
                         progress=100, count=dock_count, total=total,
                         detail={"results_dir": results_dir, "best_score": best_score, "total_docked": dock_count, "failed": dock_failed})
        except Exception as e:
            emitter.error(str(e))
        finally:
            emitter.close()

    asyncio.create_task(_work())

    async def _generate():
        async for evt in emitter.stream():
            yield _sse_format(evt)

    return StreamingResponse(_generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
