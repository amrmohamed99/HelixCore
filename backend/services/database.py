"""
SQLite Database Service — persistent storage with auto-migration from JSON.

Provides async context manager for database access, schema versioning,
and automatic migration of existing JSON project/watchlist/activity data.
"""

import os
import json
import logging
from datetime import datetime

from backend.config import WORKSPACE_DIR

try:
    import aiosqlite
    AIOSQLITE_AVAILABLE = True
except ImportError:
    AIOSQLITE_AVAILABLE = False

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(WORKSPACE_DIR, "helix_core.db")

# Current schema version — bump when tables change
SCHEMA_VERSION = 1

# DDL statements for table creation
_CREATE_TABLES = """

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    description TEXT DEFAULT '',
    receptor    TEXT DEFAULT '',
    ligands_dir TEXT DEFAULT '',
    results_dir TEXT DEFAULT '',
    notes       TEXT DEFAULT '',
    compounds   TEXT DEFAULT '[]',
    created     TEXT NOT NULL,
    updated     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    id       TEXT PRIMARY KEY,
    smiles   TEXT NOT NULL,
    name     TEXT DEFAULT '',
    notes    TEXT DEFAULT '',
    tags     TEXT DEFAULT '[]',
    flag     TEXT DEFAULT 'none',
    added    TEXT NOT NULL,
    score    REAL DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS activity_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action    TEXT NOT NULL,
    detail    TEXT DEFAULT '',
    page      TEXT DEFAULT '',
    project   TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS docking_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    TEXT,
    receptor_path TEXT NOT NULL,
    ligand_name   TEXT NOT NULL,
    score         REAL,
    output_path   TEXT,
    config        TEXT DEFAULT '{}',
    timestamp     TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS compound_cache (
    smiles    TEXT PRIMARY KEY,
    name      TEXT DEFAULT '',
    mw        REAL DEFAULT NULL,
    logp      REAL DEFAULT NULL,
    hbd       INTEGER DEFAULT NULL,
    hba       INTEGER DEFAULT NULL,
    tpsa      REAL DEFAULT NULL,
    rule_of_5 TEXT DEFAULT NULL,
    admet     TEXT DEFAULT '{}',
    updated   TEXT NOT NULL
);
"""


async def get_db() -> "aiosqlite.Connection":
    """Open a connection (caller must close/use as context manager)."""
    if not AIOSQLITE_AVAILABLE:
        raise RuntimeError("aiosqlite is not installed")
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_database():
    """Create tables if they don't exist and run migrations."""
    if not AIOSQLITE_AVAILABLE:
        logger.warning("aiosqlite not available — SQLite backend disabled")
        return

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript(_CREATE_TABLES)

        # Check / set schema version
        cursor = await db.execute("SELECT version FROM schema_version LIMIT 1")
        row = await cursor.fetchone()
        if row is None:
            await db.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        await db.commit()

    # Auto-migrate JSON data if not already done
    await _migrate_json_projects()
    await _migrate_json_watchlist()
    await _migrate_json_activity()
    logger.info(f"Database initialized at {DB_PATH}")


async def _migrate_json_projects():
    """Import existing JSON project files into SQLite."""
    projects_dir = os.path.join(WORKSPACE_DIR, "projects")
    if not os.path.isdir(projects_dir):
        return

    async with aiosqlite.connect(DB_PATH) as db:
        for fname in os.listdir(projects_dir):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(projects_dir, fname), "r") as f:
                    p = json.load(f)
                pid = p.get("id", fname.replace(".json", ""))
                # Check if already migrated
                cursor = await db.execute("SELECT id FROM projects WHERE id = ?", (pid,))
                if await cursor.fetchone():
                    continue
                await db.execute(
                    "INSERT INTO projects (id, name, description, receptor, ligands_dir, results_dir, notes, compounds, created, updated) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        pid,
                        p.get("name", ""),
                        p.get("description", ""),
                        p.get("receptor", ""),
                        p.get("ligands_dir", ""),
                        p.get("results_dir", ""),
                        p.get("notes", ""),
                        json.dumps(p.get("compounds", [])),
                        p.get("created", datetime.now().isoformat()),
                        p.get("updated", datetime.now().isoformat()),
                    )
                )
            except (json.JSONDecodeError, OSError, Exception) as exc:
                logger.warning(f"Failed to migrate project {fname}: {exc}")
        await db.commit()


async def _migrate_json_watchlist():
    """Import existing watchlist.json into SQLite."""
    watchlist_path = os.path.join(WORKSPACE_DIR, "watchlist.json")
    if not os.path.exists(watchlist_path):
        return

    try:
        with open(watchlist_path, "r") as f:
            items = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    async with aiosqlite.connect(DB_PATH) as db:
        for item in items:
            wid = item.get("id", "")
            if not wid:
                continue
            cursor = await db.execute("SELECT id FROM watchlist WHERE id = ?", (wid,))
            if await cursor.fetchone():
                continue
            try:
                await db.execute(
                    "INSERT INTO watchlist (id, smiles, name, notes, tags, flag, added, score) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        wid,
                        item.get("smiles", ""),
                        item.get("name", ""),
                        item.get("notes", ""),
                        json.dumps(item.get("tags", [])),
                        item.get("flag", "none"),
                        item.get("added", datetime.now().isoformat()),
                        item.get("score"),
                    )
                )
            except Exception as exc:
                logger.warning(f"Failed to migrate watchlist item: {exc}")
        await db.commit()


async def _migrate_json_activity():
    """Import existing activity log JSON into SQLite."""
    activity_path = os.path.join(WORKSPACE_DIR, "activity.json")
    if not os.path.exists(activity_path):
        return

    try:
        with open(activity_path, "r") as f:
            entries = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    async with aiosqlite.connect(DB_PATH) as db:
        for entry in entries:
            try:
                await db.execute(
                    "INSERT INTO activity_log (timestamp, action, detail, page, project) VALUES (?, ?, ?, ?, ?)",
                    (
                        entry.get("timestamp", datetime.now().isoformat()),
                        entry.get("action", ""),
                        entry.get("detail", ""),
                        entry.get("page", ""),
                        entry.get("project", ""),
                    )
                )
            except Exception:
                continue
        await db.commit()


# ──── CRUD helpers ────

async def save_docking_result(
    receptor_path: str,
    ligand_name: str,
    score: float | None,
    output_path: str | None,
    config: dict | None = None,
    project_id: str | None = None,
):
    """Record a docking result in the database."""
    if not AIOSQLITE_AVAILABLE:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO docking_history (project_id, receptor_path, ligand_name, score, output_path, config, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, receptor_path, ligand_name, score, output_path, json.dumps(config or {}), datetime.now().isoformat())
        )
        await db.commit()


async def cache_compound(smiles: str, properties: dict):
    """Cache computed compound properties (ADMET, Ro5, etc.)."""
    if not AIOSQLITE_AVAILABLE:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO compound_cache (smiles, name, mw, logp, hbd, hba, tpsa, rule_of_5, admet, updated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                smiles,
                properties.get("name", ""),
                properties.get("mw"),
                properties.get("logp"),
                properties.get("hbd"),
                properties.get("hba"),
                properties.get("tpsa"),
                properties.get("rule_of_5"),
                json.dumps(properties.get("admet", {})),
                datetime.now().isoformat(),
            )
        )
        await db.commit()


async def get_cached_compound(smiles: str) -> dict | None:
    """Retrieve cached compound properties."""
    if not AIOSQLITE_AVAILABLE:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM compound_cache WHERE smiles = ?", (smiles,))
        row = await cursor.fetchone()
        if row is None:
            return None
        result = dict(row)
        result["admet"] = json.loads(result.get("admet", "{}"))
        return result


async def get_docking_history(project_id: str | None = None, limit: int = 100) -> list[dict]:
    """Retrieve docking history, optionally filtered by project."""
    if not AIOSQLITE_AVAILABLE:
        return []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if project_id:
            cursor = await db.execute(
                "SELECT * FROM docking_history WHERE project_id = ? ORDER BY timestamp DESC LIMIT ?",
                (project_id, limit)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM docking_history ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
