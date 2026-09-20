from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Dict, List, Optional

from .models import AgentEvent, AgentStage, TaskState, new_task_id, now_iso


class TaskManager:
    """Tracks task lifecycle and keeps a replay buffer for websocket reconnects."""

    def __init__(self, artifact_root: str | Path = "output-live") -> None:
        self._states: Dict[str, TaskState] = {}
        self._events: DefaultDict[str, List[AgentEvent]] = defaultdict(list)
        self._workers: Dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self.artifact_root = Path(artifact_root)

    async def create_task(self, goal: str) -> TaskState:
        task_id = new_task_id()
        state = TaskState(task_id=task_id, goal=goal, created_at=now_iso())
        async with self._lock:
            self._states[task_id] = state
            self._write_snapshot_locked(task_id)
            self._append_run_log_locked(
                task_id,
                f"{state.created_at} | queued | task_created | {task_id} | {goal}",
            )
        return state

    async def get_state(self, task_id: str) -> Optional[TaskState]:
        async with self._lock:
            return self._states.get(task_id)

    async def set_worker(self, task_id: str, worker: asyncio.Task[None]) -> None:
        async with self._lock:
            self._workers[task_id] = worker

    async def append_event(self, task_id: str, event: AgentEvent) -> None:
        async with self._lock:
            self._events[task_id].append(event)
            state = self._states.get(task_id)
            if state:
                state.stage = event.stage
                if event.type == "task_completed":
                    state.completed = True
                if event.type == "task_failed":
                    state.failed = True
                    state.error = event.description
            self._write_snapshot_locked(task_id)
            self._append_run_log_locked(
                task_id,
                (
                    f"{event.timestamp} | {event.stage} | {event.type} | "
                    f"{task_id} | {event.title} | {event.description or ''}"
                ),
            )

    async def get_events(self, task_id: str) -> List[AgentEvent]:
        async with self._lock:
            return list(self._events.get(task_id, []))

    async def mark_failed(self, task_id: str, error: str) -> None:
        async with self._lock:
            state = self._states.get(task_id)
            if state:
                state.stage = "failed"
                state.failed = True
                state.error = error
                self._write_snapshot_locked(task_id)
                self._append_run_log_locked(
                    task_id,
                    f"{now_iso()} | failed | task_failed | {task_id} | {error}",
                )

    async def cancel_task(self, task_id: str) -> bool:
        async with self._lock:
            worker = self._workers.get(task_id)
        if not worker:
            return False

        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass

        async with self._lock:
            state = self._states.get(task_id)
            if state:
                state.stage = "failed"
                state.failed = True
                state.error = "Cancelled by user"
                self._write_snapshot_locked(task_id)
                self._append_run_log_locked(
                    task_id,
                    f"{now_iso()} | failed | task_cancelled | {task_id} | Cancelled by user",
                )
        return True

    async def mark_active_tasks_interrupted(self, reason: str = "Backend shutdown interrupted task") -> None:
        """Persist a terminal state for tasks still running during a clean shutdown."""
        async with self._lock:
            for task_id, state in self._states.items():
                if state.completed or state.failed:
                    continue
                state.stage = "failed"
                state.failed = True
                state.error = reason
                self._write_snapshot_locked(task_id)
                self._append_run_log_locked(
                    task_id,
                    f"{now_iso()} | failed | task_interrupted | {task_id} | {reason}",
                )

    async def snapshot(self, task_id: str) -> Optional[Dict[str, object]]:
        async with self._lock:
            state = self._states.get(task_id)
            if not state:
                return None
            events = [event.to_dict() for event in self._events.get(task_id, [])]
            return {
                "task": state.to_dict(),
                "events": events,
            }

    def _task_dir(self, task_id: str) -> Path:
        return self.artifact_root / task_id

    def _write_snapshot_locked(self, task_id: str) -> None:
        state = self._states.get(task_id)
        if state is None:
            return

        directory = self._task_dir(task_id)
        directory.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "task": state.to_dict(),
            "events": [event.to_dict() for event in self._events.get(task_id, [])],
        }
        manifest_path = directory / "task.json"
        temp_path = directory / "task.json.tmp"
        temp_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        temp_path.replace(manifest_path)

    def _append_run_log_locked(self, task_id: str, line: str) -> None:
        directory = self._task_dir(task_id)
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "run.log").open("a", encoding="utf-8") as handle:
            handle.write(line.rstrip() + "\n")
