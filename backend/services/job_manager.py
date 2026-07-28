"""
Global job manager for one active long-running task.

Routes use this service to publish progress and to cooperatively pause or
terminate work between safe units such as files, molecules, or pipeline steps.
"""

from __future__ import annotations

import asyncio
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException


TERMINAL_STATUSES = {"completed", "cancelled", "error"}
VISIBLE_TERMINAL_SECONDS = 4.0


def job_progress_message(action: str, item: str, index: int, total: int, last_done: str | None = None) -> str:
    """Build a compact, consistent progress message for the floating tracker."""
    position = min(index + 1, max(total, 1))
    done = f"Last done: {last_done}" if last_done else "Last done: none"
    return f"{action}: {item} ({position}/{max(total, 1)}) | {done}"


class JobCancelled(Exception):
    """Raised when the active job has been terminated by the user."""


@dataclass
class JobRecord:
    id: str
    name: str
    status: str = "running"
    progress: int = 0
    message: str = ""
    current: int = 0
    total: int = 0
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    terminal_at: float | None = None
    active_process: subprocess.Popen[Any] | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "progress": max(0, min(100, int(self.progress))),
            "message": self.message,
            "current": self.current,
            "total": self.total,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }


class JobManager:
    """Tracks the single global active task and exposes cooperative controls."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active: JobRecord | None = None
        self._last_terminal: JobRecord | None = None

    async def begin(self, name: str, total: int = 0, message: str = "Starting...") -> JobRecord:
        async with self._lock:
            if self._active and self._active.status not in TERMINAL_STATUSES:
                raise HTTPException(
                    status_code=409,
                    detail=f"Another task is already running: {self._active.name}",
                )
            job = JobRecord(
                id=str(uuid.uuid4()),
                name=name,
                total=max(0, total),
                message=message,
            )
            self._active = job
            return job

    async def current(self) -> dict[str, Any] | None:
        async with self._lock:
            if self._active and self._active.status not in TERMINAL_STATUSES:
                return self._active.snapshot()
            if self._last_terminal and self._last_terminal.terminal_at:
                age = time.time() - self._last_terminal.terminal_at
                if age <= VISIBLE_TERMINAL_SECONDS:
                    return self._last_terminal.snapshot()
            return None

    async def get_active(self, job_id: str) -> JobRecord:
        async with self._lock:
            if not self._active or self._active.id != job_id:
                raise HTTPException(status_code=404, detail="Active job not found")
            return self._active

    async def update(
        self,
        job_id: str,
        *,
        progress: int | None = None,
        message: str | None = None,
        current: int | None = None,
        total: int | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            job = self._active
            if not job or job.id != job_id:
                raise JobCancelled()
            if status:
                job.status = status
            if progress is not None:
                job.progress = max(0, min(100, int(progress)))
            if message is not None:
                job.message = message
            if current is not None:
                job.current = max(0, int(current))
            if total is not None:
                job.total = max(0, int(total))
            job.updated_at = time.time()
            return job.snapshot()

    async def checkpoint(
        self,
        job_id: str,
        *,
        progress: int | None = None,
        message: str | None = None,
        current: int | None = None,
        total: int | None = None,
    ) -> None:
        """Update progress, wait while paused, and raise when terminated."""
        await self.update(job_id, progress=progress, message=message, current=current, total=total)

        while True:
            async with self._lock:
                job = self._active
                if not job or job.id != job_id:
                    raise JobCancelled()
                if job.status == "terminating":
                    raise JobCancelled()
                paused = job.status == "paused"
            if not paused:
                return
            await asyncio.sleep(0.25)

    async def finish(self, job_id: str, status: str, message: str, progress: int | None = None) -> None:
        async with self._lock:
            job = self._active
            if not job or job.id != job_id:
                return
            job.status = status
            job.message = message
            if progress is not None:
                job.progress = max(0, min(100, int(progress)))
            job.updated_at = time.time()
            job.terminal_at = time.time()
            job.active_process = None
            self._last_terminal = job
            self._active = None

    async def pause(self, job_id: str) -> dict[str, Any]:
        async with self._lock:
            job = self._active
            if not job or job.id != job_id:
                raise HTTPException(status_code=404, detail="Active job not found")
            if job.status == "running":
                job.status = "paused"
                job.message = f"Paused: {job.message}"
            job.updated_at = time.time()
            return job.snapshot()

    async def resume(self, job_id: str) -> dict[str, Any]:
        async with self._lock:
            job = self._active
            if not job or job.id != job_id:
                raise HTTPException(status_code=404, detail="Active job not found")
            if job.status == "paused":
                job.status = "running"
                job.message = job.message.removeprefix("Paused: ")
            job.updated_at = time.time()
            return job.snapshot()

    async def terminate(self, job_id: str) -> dict[str, Any]:
        async with self._lock:
            job = self._active
            if not job or job.id != job_id:
                raise HTTPException(status_code=404, detail="Active job not found")
            job.status = "terminating"
            job.message = "Terminating current task..."
            job.updated_at = time.time()
            proc = job.active_process

        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

        async with self._lock:
            job = self._active
            if not job or job.id != job_id:
                raise HTTPException(status_code=404, detail="Active job not found")
            return job.snapshot()

    async def run_subprocess(
        self,
        job_id: str,
        cmd: list[str],
        *,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        capture_output: bool = True,
        text: bool = True,
        stdout: Any | None = None,
        stderr: Any | None = None,
        creationflags: int = 0,
        check: bool = False,
    ) -> subprocess.CompletedProcess[Any]:
        """Run a subprocess while honoring terminate requests."""
        if capture_output:
            stdout_arg = subprocess.PIPE
            stderr_arg = subprocess.PIPE
        else:
            stdout_arg = stdout
            stderr_arg = stderr

        proc = subprocess.Popen(
            cmd,
            env=env,
            cwd=cwd,
            stdout=stdout_arg,
            stderr=stderr_arg,
            text=text,
            creationflags=creationflags,
        )
        async with self._lock:
            job = self._active
            if job and job.id == job_id:
                job.active_process = proc

        started = time.monotonic()
        try:
            while proc.poll() is None:
                async with self._lock:
                    job = self._active
                    terminating = not job or job.id != job_id or job.status == "terminating"
                if terminating:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                    try:
                        await asyncio.to_thread(proc.wait, timeout=2)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                    raise JobCancelled()
                if timeout is not None and time.monotonic() - started > timeout:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    raise subprocess.TimeoutExpired(cmd, timeout)
                await asyncio.sleep(0.2)

            async with self._lock:
                job = self._active
                if not job or job.id != job_id or job.status == "terminating":
                    raise JobCancelled()

            out, err = await asyncio.to_thread(proc.communicate)
            result = subprocess.CompletedProcess(cmd, proc.returncode, out, err)
            if check and result.returncode != 0:
                raise subprocess.CalledProcessError(result.returncode, cmd, output=out, stderr=err)
            return result
        finally:
            async with self._lock:
                job = self._active
                if job and job.id == job_id and job.active_process is proc:
                    job.active_process = None


job_manager = JobManager()
