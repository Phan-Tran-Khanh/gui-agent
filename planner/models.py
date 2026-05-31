"""
Planner output models.

PlanOutput holds exactly three named sub-goals that together accomplish a
high-level mobile task. Using distinct fields instead of a list makes the
structure explicit and self-documenting for both the MLLM and the caller.

AchieverOutput holds the result of narrowing a single sub-goal into the
immediate next human-readable action, along with completion status and an
optional redo signal when a previous action led to an unworkable state.
"""

from typing import Optional

from pydantic import BaseModel, Field


class PlanOutput(BaseModel):
    """
    A three-phase plan for accomplishing a high-level mobile task.

    Each sub-goal represents a distinct navigation phase — not an atomic
    screen tap, but a purposeful stage of the journey that may span several
    interactions.

    Example (task: "Change Wi-Fi to Public HCMUS"):
        subgoal_1 = "Reach the application menu that contains the Settings app"
        subgoal_2 = "Navigate through Settings to enter the Wi-Fi section"
        subgoal_3 = "Browse the available networks, select Public HCMUS, and
                     complete the connection until the status shows connected"
    """

    subgoal_1: str = Field(
        description=(
            "First phase: reach or open the application, menu, or section "
            "of the mobile OS that is the starting point for this task."
        )
    )
    subgoal_2: str = Field(
        description=(
            "Second phase: navigate within that application or section "
            "to arrive at the specific feature, setting, or screen "
            "where the core action will take place."
        )
    )
    subgoal_3: str = Field(
        description=(
            "Third phase: carry out the target action within that screen "
            "and confirm or verify that the task has been accomplished successfully."
        )
    )

    def as_list(self) -> list:
        """Return the three sub-goals as an ordered list."""
        return [self.subgoal_1, self.subgoal_2, self.subgoal_3]


class AchieverOutput(BaseModel):
    """
    Result of narrowing a single high-level sub-goal into the immediate next action.

    Fields
    ------
    next_action
        The concrete next step expressed as a human-readable mobile instruction —
        specific enough for an agent (or user) to act on directly.
        Written like a step in a mobile user guide:
        e.g. "Tap the blue 'Wi-Fi' row inside the Settings list to open Wi-Fi settings."

    subgoal_achieved
        True when the current screenshot confirms the sub-goal is complete.
        The caller should stop executing and advance to the next sub-goal.

    redo_from_idx
        When a previously executed action produced an unexpected state that
        makes the current path unworkable, set this to the zero-based index
        in the executed-actions list from which the agent should redo.
        None means the current execution path is still valid.

    Example — normal step::

        AchieverOutput(
            next_action="Tap the 'Wi-Fi' row in the Settings list",
            subgoal_achieved=False,
            redo_from_idx=None,
        )

    Example — sub-goal complete::

        AchieverOutput(
            next_action="Wi-Fi is now connected to Public HCMUS.",
            subgoal_achieved=True,
            redo_from_idx=None,
        )

    Example — redo required::

        AchieverOutput(
            next_action="Dismiss the unexpected permission dialog by tapping 'Allow'.",
            subgoal_achieved=False,
            redo_from_idx=2,
        )
    """

    next_action: str = Field(
        description=(
            "The immediate next action written as a clear mobile user-guide step. "
            "Name the element, its location on screen, and the gesture to perform. "
            "When the sub-goal is already achieved, describe the current confirmed state instead."
        )
    )
    subgoal_achieved: bool = Field(
        description=(
            "True when the screenshot confirms the sub-goal has been fully accomplished "
            "and the agent should advance to the next sub-goal."
        )
    )
    redo_from_idx: Optional[int] = Field(
        default=None,
        description=(
            "Zero-based index in the executed-actions list from which the agent must redo "
            "because a prior action led to an unworkable screen state. "
            "Null when the current execution path remains valid."
        ),
    )
