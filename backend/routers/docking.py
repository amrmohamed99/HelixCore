"""
Virtual Screening / Docking router — sequential Vina pipeline + auto-grid.
Supports both REST (POST /run) and WebSocket-streamed progress (POST /run-ws).
"""

import os
import subprocess
import asyncio
import uuid
import logging
from fastapi import APIRouter, HTTPException

_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

from backend.config import find_vina
from backend.models.schemas import (
    DockingRequest,
    DockingResult,
    DockingResponse,
    AutoGridRequest,
    GridBox,
    PoseDecompRequest,
    PoseDecompResponse,
    EnergyComponent,
    MultiTargetRequest,
    MultiTargetResult,
    MultiTargetResponse,
)
from backend.utils.pdbqt_utils import (
    parse_atom_coords,
    parse_vina_process_score,
    validate_ligand_pdbqt,
    validate_receptor_pdbqt,
)
from backend.services.job_manager import JobCancelled, job_manager, job_progress_message
from backend.services.ws_manager import ws_manager, TaskStatus
from backend.utils.file_order import sorted_matching_files

router = APIRouter()
logger = logging.getLogger(__name__)

# Dynamic CPU allocation: leave 1 core for system, cap at 8 (diminishing returns beyond)
_VINA_CPU = str(max(1, min((os.cpu_count() or 4) - 1, 8)))

# Maximum grid dimension supported by AutoDock Vina (Å)
_MAX_GRID_DIM = 126.0


def _validate_receptor(path: str) -> None:
    """Raise HTTPException if the receptor PDBQT contains ligand-format tags."""
    try:
        validate_receptor_pdbqt(path)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{exc}. Re-prepare the receptor using Prepare Receptor.",
        ) from exc


@router.post("/run", response_model=DockingResponse)
async def run_docking(req: DockingRequest):
    """Run sequential Vina docking on all .pdbqt ligands in a folder."""
    vina = find_vina()
    if not vina:
        raise HTTPException(status_code=500, detail="Vina executable not found")
    if not os.path.isdir(req.ligands_dir):
        raise HTTPException(status_code=400, detail="Ligands directory not found")
    if not os.path.isfile(req.receptor):
        raise HTTPException(status_code=400, detail="Receptor file not found")
    _validate_receptor(req.receptor)

    # Prepare config
    conf_path = req.config_path
    if not conf_path and req.grid:
        max_dim = max(req.grid.size_x, req.grid.size_y, req.grid.size_z)
        if max_dim > 80:
            logger.warning("Grid dimension %.1fÅ exceeds 80Å — docking accuracy may be reduced (Feinstein & Brylinski 2015)", max_dim)
        conf_path = os.path.join(req.ligands_dir, "auto_config.txt")
        with open(conf_path, "w") as f:
            f.write(f"center_x = {req.grid.center_x}\n")
            f.write(f"center_y = {req.grid.center_y}\n")
            f.write(f"center_z = {req.grid.center_z}\n")
            f.write(f"size_x = {req.grid.size_x}\n")
            f.write(f"size_y = {req.grid.size_y}\n")
            f.write(f"size_z = {req.grid.size_z}\n")
            f.write(f"exhaustiveness = {req.exhaustiveness}\n")
            f.write(f"seed = {req.seed}\n")

    if not conf_path or not os.path.isfile(conf_path):
        raise HTTPException(status_code=400, detail="No config file provided or generated")

    # Results folder
    res_dir = os.path.join(req.ligands_dir, "Docking_Results")
    os.makedirs(res_dir, exist_ok=True)

    rec_basename = os.path.basename(req.receptor)
    files = sorted_matching_files(
        req.ligands_dir,
        (".pdbqt",),
        exclude=(rec_basename,),
    )

    results: list[DockingResult] = []
    job = await job_manager.begin("Molecular Docking", total=len(files), message="Preparing docking run")

    try:
        last_done: str | None = None
        for idx, fname in enumerate(files):
            await job_manager.checkpoint(
                job.id,
                current=idx,
                total=len(files),
                progress=int((idx / max(len(files), 1)) * 100),
                message=job_progress_message("Docking ligand", fname, idx, len(files), last_done),
            )
            lig_path = os.path.join(req.ligands_dir, fname)
            out_path = os.path.join(res_dir, fname.replace(".pdbqt", "_out.pdbqt"))
            log_path = os.path.join(res_dir, fname.replace(".pdbqt", "_log.log"))

            try:
                validate_ligand_pdbqt(lig_path)
            except ValueError as exc:
                results.append(
                    DockingResult(
                        ligand=fname,
                        status="error",
                        error_detail=f"Invalid ligand PDBQT: {exc}",
                    )
                )
                last_done = f"{fname} invalid"
                continue

            cmd = [
                vina,
                "--config", conf_path,
                "--receptor", req.receptor,
                "--ligand", lig_path,
                "--out", out_path,
                "--cpu", _VINA_CPU,
                "--seed", str(req.seed),
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

                # Save log (stdout + stderr for diagnostics)
                with open(log_path, "w") as lf:
                    lf.write(p.stdout)
                    if p.stderr:
                        lf.write("\n--- STDERR ---\n")
                        lf.write(p.stderr)

                # Parse stdout, stderr, then the output PDBQT REMARK.
                score = parse_vina_process_score(p.stdout, p.stderr, out_path)

                err_detail = None
                if p.returncode != 0:
                    err_detail = (p.stderr or p.stdout or "").strip()[-500:] or f"Vina exited with code {p.returncode}"

                results.append(
                    DockingResult(
                        ligand=fname,
                        score=score,
                        output_path=out_path,
                        status="ok" if p.returncode == 0 else "error",
                        error_detail=err_detail,
                    )
                )
                if score is not None:
                    last_done = f"{fname} ({score} kcal/mol)"
                else:
                    last_done = fname
            except JobCancelled:
                raise
            except subprocess.TimeoutExpired:
                results.append(
                    DockingResult(ligand=fname, status="error", error_detail="Timed out after 600s")
                )
                last_done = f"{fname} timed out"
            except Exception as exc:
                results.append(
                    DockingResult(ligand=fname, status="error", error_detail=str(exc)[:500])
                )
                last_done = f"{fname} failed"

        await job_manager.finish(job.id, "completed", f"Docking complete: {len(results)} ligands", progress=100)
        return DockingResponse(results=results, results_dir=res_dir)
    except JobCancelled:
        await job_manager.finish(job.id, "cancelled", f"Docking cancelled: {len(results)} ligands processed")
        return DockingResponse(results=results, results_dir=res_dir)
    except Exception as exc:
        await job_manager.finish(job.id, "error", f"Docking failed: {exc}")
        raise


@router.post("/run-ws", response_model=DockingResponse)
async def run_docking_ws(req: DockingRequest):
    """Run Vina docking with real-time WebSocket progress updates.

    Same as /run but emits per-ligand progress via the WS manager.
    The task_id is returned in the response so the client can track it.
    """
    vina = find_vina()
    if not vina:
        raise HTTPException(status_code=500, detail="Vina executable not found")
    if not os.path.isdir(req.ligands_dir):
        raise HTTPException(status_code=400, detail="Ligands directory not found")
    if not os.path.isfile(req.receptor):
        raise HTTPException(status_code=400, detail="Receptor file not found")
    _validate_receptor(req.receptor)

    conf_path = req.config_path
    if not conf_path and req.grid:
        conf_path = os.path.join(req.ligands_dir, "auto_config.txt")
        with open(conf_path, "w") as f:
            f.write(f"center_x = {req.grid.center_x}\n")
            f.write(f"center_y = {req.grid.center_y}\n")
            f.write(f"center_z = {req.grid.center_z}\n")
            f.write(f"size_x = {req.grid.size_x}\n")
            f.write(f"size_y = {req.grid.size_y}\n")
            f.write(f"size_z = {req.grid.size_z}\n")
            f.write(f"exhaustiveness = {req.exhaustiveness}\n")
            f.write(f"seed = {req.seed}\n")

    if not conf_path or not os.path.isfile(conf_path):
        raise HTTPException(status_code=400, detail="No config file provided or generated")

    res_dir = os.path.join(req.ligands_dir, "Docking_Results")
    os.makedirs(res_dir, exist_ok=True)

    rec_basename = os.path.basename(req.receptor)
    files = sorted_matching_files(
        req.ligands_dir,
        (".pdbqt",),
        exclude=(rec_basename,),
    )

    task_id = str(uuid.uuid4())
    task = ws_manager.create_task(task_id, total=len(files), label="Docking")
    task.status = TaskStatus.RUNNING
    task.started_at = __import__('time').time()

    results: list[DockingResult] = []

    try:
        for idx, fname in enumerate(files):
            # Check cancellation
            if task.is_cancelled:
                task.message = "Cancelled by user"
                await ws_manager.emit_progress(task)
                break

            # Wait if paused
            await task.wait_if_paused()

            # Check skip
            if task.should_skip:
                results.append(DockingResult(ligand=fname, status="skipped"))
                task.current = idx + 1
                task.message = f"Skipped {fname}"
                await ws_manager.emit_progress(task)
                continue

            task.current = idx
            task.message = f"Docking {fname} ({idx + 1}/{len(files)})"
            task.detail = {"ligand": fname}
            await ws_manager.emit_progress(task)

            lig_path = os.path.join(req.ligands_dir, fname)
            out_path = os.path.join(res_dir, fname.replace(".pdbqt", "_out.pdbqt"))
            log_path = os.path.join(res_dir, fname.replace(".pdbqt", "_log.log"))

            cmd = [
                vina,
                "--config", conf_path,
                "--receptor", req.receptor,
                "--ligand", lig_path,
                "--out", out_path,
                "--cpu", _VINA_CPU,
                "--seed", str(req.seed),
            ]

            try:
                validate_ligand_pdbqt(lig_path)
                p = await asyncio.to_thread(
                    subprocess.run, cmd, capture_output=True, text=True, timeout=600, creationflags=_NO_WINDOW
                )
                with open(log_path, "w") as lf:
                    lf.write(p.stdout)
                    if p.stderr:
                        lf.write("\n--- STDERR ---\n")
                        lf.write(p.stderr)

                score = parse_vina_process_score(p.stdout, p.stderr, out_path)

                err_detail = None
                if p.returncode != 0:
                    err_detail = (p.stderr or p.stdout or "").strip()[-500:] or f"Vina exited with code {p.returncode}"

                results.append(DockingResult(ligand=fname, score=score, output_path=out_path, status="ok" if p.returncode == 0 else "error", error_detail=err_detail))
            except subprocess.TimeoutExpired:
                results.append(DockingResult(ligand=fname, status="error", error_detail="Timed out after 600s"))
            except Exception as exc:
                results.append(DockingResult(ligand=fname, status="error", error_detail=str(exc)[:500]))

            task.current = idx + 1
            task.message = f"Completed {fname}"
            await ws_manager.emit_progress(task)

        response = DockingResponse(results=results, results_dir=res_dir)
        await ws_manager.emit_complete(task, {"results_dir": res_dir, "total": len(results)})
        return response

    except Exception as exc:
        await ws_manager.emit_error(task, str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        ws_manager.remove_task(task_id)


@router.post("/auto-grid", response_model=GridBox)
async def auto_calculate_grid(req: AutoGridRequest):
    """Calculate grid box from all ATOM/HETATM coordinates in a receptor file."""
    if not os.path.isfile(req.receptor_path):
        raise HTTPException(status_code=400, detail="Receptor file not found")

    coords = parse_atom_coords(req.receptor_path)
    if not coords:
        raise HTTPException(status_code=400, detail="No atoms found in receptor")

    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    zs = [c[2] for c in coords]

    raw_sizes = {
        "x": (max(xs) - min(xs)) + req.padding,
        "y": (max(ys) - min(ys)) + req.padding,
        "z": (max(zs) - min(zs)) + req.padding,
    }
    oversized = {axis: round(size, 3) for axis, size in raw_sizes.items() if size > _MAX_GRID_DIM}
    if oversized:
        dimensions = ", ".join(f"{axis}={size} Å" for axis, size in oversized.items())
        raise HTTPException(
            status_code=400,
            detail=(
                f"Auto-calculated grid exceeds AutoDock Vina's {_MAX_GRID_DIM:g} Å maximum "
                f"({dimensions}). Reduce padding or provide a manual grid focused on the binding site."
            ),
        )

    return GridBox(
        center_x=round((min(xs) + max(xs)) / 2, 3),
        center_y=round((min(ys) + max(ys)) / 2, 3),
        center_z=round((min(zs) + max(zs)) / 2, 3),
        size_x=round(raw_sizes["x"], 3),
        size_y=round(raw_sizes["y"], 3),
        size_z=round(raw_sizes["z"], 3),
    )


@router.post("/decompose", response_model=PoseDecompResponse)
async def decompose_pose(req: PoseDecompRequest):
    """Parse a Vina log file and extract energy decomposition components."""
    if not os.path.isfile(req.log_path):
        raise HTTPException(status_code=400, detail="Log file not found")

    ligand_name = os.path.basename(req.log_path).replace("_log.log", "").replace(".log", "")
    total_score = None
    components: list[EnergyComponent] = []

    with open(req.log_path, "r") as f:
        content = f.read()

    for line in content.splitlines():
        stripped = line.strip()

        parts = stripped.split()
        if len(parts) >= 4 and parts[0] == "1":
            try:
                total_score = float(parts[1])
                components.append(EnergyComponent(component="best_affinity", value=float(parts[1])))
                if len(parts) >= 3:
                    components.append(EnergyComponent(component="dist_from_rmsd_lb", value=float(parts[2])))
                if len(parts) >= 4:
                    components.append(EnergyComponent(component="dist_from_rmsd_ub", value=float(parts[3])))
            except (ValueError, IndexError):
                pass

        if "Intermolecular" in stripped and ":" in stripped:
            try:
                val = float(stripped.split(":")[-1].strip().split()[0])
                components.append(EnergyComponent(component="intermolecular", value=val))
            except (ValueError, IndexError):
                pass

        if "Internal" in stripped and ":" in stripped:
            try:
                val = float(stripped.split(":")[-1].strip().split()[0])
                components.append(EnergyComponent(component="internal", value=val))
            except (ValueError, IndexError):
                pass

        if "Torsional" in stripped and ":" in stripped:
            try:
                val = float(stripped.split(":")[-1].strip().split()[0])
                components.append(EnergyComponent(component="torsional", value=val))
            except (ValueError, IndexError):
                pass

    modes: list[dict] = []
    for line in content.splitlines():
        stripped = line.strip()
        parts = stripped.split()
        if len(parts) >= 4 and parts[0].isdigit():
            try:
                modes.append({
                    "mode": int(parts[0]),
                    "affinity": float(parts[1]),
                    "rmsd_lb": float(parts[2]),
                    "rmsd_ub": float(parts[3]),
                })
            except (ValueError, IndexError):
                pass

    if modes:
        for m in modes[1:]:
            components.append(
                EnergyComponent(
                    component=f"mode_{m['mode']}_affinity",
                    value=m["affinity"],
                )
            )

    return PoseDecompResponse(
        ligand=ligand_name,
        total_score=total_score,
        components=components,
    )


@router.post("/multi-target", response_model=MultiTargetResponse)
async def multi_target_docking(req: MultiTargetRequest):
    """Dock ligands against multiple receptors and build a selectivity matrix."""
    vina = find_vina()
    if not vina:
        raise HTTPException(status_code=500, detail="Vina executable not found")
    if not os.path.isdir(req.ligands_dir):
        raise HTTPException(status_code=400, detail="Ligands directory not found")

    ligand_files = sorted([f for f in os.listdir(req.ligands_dir) if f.endswith(".pdbqt")])
    if not ligand_files:
        raise HTTPException(status_code=400, detail="No PDBQT ligands found in directory")

    results: list[MultiTargetResult] = []
    matrix: dict[str, dict[str, float | None]] = {}

    for rec_idx, receptor_path in enumerate(req.receptors):
        if not os.path.isfile(receptor_path):
            raise HTTPException(status_code=400, detail=f"Receptor not found: {receptor_path}")
        _validate_receptor(receptor_path)

        rec_name = os.path.basename(receptor_path).replace(".pdbqt", "")
        matrix[rec_name] = {}

        # Determine config for this receptor
        conf_path = None
        if req.config_paths:
            idx = min(rec_idx, len(req.config_paths) - 1)
            conf_path = req.config_paths[idx]
        elif req.grids and rec_idx < len(req.grids):
            grid = req.grids[rec_idx]
            conf_path = os.path.join(req.ligands_dir, f"multi_config_{rec_idx}.txt")
            with open(conf_path, "w") as f:
                for k, v in grid.items():
                    f.write(f"{k} = {v}\n")

        # Results directory per receptor
        out_dir = os.path.join(req.ligands_dir, f"multi_target_{rec_name}")
        os.makedirs(out_dir, exist_ok=True)

        for lig_file in ligand_files:
            lig_path = os.path.join(req.ligands_dir, lig_file)
            lig_name = lig_file.replace(".pdbqt", "")
            out_path = os.path.join(out_dir, f"{lig_name}_out.pdbqt")
            log_path = os.path.join(out_dir, f"{lig_name}.log")

            try:
                validate_ligand_pdbqt(lig_path)
            except ValueError as exc:
                results.append(MultiTargetResult(
                    receptor=rec_name, ligand=lig_name,
                    score=None, status=f"error: invalid ligand PDBQT: {exc}",
                ))
                matrix[rec_name][lig_name] = None
                continue

            cmd = [vina, "--receptor", receptor_path, "--ligand", lig_path, "--out", out_path]
            if conf_path:
                cmd += ["--config", conf_path]
            cmd += ["--exhaustiveness", str(req.exhaustiveness), "--seed", str(req.seed)]

            try:
                proc = await asyncio.to_thread(
                    subprocess.run, cmd,
                    capture_output=True, text=True, timeout=300,
                    creationflags=_NO_WINDOW,
                    env=os.environ.copy(),
                )
                score = parse_vina_process_score(proc.stdout, proc.stderr, out_path)

                with open(log_path, "w") as f:
                    f.write(proc.stdout)
                    if proc.stderr:
                        f.write("\n--- STDERR ---\n" + proc.stderr)

                if proc.returncode == 0 and score is not None:
                    status = "ok"
                elif proc.returncode != 0:
                    detail = (proc.stderr or proc.stdout or "").strip()[-300:]
                    status = f"error: {detail or f'Vina exited with code {proc.returncode}'}"
                else:
                    status = "error: Vina completed without a parseable score"
                results.append(MultiTargetResult(
                    receptor=rec_name, ligand=lig_name,
                    score=score, status=status, output_path=out_path if status == "ok" else None,
                ))
                matrix[rec_name][lig_name] = score

            except subprocess.TimeoutExpired:
                results.append(MultiTargetResult(
                    receptor=rec_name, ligand=lig_name,
                    score=None, status="timeout",
                ))
                matrix[rec_name][lig_name] = None
            except Exception as exc:
                results.append(MultiTargetResult(
                    receptor=rec_name, ligand=lig_name,
                    score=None, status=f"error: {exc}",
                ))
                matrix[rec_name][lig_name] = None

    return MultiTargetResponse(
        results=results,
        selectivity_matrix=matrix,
        results_dir=req.ligands_dir,
        message=f"Docked {len(ligand_files)} ligands against {len(req.receptors)} receptors",
    )
