"""
Enums for MLLM Module

Defines all enumerated types used across the planning and execution system.
"""

from enum import Enum


class ExecutionStatus(Enum):
    """Status of execution for tasks, milestones, and subtasks."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ActionType(Enum):
    """Types of GUI actions that can be executed."""
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    IDENTIFY = "identify"
    WAIT = "wait"
    BACK = "back"


class PlanStatus(Enum):
    """Overall status of a plan."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    STALLED = "stalled"


class ReplannReason(Enum):
    """Reasons for replanning when execution fails."""
    ELEMENT_NOT_FOUND = "element_not_found"
    ACTION_FAILED = "action_failed"
    UNEXPECTED_SCREEN = "unexpected_screen"
    STALLED_INTERACTION = "stalled_interaction"
    DEPENDENCY_FAILED = "dependency_failed"
    USER_INTERRUPT = "user_interrupt"
