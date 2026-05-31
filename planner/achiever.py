"""
Achiever: narrows a high-level sub-goal into the immediate next mobile action.

Exported function
-----------------
    achieve(image, subgoal, executed_actions=None) -> AchieverOutput

---
Usage
---

    from planner import achieve
    from planner.models import AchieverOutput
    from PIL import Image

    image = Image.open("screenshot.png")

    result = achieve(
        image=image,
        subgoal="Navigate through Settings to enter the Wi-Fi section",
    )

    # result.next_action      — e.g. "Tap the 'Wi-Fi' row in the Settings list"
    # result.subgoal_achieved — False until the sub-goal is complete
    # result.redo_from_idx    — None (or an index if redo is needed)

    # Pass the growing history of executed actions on subsequent calls:
    history = [result.next_action]
    result2 = achieve(image=next_screenshot, subgoal=subgoal, executed_actions=history)

Error handling::

    from planner import achieve
    from mllm import MllmOutputError
    import litellm

    try:
        result = achieve(image, subgoal)
    except MllmOutputError:
        # MLLM response could not be parsed — check logs, retry
        ...
    except litellm.APIError:
        # API quota / connectivity issue
        ...
"""

import logging
from typing import List, Optional

import litellm
from PIL import Image

from config import Config
from mllm import BaseMllm, MllmOutputError
from planner.models import AchieverOutput

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MLLM system prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a precise mobile app guide assistant who delivers one clear action at a time.\n\n"
    "Each turn you receive a current mobile screenshot, a high-level sub-goal the user "
    "is working toward, and a history of actions already executed toward that sub-goal.\n\n"
    "Your responsibilities:\n\n"
    "1. Determine the single immediate next action that moves the user one step closer "
    "to the sub-goal. Express it exactly as a step in a mobile user guide — "
    "name the UI element, its position on the screen, and the gesture to perform. "
    "Be as specific as a good instruction manual: "
    "'Tap the blue Wi-Fi toggle at the top of the Wi-Fi settings screen' "
    "is the right level of detail.\n\n"
    "2. Assess subgoal_achieved: set it to true when the screenshot confirms the "
    "sub-goal is fully accomplished, so the caller can advance to the next phase.\n\n"
    "3. Assess redo_from_idx: when you observe that a previously executed action "
    "produced a screen state that makes the intended path unworkable "
    "(an unexpected dialog, a wrong menu branch, a feature that requires a prior step), "
    "identify the zero-based index in the executed-actions list from which "
    "the agent should redo. Leave it null when the current path remains viable.\n\n"
    "Ground every response in what is actually visible on the screenshot. "
    "Keep the next_action concise yet complete — one instruction, one gesture."
)


# ---------------------------------------------------------------------------
# Dedicated MLLM
# ---------------------------------------------------------------------------


class _AchieverMllm(BaseMllm[AchieverOutput]):
    """MLLM specialised for narrowing a sub-goal into the next concrete action."""

    def __init__(self) -> None:
        super().__init__(system_prompt=_SYSTEM_PROMPT, output_class=AchieverOutput)


# ---------------------------------------------------------------------------
# User message builder
# ---------------------------------------------------------------------------


def _build_user_message(subgoal: str, executed_actions: Optional[List[str]]) -> str:
    """Compose the user message from the sub-goal and optional execution history."""
    lines = [f"Sub-goal to accomplish:\n{subgoal}"]

    if executed_actions:
        lines.append("\nActions already executed toward this sub-goal:")
        for idx, action in enumerate(executed_actions):
            lines.append(f"  [{idx}] {action}")
        lines.append(
            "\nDetermine whether these actions led to the right screen state, "
            "then provide the next step."
        )
    else:
        lines.append(
            "\nNo actions have been executed yet — determine the very first step."
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Mock fallback
# ---------------------------------------------------------------------------


def _mock_achieve(
    subgoal: str, executed_actions: Optional[List[str]]
) -> AchieverOutput:
    step = len(executed_actions) + 1 if executed_actions else 1
    return AchieverOutput(
        next_action=f"[MOCK] Step {step}: Perform the next action toward '{subgoal[:60]}'",
        subgoal_achieved=False,
        redo_from_idx=None,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def achieve(
    image: Image.Image,
    subgoal: str,
    executed_actions: Optional[List[str]] = None,
) -> AchieverOutput:
    """
    Narrow a high-level sub-goal into the immediate next concrete mobile action.

    Analyses the current screenshot, the sub-goal, and any previously executed
    actions to produce a single human-readable instruction — like one step in a
    mobile user guide — that moves the user one interaction closer to completing
    the sub-goal.

    Args:
        image:            Current mobile screenshot as a PIL Image.
        subgoal:          One high-level sub-goal from the planner
                          (e.g. "Navigate through Settings to the Wi-Fi section").
        executed_actions: Ordered list of action strings already executed toward
                          this sub-goal. Pass None or omit on the first call;
                          append each result.next_action before the next call.

    Returns:
        AchieverOutput with:
        - next_action      — the concrete next step as a mobile guide instruction
        - subgoal_achieved — True when the screenshot confirms completion
        - redo_from_idx    — index to redo from if a previous action broke the path
    """
    _logger.info(
        "Achieving sub-goal: %.100s  (executed: %d)",
        subgoal,
        len(executed_actions) if executed_actions else 0,
    )

    if Config().mock_mode:
        result = _mock_achieve(subgoal, executed_actions)
        _logger.info("[MOCK] next_action: %s", result.next_action)
        return result

    user_message = _build_user_message(subgoal, executed_actions)
    mllm = _AchieverMllm()

    try:
        result = mllm.complete(user_message=user_message, image=image)
    except MllmOutputError as e:
        _logger.error("Achiever MLLM output invalid: %s", e)
        raise
    except litellm.APIError as e:
        _logger.error("Achiever MLLM API error: %s", e)
        raise

    _logger.info(
        "next_action=%r  achieved=%s  redo_from=%s",
        result.next_action,
        result.subgoal_achieved,
        result.redo_from_idx,
    )
    return result
