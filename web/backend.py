# from __future__ import annotations

# import asyncio
# import base64
# import binascii
# import logging
# import sys

# import os
# from contextlib import asynccontextmanager
# from typing import Any, Dict, Optional

# from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.staticfiles import StaticFiles
# from pydantic import BaseModel, Field
# from dotenv import load_dotenv

# from .event_emitter import EventEmitter
# from .omniparser_client import OmniParserClient, OmniParserClientError
# from .runner import AgentRunner
# from .sequential_executor import SequentialExecutor
# from .sequential_runner import SequentialRunner

# from .task_manager import TaskManager
# from config.config import Config


# task_manager = TaskManager()
# emitter = EventEmitter()
# runner = AgentRunner(task_manager=task_manager, emitter=emitter)
# sequentialRunner = SequentialRunner(task_manager=task_manager, emitter=emitter)
# # Load environment variables from gui-agent/.env when present.
# load_dotenv()

# # Setup logger
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
#     datefmt="%Y-%m-%d %H:%M:%S",
#     handlers=[logging.StreamHandler(sys.stdout)]
# )

# logger = logging.getLogger("GUIAgentBackend")


# def _build_omniparser_client_from_env() -> OmniParserClient | None:
#     parse_base_url = os.getenv("PARSE_API_BASE_URL", "").strip()
#     if not parse_base_url:
#         return None

#     parse_timeout_sec = float(os.getenv("PARSE_API_TIMEOUT_SEC", "10"))
#     parse_retry_count = int(os.getenv("PARSE_API_RETRY_COUNT", "1"))
#     parse_retry_backoff_ms = int(os.getenv("PARSE_API_RETRY_BACKOFF_MS", "250"))
#     return OmniParserClient(
#         base_url=parse_base_url,
#         timeout_sec=parse_timeout_sec,
#         retry_count=parse_retry_count,
#         retry_backoff_ms=parse_retry_backoff_ms,
#     )


# omniparser_client = _build_omniparser_client_from_env()


# @asynccontextmanager
# async def lifespan(_app: FastAPI):
#     if omniparser_client is not None:
#         try:
#             _ = await omniparser_client.probe()
#         except Exception:
#             # Fail-soft: backend remains available even if parser is temporarily unreachable.
#             pass
#     try:
#         yield
#     finally:
#         if omniparser_client is not None:
#             await omniparser_client.close()


# app = FastAPI(title="GUI Agent Web Backend", version="0.1.0", lifespan=lifespan)

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# output_dir_path = os.path.abspath("output")
# os.makedirs(output_dir_path, exist_ok=True)
# app.mount("/output", StaticFiles(directory=output_dir_path), name="output")


# class StartTaskRequest(BaseModel):
#     goal: str = Field(min_length=1, description="User goal for the GUI agent")


# class ParseScreenRequest(BaseModel):
#     prompt: str = Field(min_length=1, description="User prompt that will drive future ADB capture flow")
#     base64_image: Optional[str] = Field(default=None, description="Optional base64 image for direct parse testing")
#     filename: str = Field(default="screen.png", description="Logical filename for multipart upload")


# class SequentialExecutionRequest(BaseModel):
#     goal: str = Field(min_length=1, description="User goal to achieve")
#     device_id: str = Field(default="144321556E009492", description="Android device ID")
#     base64_image: Optional[str] = Field(default=None, description="Optional initial screenshot as base64")
#     max_steps: int = Field(default=15, description="Maximum execution steps")
#     step_delay_sec: float = Field(default=3.0, description="Delay after each action in seconds")
#     output_dir: str = Field(default="output", description="Directory to save results")
#     task_id: Optional[str] = Field(default=None, description="Optional task ID for event emission")


# @app.get("/health")
# async def health() -> Dict[str, str]:
#     return {"status": "ok"}


# @app.post("/api/v1/screen/parse")
# async def parse_screen(payload: ParseScreenRequest) -> Dict[str, Any]:
#     if omniparser_client is None:
#         raise HTTPException(status_code=503, detail="OmniParser client is not configured")

#     # Current scope: client sends prompt only. ADB capture integration will provide image bytes later.
#     if not payload.base64_image:
#         try:
#             probe = await omniparser_client.probe()
#         except Exception as exc:
#             raise HTTPException(status_code=502, detail=f"OmniParser is unreachable: {exc}")

#         return {
#             "parser_status": "capture_required",
#             "prompt": payload.prompt,
#             "omniparser_ready": bool(probe.get("model_loaded", False)),
#             "message": "No image provided. Backend is connected to OmniParser. Integrate ADB capture to continue parse.",
#             "elements_count": 0,
#             "parsed_screen": [],
#         }

#     try:
#         image_bytes = base64.b64decode(payload.base64_image, validate=True)
#     except (binascii.Error, ValueError):
#         raise HTTPException(status_code=400, detail="Invalid base64_image payload")

#     if not image_bytes:
#         raise HTTPException(status_code=400, detail="Decoded image is empty")

#     try:
#         result = await omniparser_client.parse_screen(image_bytes=image_bytes, filename=payload.filename)
#     except OmniParserClientError as exc:
#         raise HTTPException(status_code=502, detail=str(exc))

#     return {
#         "parser_status": "completed",
#         "prompt": payload.prompt,
#         "parser_request_id": result.request_id,
#         "parser_latency_ms": result.latency_ms,
#         "elements_count": len(result.parsed_screen),
#         "parsed_screen": result.parsed_screen,
#     }


# @app.post("/api/v1/sequential/execute")
# async def sequential_execute(payload: SequentialExecutionRequest) -> Dict[str, Any]:
#     """
#     Execute a sequential flow: OmniParser → Planner → Executor loop.

#     Flow:
#     1. Capture screenshot and parse with OmniParser
#     2. Send annotated screenshot to Planner
#     3. If goal not fulfilled, Planner creates action plan
#     4. Executor performs action, waits 5 seconds, captures new screenshot
#     5. Loop until goal fulfilled or 50 steps reached

#     Args:
#         payload: SequentialExecutionRequest with:
#             - goal: User goal (required)
#             - device_id: Android device ID (default: emulator-5554)
#             - base64_image: Optional initial screenshot
#             - max_steps: Maximum execution steps (default: 15)
#             - step_delay_sec: Delay after actions (default: 3.0s)
#             - output_dir: Directory to save results

#     Returns:
#         Dictionary with execution result including:
#             - success: Overall success status
#             - goal_achieved: Whether goal was fulfilled
#             - total_steps: Number of steps executed
#             - steps: Array of step details with screenshots, actions, plans
#             - completion_message: Summary message
#     """
#     logger.info(f"[sequential/execute] Received request: goal={payload.goal}, device_id={payload.device_id}")
    
#     # Validate OmniParser is configured
#     if omniparser_client is None:
#         logger.error("[sequential/execute] OmniParser client not configured")
#         raise HTTPException(status_code=503, detail="OmniParser client is not configured")

#     try:
#         # Decode initial screenshot if provided
#         initial_screenshot = None
#         if payload.base64_image:
#                 initial_screenshot = base64.b64decode(payload.base64_image, validate=True)
#                 logger.info("[sequential/execute] Initial screenshot decoded successfully")

#         # Load configuration
#         logger.info("[sequential/execute] Loading configuration...")
#         config = Config.from_args(None)
#         logger.info("[sequential/execute] Configuration loaded successfully")

#         # Create sequential executor
#         logger.info("[sequential/execute] Creating SequentialExecutor...")
#         seq_executor = SequentialExecutor(
#             device_id=payload.device_id,
#             omniparser_client=omniparser_client,
#             config=config,
#             logger=logger,
#             sequential_runner=sequentialRunner,
#             max_steps=payload.max_steps,
#             step_delay_sec=payload.step_delay_sec,
#         )
#         logger.info("[sequential/execute] SequentialExecutor created successfully")

#         # Create task in task manager
#         logger.info(f"[sequential/execute] Creating task for goal: {payload.goal}")
#         state = await task_manager.create_task(goal=payload.goal)
#         logger.info(f"[sequential/execute] Task created: task_id={state.task_id}, initial_stage={state.stage}")

#         async def _run() -> None:
#             logger.info(f"[sequential/execute] Starting background executor for task {state.task_id}")
#             try:
#                 await seq_executor.execute(
#                     user_goal=payload.goal,
#                     task_id=state.task_id,
#                     initial_screenshot=initial_screenshot,
#                     output_dir=payload.output_dir,
#                 )
#                 logger.info(f"[sequential/execute] Background executor completed for task {state.task_id}")
#             except Exception as exc:
#                 logger.exception(f"[sequential/execute] Background executor failed for task {state.task_id}: {exc}")
#                 await task_manager.mark_failed(state.task_id, str(exc))

#         worker = asyncio.create_task(_run())
#         logger.info(f"[sequential/execute] Background task created for task_id={state.task_id}")

#         await task_manager.set_worker(state.task_id, worker)
#         logger.info(f"[sequential/execute] Worker registered. Returning task_id={state.task_id} to client")

#         return { "task_id": state.task_id }

#         # Execute the sequential flow
#         # result = await seq_executor.execute(
#         #     user_goal=payload.goal,
#         #     initial_screenshot=initial_screenshot,
#         #     output_dir=payload.output_dir,
#         # )

#         # # Convert result to JSON-serializable format
#         # return {
#         #     "success": result.success,
#         #     "goal_achieved": result.goal_achieved,
#         #     "total_steps": result.total_steps,
#         #     "completion_message": result.completion_message,
#         #     "timestamp": result.timestamp,
#         #     "errors": result.errors,
#         #     "steps_summary": [
#         #         {
#         #             "step_number": step.step_number,
#         #             "timestamp": step.timestamp,
#         #             "action_executed": step.action_executed,
#         #             "elements_detected": step.elements_detected,
#         #             "goal_achieved": step.goal_achieved,
#         #             "goal_check_reasoning": step.goal_check_reasoning,
#         #             "error": step.error,
#         #             "metadata": step.metadata,
#         #         }
#         #         for step in result.steps
#         #     ],
#         # }

#     except HTTPException:
#         logger.warning(f"[sequential/execute] HTTP exception raised")
#         raise
#     except Exception as e:
#         logger.exception(f"[sequential/execute] Unexpected error during sequential execution: {type(e).__name__}: {e}")
#         raise HTTPException(status_code=500, detail=f"Sequential execution failed: {str(e)}")


# @app.post("/api/v1/backup/execute")
# async def sequential_execute_backup(payload: SequentialExecutionRequest) -> Dict[str, Any]:
#     """
#     Execute a sequential flow: OmniParser → Planner → Executor loop.

#     Flow:
#     1. Capture screenshot and parse with OmniParser
#     2. Send annotated screenshot to Planner
#     3. If goal not fulfilled, Planner creates action plan
#     4. Executor performs action, waits 5 seconds, captures new screenshot
#     5. Loop until goal fulfilled or 50 steps reached

#     Args:
#         payload: SequentialExecutionRequest with:
#             - goal: User goal (required)
#             - device_id: Android device ID (default: emulator-5554)
#             - base64_image: Optional initial screenshot
#             - max_steps: Maximum execution steps (default: 15)
#             - step_delay_sec: Delay after actions (default: 3.0s)
#             - output_dir: Directory to save results

#     Returns:
#         Dictionary with execution result including:
#             - success: Overall success status
#             - goal_achieved: Whether goal was fulfilled
#             - total_steps: Number of steps executed
#             - steps: Array of step details with screenshots, actions, plans
#             - completion_message: Summary message
#     """
#     # Validate OmniParser is configured
#     if omniparser_client is None:
#         raise HTTPException(status_code=503, detail="OmniParser client is not configured")

#     try:
#         # Decode initial screenshot if provided
#         initial_screenshot = None
#         if payload.base64_image:
#                 initial_screenshot = base64.b64decode(payload.base64_image, validate=True)

#         # Load configuration
#         config = Config.from_args(None)

#         # Create sequential executor
#         seq_executor = SequentialExecutor(
#             device_id=payload.device_id,
#             omniparser_client=omniparser_client,
#             config=config,
#             logger=logger,
#             max_steps=payload.max_steps,
#             step_delay_sec=payload.step_delay_sec,
#             sequential_runner=sequentialRunner,  # Pass the runner for event emission
#         )

#         state = await task_manager.create_task(goal=payload.goal)

#         async def _run() -> None:
#             await seq_executor.execute(
#                 user_goal=payload.goal,
#                 task_id=state.task_id,
#                 initial_screenshot=initial_screenshot,
#                 output_dir=payload.output_dir,
#             )

#         worker = asyncio.create_task(_run())

#         await task_manager.set_worker(state.task_id, worker)

#         # Execute the sequential flow
#         # result = await seq_executor.execute(
#         #     user_goal=payload.goal,
#         #     task_id=state.task_id,
#         #     initial_screenshot=initial_screenshot,
#         #     output_dir=payload.output_dir,
#         # )

#         # Convert result to JSON-serializable format
#         # return {
#         #     "success": result.success,
#         #     "goal_achieved": result.goal_achieved,
#         #     "total_steps": result.total_steps,
#         #     "completion_message": result.completion_message,
#         #     "timestamp": result.timestamp,
#         #     "errors": result.errors,
#         #     "steps_summary": [
#         #         {
#         #             "step_number": step.step_number,
#         #             "timestamp": step.timestamp,
#         #             "action_executed": step.action_executed,
#         #             "elements_detected": step.elements_detected,
#         #             "goal_achieved": step.goal_achieved,
#         #             "goal_check_reasoning": step.goal_check_reasoning,
#         #             "error": step.error,
#         #             "metadata": step.metadata,
#         #         }
#         #         for step in result.steps
#         #     ],
#         # }
#         return { "task_id": state.task_id,}

#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.exception(f"Sequential execution failed: {e}")
#         raise HTTPException(status_code=500, detail=f"Sequential execution failed: {str(e)}")



# @app.post("/api/v1/task/start")
# async def start_task(payload: StartTaskRequest) -> Dict[str, str]:
#     state = await task_manager.create_task(goal=payload.goal)

#     async def _run() -> None:
#         await runner.run(task_id=state.task_id, goal=state.goal)

#     worker = asyncio.create_task(_run())
#     await task_manager.set_worker(state.task_id, worker)
#     return {"task_id": state.task_id}


# @app.get("/api/v1/task/{task_id}")
# async def get_task(task_id: str) -> Dict[str, Any]:
#     snapshot = await task_manager.snapshot(task_id)
#     if snapshot is None:
#         raise HTTPException(status_code=404, detail="Task not found")
#     return snapshot


# @app.post("/api/v1/task/{task_id}/cancel")
# async def cancel_task(task_id: str) -> Dict[str, Any]:
#     cancelled = await task_manager.cancel_task(task_id)
#     return {"task_id": task_id, "cancelled": cancelled}


# @app.websocket("/ws/task/{task_id}")
# async def stream_task_events(websocket: WebSocket, task_id: str) -> None:
#     logger.info(f"[WebSocket] Connection request for task_id={task_id}")
    
#     # Retry logic: wait up to 2 seconds for task to be created (handles race condition)
#     state = None
#     max_retries = 20
#     retry_delay_ms = 100
    
#     for attempt in range(max_retries):
#         state = await task_manager.get_state(task_id)
#         if state is not None:
#             logger.info(f"[WebSocket] Task found on attempt {attempt + 1}: task_id={task_id}, stage={state.stage}")
#             break
#         if attempt == 0:
#             logger.warning(f"[WebSocket] Task not found yet (attempt 1/{max_retries}), retrying in {retry_delay_ms}ms...")
#         await asyncio.sleep(retry_delay_ms / 1000.0)
    
#     if state is None:
#         logger.error(f"[WebSocket] Task not found after {max_retries} retries (waited ~2s). Rejecting connection for task_id={task_id}")
#         await websocket.close(code=1008, reason="Task not found")
#         return

#     await websocket.accept()
#     logger.info(f"[WebSocket] Connection accepted for task_id={task_id}")

#     snapshot = await task_manager.snapshot(task_id)
#     if snapshot is not None:
#         event_count = len(snapshot.get("events", []))
#         logger.info(f"[WebSocket] Sending replay buffer: {event_count} events for task_id={task_id}")
#         for event in snapshot["events"]:
#             await websocket.send_json(event)
#     else:
#         logger.info(f"[WebSocket] No snapshot available for task_id={task_id}")

#     queue = await emitter.subscribe(task_id)
#     logger.info(f"[WebSocket] Subscribed to live events for task_id={task_id}")

#     try:
#         while True:
#             event = await queue.get()
#             logger.debug(f"[WebSocket] Sending event: task_id={task_id}, type={event.type}, title={event.title}")
#             await websocket.send_json(event.to_dict())
#             if event.type in {"task_completed", "task_failed"}:
#                 logger.info(f"[WebSocket] Task ended with type={event.type}. Closing connection for task_id={task_id}")
#                 break
#     except WebSocketDisconnect:
#         logger.info(f"[WebSocket] Client disconnected for task_id={task_id}")
#     except Exception as exc:
#         logger.exception(f"[WebSocket] Unexpected error for task_id={task_id}: {exc}")
#     finally:
#         await emitter.unsubscribe(task_id, queue)
#         if websocket.client_state.name != "DISCONNECTED":
#             await websocket.close()
#         logger.info(f"[WebSocket] Connection closed for task_id={task_id}")


from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import os
import sys

from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .event_emitter import EventEmitter
from .omniparser_client import OmniParserClient, OmniParserClientError
from .runner import AgentRunner
from .sequential_executor import SequentialExecutor
from .sequential_runner import SequentialRunner

from .task_manager import TaskManager
from config import Config

# Setup logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("GUIAgentBackend")

startup_config = Config()
mock_mode: bool = startup_config.mock_mode

task_manager = TaskManager()
emitter = EventEmitter()
runner = AgentRunner(task_manager=task_manager, emitter=emitter)
sequentialRunner = SequentialRunner(task_manager=task_manager, emitter=emitter)

omniparser_client: OmniParserClient | None = (
    OmniParserClient(
        base_url=startup_config.parse_api_base_url,
        timeout_sec=startup_config.parse_api_timeout_sec,
        retry_count=startup_config.parse_api_retry_count,
        retry_backoff_ms=startup_config.parse_api_retry_backoff_ms,
    )
    if startup_config.parse_api_base_url
    else None
)


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

output_dir_path = os.path.abspath("output")
os.makedirs(output_dir_path, exist_ok=True)
app.mount("/output", StaticFiles(directory=output_dir_path), name="output")


class StartTaskRequest(BaseModel):
    goal: str = Field(min_length=1, description="User goal for the GUI agent")


class ParseScreenRequest(BaseModel):
    prompt: str = Field(min_length=1, description="User prompt that will drive future ADB capture flow")
    base64_image: Optional[str] = Field(default=None, description="Optional base64 image for direct parse testing")
    filename: str = Field(default="screen.png", description="Logical filename for multipart upload")


class SequentialExecutionRequest(BaseModel):
    goal: str = Field(min_length=1, description="User goal to achieve")
    device_id: str = Field(default="144321556E009492", description="Android device ID")
    base64_image: Optional[str] = Field(default=None, description="Optional initial screenshot as base64")
    max_steps: int = Field(default=15, description="Maximum execution steps")
    step_delay_sec: float = Field(default=3.0, description="Delay after each action in seconds")
    output_dir: str = Field(default="output", description="Directory to save results")
    task_id: Optional[str] = Field(default=None, description="Optional task ID for event emission")


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


@app.post("/api/v1/sequential/execute")
async def sequential_execute(payload: SequentialExecutionRequest) -> Dict[str, Any]:
    """
    Execute a sequential flow: OmniParser → Planner → Executor → Reflect loop.

    Flow:
    1. Capture screenshot and parse with OmniParser
    2. Send annotated screenshot to Planner
    3. If goal not fulfilled, Planner creates action plan
    4. Executor performs action, waits, captures new screenshot
    5. Reflect: wrong-action detection (visual diff / achiever), ADB back if needed
    6. Loop until goal fulfilled or max steps reached

    Args:
        payload: SequentialExecutionRequest with:
            - goal: User goal (required)
            - device_id: Android device ID (default: emulator-5554)
            - base64_image: Optional initial screenshot
            - max_steps: Maximum execution steps (default: 15)
            - step_delay_sec: Delay after actions (default: 3.0s)
            - output_dir: Directory to save results

    Returns:
        Dictionary with execution result including:
            - success: Overall success status
            - goal_achieved: Whether goal was fulfilled
            - total_steps: Number of steps executed
            - steps: Array of step details with screenshots, actions, plans
            - completion_message: Summary message
    """
    logger.info(f"[sequential/execute] Received request: goal={payload.goal}, device_id={payload.device_id}")

    if not mock_mode and omniparser_client is None:
        logger.error("[sequential/execute] OmniParser client not configured")
        raise HTTPException(status_code=503, detail="OmniParser client is not configured. Set MOCK_MODE=true to run without it.")

    try:
        # Decode initial screenshot if provided
        initial_screenshot = None
        if payload.base64_image:
                initial_screenshot = base64.b64decode(payload.base64_image, validate=True)
                logger.info("[sequential/execute] Initial screenshot decoded successfully")

        # Load configuration
        logger.info("[sequential/execute] Loading configuration...")
        config = startup_config
        logger.info("[sequential/execute] Configuration loaded successfully")

        # Create sequential executor
        logger.info("[sequential/execute] Creating SequentialExecutor (mock=%s)...", mock_mode)
        seq_executor = SequentialExecutor(
            device_id=payload.device_id,
            omniparser_client=omniparser_client,
            config=config,
            logger=logger,
            sequential_runner=sequentialRunner,
            max_steps=payload.max_steps,
            step_delay_sec=payload.step_delay_sec,
            mock=mock_mode,
        )
        logger.info("[sequential/execute] SequentialExecutor created successfully")

        # Create task in task manager
        logger.info(f"[sequential/execute] Creating task for goal: {payload.goal}")
        state = await task_manager.create_task(goal=payload.goal)
        logger.info(f"[sequential/execute] Task created: task_id={state.task_id}, initial_stage={state.stage}")

        async def _run() -> None:
            logger.info(f"[sequential/execute] Starting background executor for task {state.task_id}")
            try:
                await seq_executor.execute(
                    user_goal=payload.goal,
                    task_id=state.task_id,
                    initial_screenshot=initial_screenshot,
                    output_dir=payload.output_dir,
                )
                logger.info(f"[sequential/execute] Background executor completed for task {state.task_id}")
            except Exception as exc:
                logger.exception(f"[sequential/execute] Background executor failed for task {state.task_id}: {exc}")
                await task_manager.mark_failed(state.task_id, str(exc))

        worker = asyncio.create_task(_run())
        logger.info(f"[sequential/execute] Background task created for task_id={state.task_id}")

        await task_manager.set_worker(state.task_id, worker)
        logger.info(f"[sequential/execute] Worker registered. Returning task_id={state.task_id} to client")

        return { "task_id": state.task_id }

        # Execute the sequential flow
        # result = await seq_executor.execute(
        #     user_goal=payload.goal,
        #     initial_screenshot=initial_screenshot,
        #     output_dir=payload.output_dir,
        # )

        # # Convert result to JSON-serializable format
        # return {
        #     "success": result.success,
        #     "goal_achieved": result.goal_achieved,
        #     "total_steps": result.total_steps,
        #     "completion_message": result.completion_message,
        #     "timestamp": result.timestamp,
        #     "errors": result.errors,
        #     "steps_summary": [
        #         {
        #             "step_number": step.step_number,
        #             "timestamp": step.timestamp,
        #             "action_executed": step.action_executed,
        #             "elements_detected": step.elements_detected,
        #             "goal_achieved": step.goal_achieved,
        #             "goal_check_reasoning": step.goal_check_reasoning,
        #             "error": step.error,
        #             "metadata": step.metadata,
        #         }
        #         for step in result.steps
        #     ],
        # }

    except HTTPException:
        logger.warning(f"[sequential/execute] HTTP exception raised")
        raise
    except Exception as e:
        logger.exception(f"[sequential/execute] Unexpected error during sequential execution: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Sequential execution failed: {str(e)}")


@app.post("/api/v1/backup/execute")
async def sequential_execute_backup(payload: SequentialExecutionRequest) -> Dict[str, Any]:
    """
    Execute a sequential flow: OmniParser → Planner → Executor loop.

    Flow:
    1. Capture screenshot and parse with OmniParser
    2. Send annotated screenshot to Planner
    3. If goal not fulfilled, Planner creates action plan
    4. Executor performs action, waits 5 seconds, captures new screenshot
    5. Loop until goal fulfilled or 50 steps reached

    Args:
        payload: SequentialExecutionRequest with:
            - goal: User goal (required)
            - device_id: Android device ID (default: emulator-5554)
            - base64_image: Optional initial screenshot
            - max_steps: Maximum execution steps (default: 15)
            - step_delay_sec: Delay after actions (default: 3.0s)
            - output_dir: Directory to save results

    Returns:
        Dictionary with execution result including:
            - success: Overall success status
            - goal_achieved: Whether goal was fulfilled
            - total_steps: Number of steps executed
            - steps: Array of step details with screenshots, actions, plans
            - completion_message: Summary message
    """
    if not mock_mode and omniparser_client is None:
        raise HTTPException(status_code=503, detail="OmniParser client is not configured. Set MOCK_MODE=true to run without it.")

    try:
        # Decode initial screenshot if provided
        initial_screenshot = None
        if payload.base64_image:
                initial_screenshot = base64.b64decode(payload.base64_image, validate=True)

        # Load configuration
        config = startup_config

        # Create sequential executor
        seq_executor = SequentialExecutor(
            device_id=payload.device_id,
            omniparser_client=omniparser_client,
            config=config,
            logger=logger,
            max_steps=payload.max_steps,
            step_delay_sec=payload.step_delay_sec,
            sequential_runner=sequentialRunner,
            mock=mock_mode,
        )

        state = await task_manager.create_task(goal=payload.goal)

        async def _run() -> None:
            await seq_executor.execute(
                user_goal=payload.goal,
                task_id=state.task_id,
                initial_screenshot=initial_screenshot,
                output_dir=payload.output_dir,
            )

        worker = asyncio.create_task(_run())

        await task_manager.set_worker(state.task_id, worker)

        # Execute the sequential flow
        # result = await seq_executor.execute(
        #     user_goal=payload.goal,
        #     task_id=state.task_id,
        #     initial_screenshot=initial_screenshot,
        #     output_dir=payload.output_dir,
        # )

        # Convert result to JSON-serializable format
        # return {
        #     "success": result.success,
        #     "goal_achieved": result.goal_achieved,
        #     "total_steps": result.total_steps,
        #     "completion_message": result.completion_message,
        #     "timestamp": result.timestamp,
        #     "errors": result.errors,
        #     "steps_summary": [
        #         {
        #             "step_number": step.step_number,
        #             "timestamp": step.timestamp,
        #             "action_executed": step.action_executed,
        #             "elements_detected": step.elements_detected,
        #             "goal_achieved": step.goal_achieved,
        #             "goal_check_reasoning": step.goal_check_reasoning,
        #             "error": step.error,
        #             "metadata": step.metadata,
        #         }
        #         for step in result.steps
        #     ],
        # }
        return { "task_id": state.task_id,}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Sequential execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Sequential execution failed: {str(e)}")



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
    logger.info(f"[WebSocket] Connection request for task_id={task_id}")
    
    # Retry logic: wait up to 2 seconds for task to be created (handles race condition)
    state = None
    max_retries = 20
    retry_delay_ms = 100
    
    for attempt in range(max_retries):
        state = await task_manager.get_state(task_id)
        if state is not None:
            logger.info(f"[WebSocket] Task found on attempt {attempt + 1}: task_id={task_id}, stage={state.stage}")
            break
        if attempt == 0:
            logger.warning(f"[WebSocket] Task not found yet (attempt 1/{max_retries}), retrying in {retry_delay_ms}ms...")
        await asyncio.sleep(retry_delay_ms / 1000.0)
    
    if state is None:
        logger.error(f"[WebSocket] Task not found after {max_retries} retries (waited ~2s). Rejecting connection for task_id={task_id}")
        await websocket.close(code=1008, reason="Task not found")
        return

    await websocket.accept()
    logger.info(f"[WebSocket] Connection accepted for task_id={task_id}")

    snapshot = await task_manager.snapshot(task_id)
    if snapshot is not None:
        event_count = len(snapshot.get("events", []))
        logger.info(f"[WebSocket] Sending replay buffer: {event_count} events for task_id={task_id}")
        for event in snapshot["events"]:
            await websocket.send_json(event)
    else:
        logger.info(f"[WebSocket] No snapshot available for task_id={task_id}")

    queue = await emitter.subscribe(task_id)
    logger.info(f"[WebSocket] Subscribed to live events for task_id={task_id}")

    try:
        while True:
            event = await queue.get()
            logger.debug(f"[WebSocket] Sending event: task_id={task_id}, type={event.type}, title={event.title}")
            await websocket.send_json(event.to_dict())
            if event.type in {"task_completed", "task_failed"}:
                logger.info(f"[WebSocket] Task ended with type={event.type}. Closing connection for task_id={task_id}")
                break
    except WebSocketDisconnect:
        logger.info(f"[WebSocket] Client disconnected for task_id={task_id}")
    except Exception as exc:
        logger.exception(f"[WebSocket] Unexpected error for task_id={task_id}: {exc}")
    finally:
        await emitter.unsubscribe(task_id, queue)
        if websocket.client_state.name != "DISCONNECTED":
            await websocket.close()
        logger.info(f"[WebSocket] Connection closed for task_id={task_id}")

