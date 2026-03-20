"""
Sequential Runner for Sequential Executor

Event-driven runner that emits messages to frontend as the sequential executor
progresses through steps: OmniParser → Planner → Executor loop.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional, Dict, Any

from .event_emitter import EventEmitter
from .models import AgentEvent, AgentStage, AgentEventType, now_iso
from .task_manager import TaskManager


class SequentialRunner:
    """
    Event emitter wrapper for Sequential Executor.
    
    Allows sequential executor to easily emit events to frontend via WebSocket.
    Similar to AgentRunner but designed for real-time step-by-step execution events.
    """

    def __init__(self, task_manager: TaskManager, emitter: EventEmitter) -> None:
        """
        Initialize the SequentialRunner.
        
        Args:
            task_manager: TaskManager instance for storing events
            emitter: EventEmitter instance for publishing events to frontend
        """
        self.task_manager = task_manager
        self.emitter = emitter
        self.sequence = 0

    async def emit(
        self,
        task_id: str,
        *,
        stage: AgentStage,
        event_type: AgentEventType,
        title: str,
        description: Optional[str] = None,
        subgoal_id: Optional[str] = None,
        subgoal_index: Optional[int] = None,
        confidence: Optional[float] = None,
        reasoning: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Emit an event to both task manager and event emitter.
        
        Args:
            task_id: Task ID for tracking
            stage: Current execution stage (planning, executing_subgoal, reflecting, etc.)
            event_type: Type of event (task_started, plan_generated, action_executed, etc.)
            title: Human-readable event title
            description: Optional detailed description
            subgoal_id: Optional subgoal identifier
            subgoal_index: Optional subgoal index (step number)
            confidence: Optional confidence score (0.0-1.0)
            reasoning: Optional reasoning/explanation
            metadata: Optional metadata dictionary
        """
        event = AgentEvent(
            eventId=f"{task_id}-{self.sequence}",
            taskId=task_id,
            sequence=self.sequence,
            timestamp=now_iso(),
            stage=stage,
            type=event_type,
            title=title,
            description=description,
            subgoalId=subgoal_id,
            subgoalIndex=subgoal_index,
            confidence=confidence,
            reasoning=reasoning,
            metadata=metadata or {},
        )
        
        self.sequence += 1
        
        # Store in task manager for later retrieval
        await self.task_manager.append_event(task_id, event)
        
        # Publish to frontend via event emitter
        await self.emitter.publish(task_id, event)
