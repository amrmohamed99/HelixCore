"""
Compound Watchlist — track flagged compounds with notes and tags.
Persists to workspace/watchlist.json.
"""

import os
import json
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException

from backend.models.schemas import WatchlistItem
from backend.config import WORKSPACE_DIR

router = APIRouter()

WATCHLIST_PATH = os.path.join(WORKSPACE_DIR, "watchlist.json")


def _load_watchlist() -> list[dict]:
    """Load the watchlist from disk."""
    if not os.path.exists(WATCHLIST_PATH):
        return []
    try:
        with open(WATCHLIST_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_watchlist(items: list[dict]):
    """Persist the watchlist to disk."""
    os.makedirs(os.path.dirname(WATCHLIST_PATH), exist_ok=True)
    with open(WATCHLIST_PATH, "w") as f:
        json.dump(items, f, indent=2)


@router.get("/list")
async def list_watchlist():
    """Return all items on the watchlist."""
    items = _load_watchlist()
    return {"items": items, "count": len(items)}


@router.post("/add")
async def add_to_watchlist(item: WatchlistItem):
    """Add a compound to the watchlist."""
    items = _load_watchlist()

    if not item.id:
        item.id = str(uuid.uuid4())[:8]
    item.added = datetime.now().isoformat()

    for existing in items:
        if existing.get("smiles") == item.smiles:
            raise HTTPException(status_code=409, detail="Compound already on watchlist")

    items.append(item.model_dump())
    _save_watchlist(items)
    return {"status": "added", "id": item.id}


@router.delete("/remove/{item_id}")
async def remove_from_watchlist(item_id: str):
    """Remove a compound from the watchlist by ID."""
    items = _load_watchlist()
    new_items = [i for i in items if i.get("id") != item_id]
    if len(new_items) == len(items):
        raise HTTPException(status_code=404, detail="Item not found")
    _save_watchlist(new_items)
    return {"status": "removed", "id": item_id}


@router.put("/update")
async def update_watchlist_item(item: WatchlistItem):
    """Update an existing watchlist item (notes, tags, flag)."""
    if not item.id:
        raise HTTPException(status_code=400, detail="Item ID required for update")

    items = _load_watchlist()
    found = False
    for i, existing in enumerate(items):
        if existing.get("id") == item.id:
            data = item.model_dump()
            data["added"] = existing.get("added", datetime.now().isoformat())
            items[i] = data
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail="Item not found")

    _save_watchlist(items)
    return {"status": "updated", "id": item.id}
