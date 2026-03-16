from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
from uuid import uuid4


AgentStage = Literal[
    "queued",
    "planning",
    "executing_subgoal",
    "reflecting",
    "replanning",
    "completed",
    "failed",
]

AgentEventType = Literal[
    "task_started",
    "plan_generated",
    "subgoal_started",
    "gui_state_updated",
    "action_decided",
    "action_executed",
    "reflection_updated",
    "replan_triggered",
    "task_completed",
    "task_failed",
]


@dataclass
class AgentEvent:
    eventId: str
    taskId: str
    sequence: int
    timestamp: str
    stage: AgentStage
    type: AgentEventType
    title: str
    description: Optional[str] = None
    subgoalId: Optional[str] = None
    subgoalIndex: Optional[int] = None
    confidence: Optional[float] = None
    reasoning: Optional[str] = None
    screenshotUrl: Optional[str] = None
    screenshotBase64: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eventId": self.eventId,
            "taskId": self.taskId,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "stage": self.stage,
            "type": self.type,
            "title": self.title,
            "description": self.description,
            "subgoalId": self.subgoalId,
            "subgoalIndex": self.subgoalIndex,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "screenshotUrl": self.screenshotUrl,
            "screenshotBase64": self.screenshotBase64,
            "metadata": self.metadata,
        }


@dataclass
class TaskState:
    task_id: str
    goal: str
    created_at: str
    stage: AgentStage = "queued"
    completed: bool = False
    failed: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "created_at": self.created_at,
            "stage": self.stage,
            "completed": self.completed,
            "failed": self.failed,
            "error": self.error,
        }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_task_id() -> str:
    return f"task-{uuid4().hex[:12]}"
