from __future__ import annotations

import asyncio
import base64
import binascii
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from .event_emitter import EventEmitter
from .omniparser_client import OmniParserClient, OmniParserClientError
from .runner import AgentRunner
from .task_manager import TaskManager


task_manager = TaskManager()
emitter = EventEmitter()
runner = AgentRunner(task_manager=task_manager, emitter=emitter)

# Load environment variables from gui-agent/.env when present.
load_dotenv()


def _build_omniparser_client_from_env() -> OmniParserClient | None:
    parse_base_url = os.getenv("PARSE_API_BASE_URL", "").strip()
    if not parse_base_url:
        return None

    parse_timeout_sec = float(os.getenv("PARSE_API_TIMEOUT_SEC", "10"))
    parse_retry_count = int(os.getenv("PARSE_API_RETRY_COUNT", "1"))
    parse_retry_backoff_ms = int(os.getenv("PARSE_API_RETRY_BACKOFF_MS", "250"))
    return OmniParserClient(
        base_url=parse_base_url,
        timeout_sec=parse_timeout_sec,
        retry_count=parse_retry_count,
        retry_backoff_ms=parse_retry_backoff_ms,
    )


omniparser_client = _build_omniparser_client_from_env()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if omniparser_client is not None:
        try:
            _ = await omniparser_client.probe()
        except Exception:
            # Fail-soft: backend remains available even if parser is temporarily unreachable.
            pass
    try:
        yield
    finally:
        if omniparser_client is not None:
            await omniparser_client.close()


app = FastAPI(title="GUI Agent Web Backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StartTaskRequest(BaseModel):
    goal: str = Field(min_length=1, description="User goal for the GUI agent")


class ParseScreenRequest(BaseModel):
    prompt: str = Field(min_length=1, description="User prompt that will drive future ADB capture flow")
    base64_image: Optional[str] = Field(default=None, description="Optional base64 image for direct parse testing")
    filename: str = Field(default="screen.png", description="Logical filename for multipart upload")


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/screen/parse")
async def parse_screen(payload: ParseScreenRequest) -> Dict[str, Any]:
    if omniparser_client is None:
        raise HTTPException(status_code=503, detail="OmniParser client is not configured")

    # Current scope: client sends prompt only. ADB capture integration will provide image bytes later.
    if not payload.base64_image:
        try:
            probe = await omniparser_client.probe()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"OmniParser is unreachable: {exc}")

        return {
            "parser_status": "capture_required",
            "prompt": payload.prompt,
            "omniparser_ready": bool(probe.get("model_loaded", False)),
            "message": "No image provided. Backend is connected to OmniParser. Integrate ADB capture to continue parse.",
            "elements_count": 0,
            "parsed_screen": [],
        }

    try:
        image_bytes = base64.b64decode(payload.base64_image, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Invalid base64_image payload")

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Decoded image is empty")

    try:
        result = await omniparser_client.parse_screen(image_bytes=image_bytes, filename=payload.filename)
    except OmniParserClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {
        "parser_status": "completed",
        "prompt": payload.prompt,
        "parser_request_id": result.request_id,
        "parser_latency_ms": result.latency_ms,
        "elements_count": len(result.parsed_screen),
        "parsed_screen": result.parsed_screen,
    }


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
