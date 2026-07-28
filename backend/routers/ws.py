"""
WebSocket router — real-time progress streaming and task control.
"""

import uuid
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.services.ws_manager import ws_manager

router = APIRouter()


@router.websocket("/progress")
async def ws_progress(ws: WebSocket):
    """Main WebSocket endpoint for real-time progress updates and task control.

    Client → Server commands:
        {"action": "cancel", "task_id": "..."}
        {"action": "pause",  "task_id": "..."}
        {"action": "resume", "task_id": "..."}
        {"action": "skip",   "task_id": "..."}
        {"action": "list"}   — returns active tasks

    Server → Client events:
        {"type": "progress", "task_id": "...", "progress": 45.2, ...}
        {"type": "complete", "task_id": "...", "result": {...}}
        {"type": "error",    "task_id": "...", "message": "..."}
        {"type": "connected", "client_id": "..."}
    """
    client_id = str(uuid.uuid4())
    await ws_manager.connect(ws, client_id)

    try:
        await ws.send_text(json.dumps({
            "type": "connected",
            "client_id": client_id,
        }))

        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                continue

            action = msg.get("action", "")
            task_id = msg.get("task_id", "")

            if action == "cancel":
                task = ws_manager.get_task(task_id)
                if task:
                    task.cancel()
                    await ws_manager.emit_progress(task)
                else:
                    await ws.send_text(json.dumps({"type": "error", "message": f"Task {task_id} not found"}))

            elif action == "pause":
                task = ws_manager.get_task(task_id)
                if task:
                    task.pause()
                    await ws_manager.emit_progress(task)

            elif action == "resume":
                task = ws_manager.get_task(task_id)
                if task:
                    task.resume()
                    await ws_manager.emit_progress(task)

            elif action == "skip":
                task = ws_manager.get_task(task_id)
                if task:
                    task.skip()

            elif action == "list":
                await ws.send_text(json.dumps({
                    "type": "task_list",
                    "tasks": ws_manager.active_tasks,
                }))

            else:
                await ws.send_text(json.dumps({"type": "error", "message": f"Unknown action: {action}"}))

    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(client_id)
