"""
System router — health, stats, version, molecule rendering, structure file serving.
"""

import os
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, PlainTextResponse

router = APIRouter()

try:
    import psutil
    SYS_AVAILABLE = True
except ImportError:
    SYS_AVAILABLE = False

try:
    from rdkit import Chem
    from rdkit.Chem import Draw
    RDKIT_DRAW_AVAILABLE = True
except ImportError:
    RDKIT_DRAW_AVAILABLE = False


@router.get("/stats")
async def system_stats():
    """Return CPU and RAM utilization."""
    if not SYS_AVAILABLE:
        return {"cpu_percent": 0, "ram_percent": 0, "cores": 0, "ram_total_gb": 0}

    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    return {
        "cpu_percent": cpu,
        "ram_percent": mem.percent,
        "cores": psutil.cpu_count(logical=True),
        "ram_total_gb": round(mem.total / (1024**3), 1),
    }


@router.get("/mol-svg")
async def molecule_svg(
    smiles: str = Query(..., description="SMILES string to render"),
    width: int = Query(250, ge=50, le=800),
    height: int = Query(200, ge=50, le=800),
):
    """Render a molecule as SVG — accepts SMILES, InChI, compound name, or CAS number."""
    if not RDKIT_DRAW_AVAILABLE:
        raise HTTPException(status_code=503, detail="RDKit Draw module not available")

    # Use universal resolver
    try:
        from backend.routers.resolve import resolve_to_smiles
        resolved_smiles, _, _ = resolve_to_smiles(smiles)
        mol = Chem.MolFromSmiles(resolved_smiles)
    except Exception:
        mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise HTTPException(status_code=400, detail="Could not resolve molecule")

    drawer = Draw.MolDraw2DSVG(width, height)
    drawer.drawOptions().clearBackground = False
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    svg = drawer.GetDrawingText()

    return Response(content=svg, media_type="image/svg+xml")


# ──── Allowed extensions for 3D structure serving ────
_STRUCTURE_EXTENSIONS = {'.pdb', '.pdbqt', '.mol2', '.sdf', '.mol', '.cif', '.mmcif'}


@router.get("/structure-file")
async def serve_structure_file(
    path: str = Query(..., description="Absolute path to a structure file"),
):
    """Serve a local structure file (PDB/PDBQT/MOL2/SDF/CIF) as plain text for the 3D viewer."""
    if not os.path.isabs(path):
        raise HTTPException(status_code=400, detail="Path must be absolute")

    ext = os.path.splitext(path)[1].lower()
    if ext not in _STRUCTURE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Structure file not found")

    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not read file: {exc}")

    return PlainTextResponse(content=content, headers={
        "Access-Control-Allow-Origin": "*",
    })
