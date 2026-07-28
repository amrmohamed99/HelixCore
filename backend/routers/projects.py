"""
Project Management — persists named projects with workspace paths,
compound lists, and notes to JSON files in workspace/projects/.
"""

import os
import json
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException

from backend.models.schemas import Project
from backend.config import WORKSPACE_DIR

router = APIRouter()

PROJECTS_DIR = os.path.join(WORKSPACE_DIR, "projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)


def _project_path(project_id: str) -> str:
    """Return full path for a project JSON file."""
    return os.path.join(PROJECTS_DIR, f"{project_id}.json")


@router.get("/list")
async def list_projects():
    """List all saved projects."""
    projects: list[dict] = []
    for fname in sorted(os.listdir(PROJECTS_DIR)):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(PROJECTS_DIR, fname), "r") as f:
                    p = json.load(f)
                    projects.append(p)
            except (json.JSONDecodeError, OSError):
                continue
    return {"projects": projects, "count": len(projects)}


@router.post("/save")
async def save_project(project: Project):
    """Create or overwrite a named project."""
    if not project.id:
        project.id = str(uuid.uuid4())[:8]
    project.updated = datetime.now().isoformat()
    if not project.created:
        project.created = project.updated

    data = project.model_dump()
    with open(_project_path(project.id), "w") as f:
        json.dump(data, f, indent=2)

    return {"status": "saved", "id": project.id}


@router.get("/load/{project_id}")
async def load_project(project_id: str):
    """Load a single project by ID."""
    path = _project_path(project_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Project not found")
    with open(path, "r") as f:
        return json.load(f)


@router.delete("/delete/{project_id}")
async def delete_project(project_id: str):
    """Delete a project by ID."""
    path = _project_path(project_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Project not found")
    os.remove(path)
    return {"status": "deleted", "id": project_id}
