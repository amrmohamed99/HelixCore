"""Global job status and controls."""

from fastapi import APIRouter

from backend.models.schemas import JobControlResponse, JobSnapshot
from backend.services.job_manager import job_manager

router = APIRouter()


@router.get("/current", response_model=JobSnapshot | None)
async def current_job():
    """Return the active or just-finished global task."""
    job = await job_manager.current()
    return JobSnapshot(**job) if job else None


@router.post("/{job_id}/pause", response_model=JobControlResponse)
async def pause_job(job_id: str):
    """Pause the active task at the next safe checkpoint."""
    job = await job_manager.pause(job_id)
    return JobControlResponse(success=True, message="Task paused", job=JobSnapshot(**job))


@router.post("/{job_id}/resume", response_model=JobControlResponse)
async def resume_job(job_id: str):
    """Resume a paused task."""
    job = await job_manager.resume(job_id)
    return JobControlResponse(success=True, message="Task resumed", job=JobSnapshot(**job))


@router.post("/{job_id}/terminate", response_model=JobControlResponse)
async def terminate_job(job_id: str):
    """Terminate the active task and keep any files already produced."""
    job = await job_manager.terminate(job_id)
    return JobControlResponse(success=True, message="Task termination requested", job=JobSnapshot(**job))
