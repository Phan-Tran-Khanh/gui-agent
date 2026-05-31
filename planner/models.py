"""
Planner output models.

PlanOutput holds exactly three named sub-goals that together accomplish a
high-level mobile task. Using distinct fields instead of a list makes the
structure explicit and self-documenting for both the MLLM and the caller.
"""

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
