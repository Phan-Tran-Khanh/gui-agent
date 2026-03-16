from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .event_emitter import EventEmitter
from .runner import AgentRunner
from .task_manager import TaskManager


task_manager = TaskManager()
emitter = EventEmitter()
runner = AgentRunner(task_manager=task_manager, emitter=emitter)

app = FastAPI(title="GUI Agent Web Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StartTaskRequest(BaseModel):
    goal: str = Field(min_length=1, description="User goal for the GUI agent")


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/task/start")
async def start_task(payload: StartTaskRequest) -> Dict[str, str]:
    state = await task_manager.create_task(goal=payload.goal)

    async def _run() -> None:
        await runner.run(task_id=state.task_id, goal=state.goal)

    worker = asyncio.create_task(_run())
    await task_manager.set_worker(state.task_id, worker)
    return {"task_id": state.task_id}


@app.get("/api/v1/task/{task_id}")
async def get_task(task_id: str) -> Dict[str, Any]:
    snapshot = await task_manager.snapshot(task_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return snapshot


@app.post("/api/v1/task/{task_id}/cancel")
async def cancel_task(task_id: str) -> Dict[str, Any]:
    cancelled = await task_manager.cancel_task(task_id)
    return {"task_id": task_id, "cancelled": cancelled}


@app.websocket("/ws/task/{task_id}")
async def stream_task_events(websocket: WebSocket, task_id: str) -> None:
    state = await task_manager.get_state(task_id)
    if state is None:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    snapshot = await task_manager.snapshot(task_id)
    if snapshot is not None:
        for event in snapshot["events"]:
            await websocket.send_json(event)

    queue = await emitter.subscribe(task_id)

    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event.to_dict())
            if event.type in {"task_completed", "task_failed"}:
                break
    except WebSocketDisconnect:
        pass
    finally:
        await emitter.unsubscribe(task_id, queue)
        if websocket.client_state.name != "DISCONNECTED":
            await websocket.close()
