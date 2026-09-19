"""Public sequential-execution API compatibility during engine rollout."""

from __future__ import annotations

import asyncio
import logging
import tempfile
import unittest
from unittest.mock import patch

from config import Config
from execution.backend_adapter import BackendExecutionResult


class _LegacyExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return object()


class _ClosedLoopAdapter:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(self, **kwargs: object) -> BackendExecutionResult:
        self.calls.append(kwargs)
        return BackendExecutionResult(
            success=False,
            goal_achieved=False,
            total_steps=0,
            failure_class="perception",
        )


class ApiCompatibilityTests(unittest.TestCase):
    def test_sequential_request_fields_and_task_id_response_remain_stable_under_default_engine(self) -> None:
        from app.backend import backend

        request = backend.SequentialExecutionRequest(
            goal="open settings",
            device_id="emulator-5554",
            base64_image=None,
            max_steps=7,
            step_delay_sec=0.0,
            output_dir="output",
            task_id="legacy-client-task-id",
        )
        self.assertEqual(
            {
                "goal",
                "device_id",
                "base64_image",
                "max_steps",
                "step_delay_sec",
                "output_dir",
                "task_id",
            },
            set(request.model_dump()),
        )
        legacy = _LegacyExecutor()

        async def scenario() -> dict[str, object]:
            with (
                patch.object(backend, "startup_config", Config(mock_mode=True)),
                patch.object(backend, "mock_mode", True),
                patch.object(backend, "create_legacy_executor", return_value=legacy),
                patch.object(backend, "create_closed_loop_adapter") as closed_loop_factory,
            ):
                response = await backend.sequential_execute(request)
                await asyncio.sleep(0)
            self.assertFalse(closed_loop_factory.called)
            return response

        response = asyncio.run(scenario())

        self.assertEqual({"task_id"}, set(response))
        self.assertTrue(str(response["task_id"]).startswith("task-"))
        self.assertEqual(1, len(legacy.calls))
        self.assertEqual("open settings", legacy.calls[0]["user_goal"])

    def test_closed_loop_flag_uses_the_shared_adapter_instead_of_legacy_executor(self) -> None:
        from app.backend import backend

        request = backend.SequentialExecutionRequest(
            goal="open settings",
            device_id="emulator-5554",
            max_steps=3,
        )
        adapter = _ClosedLoopAdapter()

        async def scenario() -> dict[str, object]:
            with (
                patch.object(
                    backend,
                    "startup_config",
                    Config(mock_mode=True, execution_engine="closed_loop"),
                ),
                patch.object(backend, "mock_mode", True),
                patch.object(backend, "create_legacy_executor") as legacy_factory,
                patch.object(
                    backend,
                    "create_closed_loop_adapter",
                    return_value=adapter,
                ) as closed_loop_factory,
            ):
                response = await backend.sequential_execute(request)
                await asyncio.sleep(0)
            self.assertFalse(legacy_factory.called)
            self.assertTrue(closed_loop_factory.called)
            return response

        response = asyncio.run(scenario())

        self.assertEqual({"task_id"}, set(response))
        self.assertEqual(1, len(adapter.calls))
        self.assertEqual("open settings", adapter.calls[0]["goal"])
        self.assertEqual(3, adapter.calls[0]["max_steps"])

    def test_legacy_max_steps_without_goal_verification_is_terminal_failure(self) -> None:
        from app.backend.sequential_executor import SequentialExecutor

        class RecordingEvents:
            def __init__(self) -> None:
                self.events: list[dict[str, object]] = []

            async def emit(self, task_id: str, **event: object) -> None:
                self.events.append({"task_id": task_id, **event})

        events = RecordingEvents()
        executor_logger = logging.getLogger("test.sequential_executor")
        executor_logger.disabled = True
        executor = SequentialExecutor(
            device_id="emulator-5554",
            omniparser_client=None,
            config=Config(mock_mode=True),
            logger=executor_logger,
            sequential_runner=events,
            max_steps=1,
            step_delay_sec=0.0,
            mock=True,
        )

        with tempfile.TemporaryDirectory() as output_dir:
            result = asyncio.run(
                executor.execute(
                    user_goal="open settings",
                    task_id="task-max-steps",
                    output_dir=output_dir,
                )
            )

        self.assertFalse(result.success)
        self.assertFalse(result.goal_achieved)
        self.assertEqual("task_failed", events.events[-1]["event_type"])
        self.assertEqual("failed", events.events[-1]["stage"])
        action_events = [
            event
            for event in events.events
            if event["event_type"] in {"action_decided", "action_executed"}
        ]
        self.assertEqual(["m_1", "m_1"], [event["subgoal_id"] for event in action_events])


if __name__ == "__main__":
    unittest.main()
