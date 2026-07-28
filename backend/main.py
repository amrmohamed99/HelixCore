"""
Helix Core v3.0.0 — FastAPI Application Entry Point
"""

import os
import warnings
from contextlib import asynccontextmanager

warnings.filterwarnings(
    "ignore",
    message=r"to-Python converter for class boost::shared_ptr<class RDKit::FilterHierarchyMatcher> already registered; second conversion method ignored\.",
    category=RuntimeWarning,
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import APP_VERSION, HOST, PORT

_CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "HELIX_CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    ).split(",")
    if origin.strip()
]

# --- Router Imports ---
from backend.routers import fetch, pocket, batch, minimize, convert, pipeline
from backend.routers import similarity, docking, oracle, results, system
from backend.routers import filters, admet, interactions, cluster, analogs
from backend.routers import projects, watchlist, resolve, activity, prepare
from backend.routers import compare, pharmacophore
from backend.routers import ws, report, fragments, scaffold
from backend.routers import jobs


@asynccontextmanager
async def _lifespan(_: FastAPI):
    """Check local engine identity and initialize persistence at startup."""
    # Interactive use stays available when an engine is missing or unexpected:
    # this entry point logs the exact mismatch but deliberately never raises.
    # Measurement runners use the separate, strict gate before writing evidence.
    from backend.utils.engine_guard import warn_if_unexpected_engines

    warn_if_unexpected_engines()

    try:
        from backend.services.database import init_database
        await init_database()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(f"Database init skipped: {exc}")

    yield

app = FastAPI(
    title="Helix Core Backend",
    version=APP_VERSION,
    description="Drug Discovery Suite — REST + WebSocket API",
    lifespan=_lifespan,
)

# --- CORS (allow Electron renderer) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    # Packaged Electron windows use an opaque/null origin; keep that narrow
    # exception while rejecting arbitrary browser origins by default.
    allow_origin_regex=r"^(null|file://.*)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Register Routers ---
app.include_router(jobs.router,        prefix="/api/jobs",       tags=["Jobs"])
app.include_router(system.router,      prefix="/api/system",     tags=["System"])
app.include_router(fetch.router,       prefix="/api/fetch",      tags=["PDB Fetcher"])
app.include_router(pocket.router,      prefix="/api/pocket",     tags=["Pocket Analyzer"])
app.include_router(batch.router,       prefix="/api/batch",      tags=["Batch Generator"])
app.include_router(minimize.router,    prefix="/api/minimize",   tags=["Minimization"])
app.include_router(convert.router,     prefix="/api/convert",    tags=["Converter"])
app.include_router(pipeline.router,    prefix="/api/pipeline",   tags=["Auto-Pipeline"])
app.include_router(similarity.router,  prefix="/api/similarity", tags=["Similarity Search"])
app.include_router(docking.router,     prefix="/api/docking",    tags=["Virtual Screening"])
app.include_router(oracle.router,      prefix="/api/oracle",     tags=["Oracle AI"])
app.include_router(results.router,     prefix="/api/results",    tags=["Results Explorer"])
app.include_router(filters.router,     prefix="/api/filters",    tags=["Compound Filters"])
app.include_router(admet.router,       prefix="/api/admet",      tags=["ADMET Profiler"])
app.include_router(interactions.router, prefix="/api/interactions", tags=["Interaction Profiler"])
app.include_router(cluster.router,     prefix="/api/cluster",    tags=["Chemical Clustering"])
app.include_router(analogs.router,     prefix="/api/analogs",    tags=["Analog Generator"])
app.include_router(projects.router,    prefix="/api/projects",   tags=["Project Management"])
app.include_router(watchlist.router,   prefix="/api/watchlist",  tags=["Compound Watchlist"])
app.include_router(resolve.router,     prefix="/api/resolve",    tags=["Molecule Resolver"])
app.include_router(activity.router,    prefix="/api/activity",   tags=["Activity Log"])
app.include_router(prepare.router,     prefix="/api/prepare",    tags=["Receptor Preparation"])
app.include_router(compare.router,     prefix="/api/compare",    tags=["Compound Comparison"])
app.include_router(pharmacophore.router, prefix="/api/pharmacophore", tags=["Pharmacophore"])
app.include_router(ws.router,             prefix="/api/ws",             tags=["WebSocket"])
app.include_router(report.router,         prefix="/api/report",         tags=["Report Generation"])
app.include_router(fragments.router,      prefix="/api/fragments",      tags=["Fragment Design"])
app.include_router(scaffold.router,       prefix="/api/scaffold",       tags=["Scaffold Hopping"])


@app.get("/api/health")
async def health_check():
    """Health check endpoint used by the Electron shell."""
    return {"status": "online", "version": APP_VERSION}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=True)
