"""
Skills registry for mobile GUI automation.

Defines all actions the MLLM executor can choose from (PhoneAction) and the
ActionOutput Pydantic class that constrains MLLM output so it maps directly to
executable ADB commands.

Element-based actions (TAP, LONG_PRESS, INPUT) use element_id — the numeric
ID shown on the annotated screenshot and listed in screen_info — instead of
raw pixel coordinates. The executor resolves the ID to actual screen
coordinates using the OmniParser element list.

get_skills_prompt() returns the formatted action description injected into
every executor system prompt.
"""

from enum import Enum
from typing import Optional

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

    Element-based actions identify the target by its ID in screen_info rather
    than by raw pixel coordinates, making decisions robust to screen resolution.

    Per-action constraints
    ----------------------
    TAP          element_id=<id>                   value=null   position=null
    INPUT        element_id=<id>   value=<text>                 position=null
    LONG_PRESS   element_id=<id>                   value=null   position=null
    SWIPE        element_id=null   value=null   position=[[x1,y1],[x2,y2]]
    ENTER        element_id=null   value=null   position=null
    NAVIGATE_BACK  element_id=null  value=null  position=null
    NAVIGATE_HOME  element_id=null  value=null  position=null
    OPEN_APP     element_id=null   value=<package name>         position=null
    WAIT         element_id=null   value=null   position=null
    ANSWER       element_id=null   value=<status message>       position=null
    """

    action_type: PhoneAction = Field(description="The action to perform on the device.")
    element_id: Optional[int] = Field(
        default=None,
        description=(
            "ID of the interactable element to act on, as shown in screen_info "
            "and on the annotated screenshot. Required for TAP, INPUT, LONG_PRESS."
        ),
    )
    value: Optional[str] = Field(
        default=None,
        description=(
            "Text payload: string to type (INPUT), Android package name (OPEN_APP), "
            "or completion status (ANSWER)."
        ),
    )
    direction: Optional[str] = Field(
        default=None,
        description="Swipe direction for SWIPE: one of 'up', 'down', 'left', 'right'.",
    )
    distance: Optional[str] = Field(
        default="medium",
        description=(
            "Swipe distance for SWIPE: 'short', 'medium', or 'long'. "
            "Defaults to 'medium' when omitted."
        ),
    )


_SKILL_LINES = (
    "1.  INPUT         — Type text into an element identified by its ID.\n"
    "                    element_id: ID from screen_info  |  value: text to type\n"
    "2.  SWIPE         — Swipe the screen in a direction.\n"
    "                    direction: 'up'|'down'|'left'|'right'\n"
    "                    distance:  'short'|'medium'|'long'  (default: medium)\n"
    "3.  TAP           — Tap on an element identified by its ID.\n"
    "                    element_id: ID from screen_info\n"
    "4.  ANSWER        — Mark the task as complete.\n"
    "                    value: status message (e.g. 'task complete')\n"
    "5.  ENTER         — Press the Enter / confirm key. No parameters.\n"
    "6.  LONG_PRESS    — Long-press an element identified by its ID.\n"
    "                    element_id: ID from screen_info\n"
    "7.  NAVIGATE_BACK — Press the device back button. No parameters.\n"
    "8.  NAVIGATE_HOME — Go to the device home screen. No parameters.\n"
    "9.  OPEN_APP      — Launch an application by its Android package name.\n"
    "                    value: package name (e.g. com.android.settings)\n"
    "10. WAIT          — Wait for the UI to settle. No parameters."
)


def get_skills_prompt() -> str:
    """Return the formatted skills description for injection into MLLM system prompts."""
    return _SKILL_LINES
