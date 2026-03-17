from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import DefaultDict, Dict, List, Optional

from .models import AgentEvent, AgentStage, TaskState, new_task_id, now_iso


class TaskManager:
    """Tracks task lifecycle and keeps a replay buffer for websocket reconnects."""

    def __init__(self) -> None:
        self._states: Dict[str, TaskState] = {}
        self._events: DefaultDict[str, List[AgentEvent]] = defaultdict(list)
        self._workers: Dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def create_task(self, goal: str) -> TaskState:
        task_id = new_task_id()
        state = TaskState(task_id=task_id, goal=goal, created_at=now_iso())
        async with self._lock:
            self._states[task_id] = state
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
        return True

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
