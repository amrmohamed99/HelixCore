"""
WebSocket manager — real-time progress, cancellation, pause, and skip control.
Provides a centralized hub for long-running tasks to emit progress events.
"""

import asyncio
import time
import json
from enum import Enum
from typing import Any
from fastapi import WebSocket


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    ERROR = "error"
    SKIPPED = "skipped"


class TaskProgress:
    """Tracks progress for a single long-running task."""

    def __init__(self, task_id: str, total: int = 0, label: str = ""):
        self.task_id = task_id
        self.total = total
        self.label = label
        self.current = 0
        self.status = TaskStatus.PENDING
        self.message = ""
        self.started_at = 0.0
        self.detail: dict[str, Any] = {}
        self._cancel_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # not paused initially
        self._skip_event = asyncio.Event()

    @property
    def progress(self) -> float:
        if self.total <= 0:
            return 0.0
        return min(100.0, (self.current / self.total) * 100)

    @property
    def elapsed(self) -> float:
        if self.started_at == 0:
            return 0.0
        return time.time() - self.started_at

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "label": self.label,
            "current": self.current,
            "total": self.total,
            "progress": round(self.progress, 1),
            "elapsed": round(self.elapsed, 1),
            "message": self.message,
            "detail": self.detail,
        }

    def cancel(self) -> None:
        self.status = TaskStatus.CANCELLED
        self._cancel_event.set()
        self._pause_event.set()  # unblock if paused

    def pause(self) -> None:
        if self.status == TaskStatus.RUNNING:
            self.status = TaskStatus.PAUSED
            self._pause_event.clear()

    def resume(self) -> None:
        if self.status == TaskStatus.PAUSED:
            self.status = TaskStatus.RUNNING
            self._pause_event.set()

    def skip(self) -> None:
        self._skip_event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    @property
    def should_skip(self) -> bool:
        if self._skip_event.is_set():
            self._skip_event.clear()
            return True
        return False

    async def wait_if_paused(self) -> None:
        """Block until un-paused. Returns immediately if not paused."""
        await self._pause_event.wait()


class WebSocketManager:
    """Central manager for WebSocket connections and task progress."""

    def __init__(self):
        self._connections: dict[str, WebSocket] = {}
        self._tasks: dict[str, TaskProgress] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, client_id: str) -> None:
        await ws.accept()
        self._connections[client_id] = ws

    async def disconnect(self, client_id: str) -> None:
        self._connections.pop(client_id, None)

    def create_task(self, task_id: str, total: int = 0, label: str = "") -> TaskProgress:
        task = TaskProgress(task_id=task_id, total=total, label=label)
        self._tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> TaskProgress | None:
        return self._tasks.get(task_id)

    def remove_task(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)

    async def broadcast(self, event: dict) -> None:
        """Send an event to all connected WebSocket clients."""
        msg = json.dumps(event)
        dead: list[str] = []
        for cid, ws in self._connections.items():
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self._connections.pop(cid, None)

    async def send_to(self, client_id: str, event: dict) -> None:
        ws = self._connections.get(client_id)
        if ws:
            try:
                await ws.send_text(json.dumps(event))
            except Exception:
                self._connections.pop(client_id, None)

    async def emit_progress(self, task: TaskProgress) -> None:
        """Broadcast current progress of a task."""
        await self.broadcast({"type": "progress", **task.to_dict()})

    async def emit_complete(self, task: TaskProgress, result: dict | None = None) -> None:
        """Broadcast task completion."""
        task.status = TaskStatus.COMPLETED
        payload = {"type": "complete", **task.to_dict()}
        if result:
            payload["result"] = result
        await self.broadcast(payload)

    async def emit_error(self, task: TaskProgress, error: str) -> None:
        """Broadcast task error."""
        task.status = TaskStatus.ERROR
        task.message = error
        await self.broadcast({"type": "error", **task.to_dict()})

    @property
    def active_tasks(self) -> list[dict]:
        return [t.to_dict() for t in self._tasks.values()
                if t.status in (TaskStatus.RUNNING, TaskStatus.PAUSED, TaskStatus.PENDING)]


# Global singleton
ws_manager = WebSocketManager()
