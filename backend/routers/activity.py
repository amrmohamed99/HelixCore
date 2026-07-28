"""
Activity Log — persistent action audit trail.
Stores activity entries as newline-delimited JSON in workspace/activity.jsonl.
"""

import os
import json
from datetime import datetime
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.config import WORKSPACE_DIR

router = APIRouter()

ACTIVITY_FILE = os.path.join(WORKSPACE_DIR, "activity.jsonl")


class ActivityEntry(BaseModel):
    """A single activity log entry."""
    action: str = Field(..., description="Short action description")
    page: str = Field("", description="Page where the action occurred")
    details: dict | None = Field(None, description="Additional structured data")
    duration_ms: int | None = Field(None, description="Duration of the action in ms")


class ActivityRecord(ActivityEntry):
    """Entry with server-assigned timestamp and id."""
    id: int = 0
    timestamp: str = ""


@router.post("/log")
async def log_activity(entry: ActivityEntry):
    """Append an activity entry to the log file."""
    record = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": entry.action,
        "page": entry.page,
        "details": entry.details,
        "duration_ms": entry.duration_ms,
    }
    os.makedirs(os.path.dirname(ACTIVITY_FILE), exist_ok=True)
    with open(ACTIVITY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return {"status": "logged"}


@router.get("/list")
async def list_activities(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    filter_page: str | None = Query(None, alias="filterPage"),
):
    """Read activity entries with pagination and optional page filter."""
    if not os.path.exists(ACTIVITY_FILE):
        return {"entries": [], "total": 0, "page": page, "per_page": per_page}

    entries: list[dict] = []
    with open(ACTIVITY_FILE, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                record["id"] = i + 1
                if filter_page and record.get("page", "") != filter_page:
                    continue
                entries.append(record)
            except json.JSONDecodeError:
                continue

    # Newest first
    entries.reverse()
    total = len(entries)
    start = (page - 1) * per_page
    end = start + per_page

    return {
        "entries": entries[start:end],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.post("/clear")
async def clear_activity():
    """Clear all activity log entries."""
    if os.path.exists(ACTIVITY_FILE):
        os.remove(ACTIVITY_FILE)
    return {"status": "cleared"}


@router.get("/export")
async def export_activity():
    """Return the raw JSONL content for download."""
    if not os.path.exists(ACTIVITY_FILE):
        return {"content": "", "filename": "activity.jsonl"}
    with open(ACTIVITY_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    return {"content": content, "filename": "activity.jsonl"}
