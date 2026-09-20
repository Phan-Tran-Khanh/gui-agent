"""Regression tests for task-scoped execution artifacts."""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import unittest
from pathlib import Path

from app.backend.models import AgentEvent
from app.backend.task_manager import TaskManager


class TaskArtifactTests(unittest.TestCase):
    def test_task_manager_persists_manifest_and_event_log_per_task(self) -> None:
        async def scenario(root: str) -> str:
            manager = TaskManager(artifact_root=root)
            state = await manager.create_task("set alarm at 8:00")
            await manager.append_event(
                state.task_id,
                AgentEvent(
                    eventId="event-1",
                    taskId=state.task_id,
                    sequence=0,
                    timestamp="2026-09-21T00:00:00+00:00",
                    stage="planning",
                    type="task_started",
                    title="Started",
                ),
            )
            return state.task_id

        with tempfile.TemporaryDirectory() as root:
            task_id = asyncio.run(scenario(root))
            task_dir = Path(root) / task_id

            manifest = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
            self.assertEqual(task_id, manifest["task"]["task_id"])
            self.assertEqual("task_started", manifest["events"][0]["type"])

            run_log = (task_dir / "run.log").read_text(encoding="utf-8")
            self.assertIn("task_started", run_log)
            self.assertIn(task_id, run_log)

    def test_legacy_executor_writes_screenshots_under_task_directory(self) -> None:
        from app.backend.sequential_executor import SequentialExecutor
        from config import Config

        logger = logging.getLogger("test.task_artifacts")
        logger.disabled = True
        executor = SequentialExecutor(
            device_id="emulator-5554",
            omniparser_client=None,
            config=Config(mock_mode=True),
            logger=logger,
            max_steps=1,
            step_delay_sec=0.0,
            mock=True,
        )

        with tempfile.TemporaryDirectory() as root:
            asyncio.run(
                executor.execute(
                    user_goal="open settings",
                    task_id="task-artifacts",
                    output_dir=root,
                )
            )

            task_dir = Path(root) / "task-artifacts"
            self.assertTrue((task_dir / "step-001" / "raw.png").is_file())
            self.assertTrue((task_dir / "step-001" / "annotated.png").is_file())
            self.assertTrue((task_dir / "step-001" / "action.json").is_file())
            self.assertFalse((Path(root) / "step_1_raw.png").exists())


if __name__ == "__main__":
    unittest.main()
