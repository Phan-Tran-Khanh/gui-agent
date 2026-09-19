"""Configuration and selection contracts for staged execution-engine rollout."""

from __future__ import annotations

import asyncio
import sys
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from config import Config
from execution.backend_adapter import BackendExecutionResult, ExecutionEngine, run_with_engine


class ExecutionEngineRolloutTests(unittest.TestCase):
    def test_legacy_is_the_default_and_invalid_engine_is_rejected(self) -> None:
        self.assertIs(ExecutionEngine.LEGACY, Config(mock_mode=True).execution_engine)
        self.assertIs(
            ExecutionEngine.CLOSED_LOOP,
            Config(mock_mode=True, execution_engine="closed_loop").execution_engine,
        )
        with self.assertRaises(ValidationError):
            Config(mock_mode=True, execution_engine="unsafe-unrecognized-engine")

    def test_shadow_keeps_legacy_authoritative_after_a_non_mutating_prediction(self) -> None:
        calls: list[str] = []

        async def legacy_execute() -> str:
            calls.append("legacy")
            return "legacy-result"

        async def closed_loop_execute() -> str:
            calls.append("closed_loop")
            return "closed-loop-result"

        async def shadow_predict() -> None:
            calls.append("shadow")

        result = asyncio.run(
            run_with_engine(
                ExecutionEngine.SHADOW,
                legacy_execute=legacy_execute,
                closed_loop_execute=closed_loop_execute,
                shadow_predict=shadow_predict,
            )
        )

        self.assertEqual("legacy-result", result)
        self.assertEqual(["shadow", "legacy"], calls)

    def test_closed_loop_bypasses_legacy_execution(self) -> None:
        calls: list[str] = []

        async def legacy_execute() -> str:
            calls.append("legacy")
            return "legacy-result"

        async def closed_loop_execute() -> str:
            calls.append("closed_loop")
            return "closed-loop-result"

        result = asyncio.run(
            run_with_engine(
                ExecutionEngine.CLOSED_LOOP,
                legacy_execute=legacy_execute,
                closed_loop_execute=closed_loop_execute,
            )
        )

        self.assertEqual("closed-loop-result", result)
        self.assertEqual(["closed_loop"], calls)

    def test_cli_accepts_the_same_engine_values(self) -> None:
        import eval as cli

        with patch.object(
            sys,
            "argv",
            ["eval.py", "open settings", "--device-id", "emulator-5554", "--engine", "shadow"],
        ):
            args = cli._parse_args()

        self.assertEqual("open settings", args.task)
        self.assertEqual("emulator-5554", args.device_id)
        self.assertEqual("shadow", args.engine)

    def test_closed_loop_cli_does_not_construct_the_legacy_executor(self) -> None:
        import eval as cli

        class Adapter:
            async def execute(self, **_kwargs: object) -> BackendExecutionResult:
                return BackendExecutionResult(
                    success=False,
                    goal_achieved=False,
                    total_steps=0,
                    failure_class="perception",
                )

        config = Config(mock_mode=True, execution_engine="legacy")
        with (
            patch.object(cli, "Config", return_value=config),
            patch.object(cli, "create_android_adapter", return_value=Adapter()),
            patch.object(cli, "_legacy_executor") as legacy_factory,
        ):
            result = asyncio.run(
                cli.run(
                    task="open settings",
                    device_id="emulator-5554",
                    max_steps=2,
                    engine=ExecutionEngine.CLOSED_LOOP,
                )
            )

        self.assertFalse(legacy_factory.called)
        self.assertFalse(result.goal_achieved)


if __name__ == "__main__":
    unittest.main()
