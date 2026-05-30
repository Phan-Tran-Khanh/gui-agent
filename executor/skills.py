"""
Skills registry for mobile GUI automation.

Defines all actions the MLLM executor can choose from (PhoneAction) and the
ActionOutput Pydantic class that constrains MLLM output so it maps directly to
executable ADB commands.

get_skills_prompt() returns the formatted description injected into every
executor system prompt so the MLLM knows each action's purpose and required
parameters.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class PhoneAction(str, Enum):
    """All supported mobile device actions."""

    INPUT = "INPUT"
    SWIPE = "SWIPE"
    TAP = "TAP"
    ANSWER = "ANSWER"
    ENTER = "ENTER"
    LONG_PRESS = "LONG_PRESS"
    NAVIGATE_BACK = "NAVIGATE_BACK"
    NAVIGATE_HOME = "NAVIGATE_HOME"
    OPEN_APP = "OPEN_APP"
    WAIT = "WAIT"


class ActionOutput(BaseModel):
    """
    Structured output produced by the executor MLLM.

    Each field maps directly to an ADB call:

    - action_type  selects which ADB function to invoke.
    - value        carries a text payload (see per-action notes below).
    - position     carries screen coordinates (see per-action notes below).

    Per-action constraints
    ----------------------
    TAP          position=[x, y]                   value=null
    INPUT        position=[x, y]   value=<text>
    SWIPE        position=[[x1,y1],[x2,y2]]         value=null
    LONG_PRESS   position=[x, y]                   value=null
    ENTER        position=null                     value=null
    NAVIGATE_BACK  position=null                   value=null
    NAVIGATE_HOME  position=null                   value=null
    OPEN_APP     position=null     value=<app name>
    WAIT         position=null                     value=null
    ANSWER       position=null     value=<status message>
    """

    action_type: PhoneAction = Field(description="The action to perform on the device.")
    value: Optional[str] = Field(
        default=None,
        description=(
            "Text payload: string to type (INPUT), Android package name (OPEN_APP), "
            "or completion status (ANSWER). Null for all other actions."
        ),
    )
    position: Optional[List] = Field(
        default=None,
        description=(
            "[x, y] pixel coordinates for TAP, INPUT, LONG_PRESS. "
            "[[x1, y1], [x2, y2]] start and end coordinates for SWIPE. "
            "Null for ENTER, NAVIGATE_BACK, NAVIGATE_HOME, OPEN_APP, WAIT, ANSWER."
        ),
    )


_SKILL_LINES = (
    "1.  INPUT         — Type text into a focused element.\n"
    "                    value: string to type  |  position: [x, y] of target element\n"
    "2.  SWIPE         — Swipe across the screen.\n"
    "                    value: null  |  position: [[x1, y1], [x2, y2]] start → end\n"
    "3.  TAP           — Tap on an element.\n"
    "                    value: null  |  position: [x, y]\n"
    "4.  ANSWER        — Mark the task as complete.\n"
    "                    value: status message (e.g. 'task complete')  |  position: null\n"
    "5.  ENTER         — Press the Enter / confirm key.\n"
    "                    value: null  |  position: null\n"
    "6.  LONG_PRESS    — Long-press an element.\n"
    "                    value: null  |  position: [x, y]\n"
    "7.  NAVIGATE_BACK — Press the device back button.\n"
    "                    value: null  |  position: null\n"
    "8.  NAVIGATE_HOME — Go to the device home screen.\n"
    "                    value: null  |  position: null\n"
    "9.  OPEN_APP      — Launch an application by its Android package name.\n"
    "                    value: package name (e.g. com.android.settings)  |  position: null\n"
    "10. WAIT          — Wait for the UI to settle.\n"
    "                    value: null  |  position: null"
)


def get_skills_prompt() -> str:
    """Return the formatted skills description for injection into MLLM system prompts."""
    return _SKILL_LINES
