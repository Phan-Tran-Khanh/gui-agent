from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import DefaultDict, Set

from .models import AgentEvent


class EventEmitter:
    """Per-task pub/sub using asyncio queues for websocket streaming."""

    def __init__(self) -> None:
        self._subscribers: DefaultDict[str, Set[asyncio.Queue[AgentEvent]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, task_id: str) -> asyncio.Queue[AgentEvent]:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue(maxsize=200)
        async with self._lock:
            self._subscribers[task_id].add(queue)
        return queue

    async def unsubscribe(self, task_id: str, queue: asyncio.Queue[AgentEvent]) -> None:
        async with self._lock:
            if task_id not in self._subscribers:
                return
            self._subscribers[task_id].discard(queue)
            if not self._subscribers[task_id]:
                self._subscribers.pop(task_id, None)

    async def publish(self, task_id: str, event: AgentEvent) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(task_id, set()))

        for queue in queues:
            if queue.full():
                try:
                    _ = queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await queue.put(event)
