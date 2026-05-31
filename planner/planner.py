"""
Planner: breaks a user task into three actionable mobile sub-goals.

Exported function
-----------------
    plan(task, image) -> List[str]

---
Usage
---

    from planner import plan
    from PIL import Image

    image = Image.open("screenshot.png")
    subgoals = plan(task="Search for cheap flights to Tokyo", image=image)

    # subgoals — list of exactly 3 strings, each a concrete mobile action step:
    #   ["Open the search bar at the top of the screen",
    #    "Type 'cheap flights to Tokyo' into the search field",
    #    "Tap the Search button to submit and view results"]

Action examples
---------------

    task="Send a message to John saying hello"
        → ["Open the messaging app on the home screen",
           "Find and tap the conversation with John",
           "Type 'hello' and tap the Send button"]

    task="Turn on Wi-Fi"
        → ["Swipe down from the top to open the notification shade",
           "Tap the Wi-Fi icon to toggle it on",
           "Confirm Wi-Fi is active and connected"]

Error handling::

    from planner import plan
    from mllm import MllmOutputError
    import litellm

    try:
        subgoals = plan(task, image)
    except MllmOutputError:
        # MLLM response could not be parsed — check logs, retry
        ...
    except litellm.RateLimitError:
        # Back off and retry
        ...
    # Mock mode returns synthetic sub-goals without any API call.
"""

import logging
from typing import List

import litellm
from PIL import Image

from config import Config
from mllm import BaseMllm, MllmOutputError
from planner.models import PlanOutput

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MLLM system prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a strategic mobile task planner for Android and iOS devices.\n\n"
    "Your responsibility is to study the user's goal and the current mobile screenshot, "
    "then decompose that goal into exactly three high-level sub-goals that, "
    "pursued in order, guide the user from the current state to full completion.\n\n"
    "Each sub-goal represents a meaningful phase of the journey — "
    "a purposeful stage that may require several screen interactions to finish. "
    "Think in terms of navigation milestones: reaching the right app or section, "
    "arriving at the specific feature, and accomplishing the final action.\n\n"
    "Shape each sub-goal as a forward-moving intention expressed with an active English verb "
    "appropriate for mobile navigation — words like reach, open, navigate, browse, "
    "locate, select, configure, confirm, complete, and so on.\n\n"
    "Calibrate the scope of each sub-goal to the mobile context: "
    "a sub-goal should describe a purposeful stage of the task, "
    "broad enough to encompass several taps or swipes, "
    "yet specific enough that an agent clearly knows what to pursue next.\n\n"
    "Sequence the three sub-goals so each one advances the task from "
    "where the previous left off, forming a coherent path to the final outcome."
)


# ---------------------------------------------------------------------------
# Dedicated MLLM
# ---------------------------------------------------------------------------

class _PlannerMllm(BaseMllm[PlanOutput]):
    """MLLM specialised for task decomposition into mobile sub-goals."""

    def __init__(self) -> None:
        super().__init__(system_prompt=_SYSTEM_PROMPT, output_class=PlanOutput)


# ---------------------------------------------------------------------------
# Mock fallback
# ---------------------------------------------------------------------------

def _mock_plan(task: str) -> List[str]:
    return [
        f"[MOCK] Reach the application or section relevant to: {task[:60]}",
        "[MOCK] Navigate to the specific feature or setting within that section",
        "[MOCK] Complete the target action and confirm successful outcome",
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plan(task: str, image: Image.Image) -> List[str]:
    """
    Break a user task into three sequential high-level mobile sub-goals.

    Analyses the screenshot alongside the task description and returns three
    ordered navigation milestones — each a purposeful phase of the journey,
    not a single atomic action — that together accomplish the task.

    Args:
        task:  Plain-English description of what the user wants to achieve
               (e.g. "Change Wi-Fi to Public HCMUS").
        image: Current mobile screenshot as a PIL Image.

    Returns:
        List of exactly three strings, each a high-level mobile sub-goal.
    """
    _logger.info("Planning task: %.120s", task)

    if Config().mock_mode:
        subgoals = _mock_plan(task)
        _logger.info("[MOCK] Returning synthetic plan")
        for i, sg in enumerate(subgoals, 1):
            _logger.info("[MOCK] Sub-goal %d: %s", i, sg)
        return subgoals

    user_message = f"Task to accomplish:\n{task}"

    mllm = _PlannerMllm()

    try:
        output = mllm.complete(user_message=user_message, image=image)
    except MllmOutputError as e:
        _logger.error("Planner MLLM output invalid: %s", e)
        raise
    except litellm.APIError as e:
        _logger.error("Planner MLLM API error: %s", e)
        raise

    subgoals = output.as_list()
    for i, sg in enumerate(subgoals, 1):
        _logger.info("Sub-goal %d: %s", i, sg)

    return subgoals
