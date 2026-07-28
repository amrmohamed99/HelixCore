"""
Report router — generate PDF and HTML reports from screening data.
"""

import os
import json
import time
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.models.schemas import ReportRequest, ReportResponse
from backend.config import WORKSPACE_DIR

router = APIRouter()


def _collect_results_data(results_dir: str) -> list[dict]:
    """Scan a docking results directory and collect candidate data."""
    sections: list[dict] = []
    candidates = []

    if not os.path.isdir(results_dir):
        return sections

    for fname in sorted(os.listdir(results_dir)):
        if fname.endswith("_out.pdbqt"):
            name = fname.replace("_out.pdbqt", "")
            log_path = os.path.join(results_dir, fname.replace("_out.pdbqt", "_log.log"))
            score = None
            if os.path.isfile(log_path):
                with open(log_path, "r") as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) >= 2 and parts[0] == "1":
                            try:
                                score = float(parts[1])
                            except ValueError:
                                pass
                            break
            candidates.append({"name": name, "score": score})

    if candidates:
        candidates.sort(key=lambda c: c.get("score") or 999)
        sections.append({
            "title": "Docking Results Summary",
            "type": "stats",
            "data": {
                "Total Candidates": len(candidates),
                "Best Score": f"{candidates[0]['score']:.2f} kcal/mol" if candidates[0].get("score") else "N/A",
                "≤ -6 kcal/mol": sum(1 for c in candidates if c.get("score") and c["score"] <= -6),
                "≤ -8 kcal/mol": sum(1 for c in candidates if c.get("score") and c["score"] <= -8),
            },
        })
        sections.append({
            "title": "Ranked Candidates",
            "type": "table",
            "data": {
                "headers": ["Rank", "Ligand", "Score (kcal/mol)"],
                "rows": [
                    [i + 1, c["name"], f"{c['score']:.2f}" if c.get("score") else "—"]
                    for i, c in enumerate(candidates)
                ],
            },
        })

    return sections


@router.post("/generate", response_model=ReportResponse)
async def generate_report(req: ReportRequest):
    """Generate a PDF or HTML report from screening results."""
    output_dir = req.output_dir or os.path.join(WORKSPACE_DIR, "reports")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    sections = req.sections or []

    # If results_dir is provided, auto-collect data
    if req.results_dir:
        auto_sections = _collect_results_data(req.results_dir)
        sections = auto_sections + sections

    # Add any custom sections
    if req.custom_text:
        sections.append({"title": "Notes", "type": "text", "data": req.custom_text})

    metadata = {
        "project": req.project_name or "",
        "author": req.author or "",
    }

    paths: list[str] = []

    if req.format in ("pdf", "both"):
        try:
            from backend.services.report_builder import generate_pdf_report
            pdf_path = os.path.join(output_dir, f"report_{timestamp}.pdf")
            generate_pdf_report(pdf_path, title=req.title or "Helix Core Report", sections=sections, metadata=metadata)
            paths.append(pdf_path)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}")

    if req.format in ("html", "both"):
        try:
            from backend.services.report_builder import generate_html_report
            html_path = os.path.join(output_dir, f"report_{timestamp}.html")
            generate_html_report(html_path, title=req.title or "Helix Core Report", sections=sections, metadata=metadata)
            paths.append(html_path)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"HTML generation failed: {exc}")

    return ReportResponse(
        paths=paths,
        message=f"Generated {len(paths)} report(s)",
    )


@router.get("/download")
async def download_report(path: str):
    """Download a generated report file."""
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Report file not found")

    ext = os.path.splitext(path)[1].lower()
    media = "application/pdf" if ext == ".pdf" else "text/html"
    return FileResponse(path, media_type=media, filename=os.path.basename(path))
