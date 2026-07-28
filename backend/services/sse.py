"""
SSE helpers — lightweight progress emitter for long-running pipeline tasks.
"""

import asyncio
import json
import time
from typing import AsyncGenerator


class ProgressEmitter:
    """Async generator that yields SSE-formatted progress events.

    Usage in a router:
        emitter = ProgressEmitter()
        async def do_work():
            emitter.emit("step1", "Generating 3D…", progress=10)
            ...
            emitter.emit("done", "Complete!", progress=100)
            emitter.close()

        asyncio.create_task(do_work())
        return EventSourceResponse(emitter.stream())
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict | None] = asyncio.Queue()
        self._closed = False
        self._start = time.time()

    def emit(
        self,
        step: str,
        message: str,
        *,
        progress: int = 0,
        count: int | None = None,
        total: int | None = None,
        detail: dict | None = None,
    ) -> None:
        """Push one progress event into the stream."""
        if self._closed:
            return
        evt: dict = {
            "step": step,
            "message": message,
            "progress": progress,
            "elapsed": round(time.time() - self._start, 1),
        }
        if count is not None:
            evt["count"] = count
        if total is not None:
            evt["total"] = total
        if detail:
            evt["detail"] = detail
        self._queue.put_nowait(evt)

    def close(self) -> None:
        """Signal end-of-stream."""
        self._closed = True
        self._queue.put_nowait(None)

    def error(self, message: str) -> None:
        """Push an error event and close the stream."""
        self.emit("error", message, progress=-1)
        self.close()

    async def stream(self) -> AsyncGenerator[dict, None]:
        """Async generator yielding SSE data dicts until closed."""
        while True:
            item = await self._queue.get()
            if item is None:
                return
            yield item
