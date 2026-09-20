#!/usr/bin/env python3
"""Run the selected GUI-agent execution engine from the command line."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Any
from uuid import uuid4

from app.backend.omniparser_client import OmniParserClient
from app.backend.sequential_executor import SequentialExecutor
from config import Config
from execution.backend_adapter import (
    BackendExecutionResult,
    ExecutionEngine,
    create_android_adapter,
    run_with_engine,
)
from grounder.grounder import parse_screen as parse_grounded_screen


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_logger = logging.getLogger("eval")


class _ConsoleEvents:
    """Expose the existing event shape without coupling the CLI to FastAPI."""

    async def emit(self, _task_id: str, **event: Any) -> None:
        _logger.info("[%s] %s", event["event_type"], event["title"])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GUI Agent — execute a task on a mobile device",
    )
    parser.add_argument("task", help="Natural-language task to accomplish")
    parser.add_argument(
        "--device-id",
        "-d",
        default=None,
        help="Android device ID or emulator serial (for example emulator-5554).",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=20,
        help="Maximum controller actions (default: 20).",
    )
    parser.add_argument(
        "--engine",
        choices=[engine.value for engine in ExecutionEngine],
        default=None,
        help="Override EXECUTION_ENGINE for this invocation.",
    )
    return parser.parse_args()


def _legacy_executor(
    *,
    device_id: str | None,
    config: Config,
    events: _ConsoleEvents,
    max_steps: int,
) -> SequentialExecutor:
    parser_client = (
        OmniParserClient(
            base_url=config.parse_api_base_url,
            timeout_sec=config.parse_api_timeout_sec,
            retry_count=config.parse_api_retry_count,
            retry_backoff_ms=config.parse_api_retry_backoff_ms,
        )
        if config.parse_api_base_url
        else None
    )
    return SequentialExecutor(
        device_id=device_id or "",
        omniparser_client=parser_client,
        config=config,
        logger=_logger,
        sequential_runner=events,
        max_steps=max_steps,
        mock=config.mock_mode,
    )


async def run(
    task: str,
    device_id: str | None,
    max_steps: int,
    engine: str | ExecutionEngine | None = None,
) -> BackendExecutionResult | Any:
    """Invoke the same selected engine used by the web backend."""

    config = Config()
    selected_engine = ExecutionEngine(engine) if engine is not None else config.execution_engine
    events = _ConsoleEvents()
    task_id = f"cli-{uuid4().hex[:12]}"
    adapter = (
        create_android_adapter(
            device_id=device_id,
            parse_screen=lambda image: parse_grounded_screen(image, config),
        )
        if selected_engine is not ExecutionEngine.LEGACY
        else None
    )
    legacy = (
        _legacy_executor(
            device_id=device_id,
            config=config,
            events=events,
            max_steps=max_steps,
        )
        if selected_engine is not ExecutionEngine.CLOSED_LOOP
        else None
    )

    _logger.info("Task: %s", task)
    _logger.info("Device: %s", device_id or "ADB default")
    _logger.info("Execution engine: %s", selected_engine.value)

    async def legacy_execute() -> Any:
        if legacy is None:
            raise RuntimeError("legacy executor was not created")
        return await legacy.execute(user_goal=task, task_id=task_id)

    async def closed_loop_execute() -> BackendExecutionResult:
        if adapter is None:
            raise RuntimeError("closed-loop adapter was not created")
        return await adapter.execute(
            task_id=task_id,
            goal=task,
            max_steps=max_steps,
            event_sink=events,
        )

    async def shadow_predict() -> None:
        if adapter is None:
            raise RuntimeError("closed-loop adapter was not created")
        try:
            await adapter.emit_shadow_prediction(task_id=task_id, goal=task, event_sink=events)
        except Exception as error:
            _logger.warning("Shadow prediction failed; continuing legacy execution: %s", error)

    result = await run_with_engine(
        selected_engine,
        legacy_execute=legacy_execute,
        closed_loop_execute=closed_loop_execute,
        shadow_predict=shadow_predict,
    )
    _logger.info("Goal verified: %s", result.goal_achieved)
    return result


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(
            run(
                task=args.task,
                device_id=args.device_id,
                max_steps=args.max_steps,
                engine=args.engine,
            )
        )
    except KeyboardInterrupt:
        _logger.info("Interrupted by user")
        sys.exit(130)
    except RuntimeError as exc:
        _logger.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
