"""
Executor: translates a natural language action + screenshot into an ADB device command.

Exported function
-----------------
    execute(action_text, image_base64, device_id) -> bool

---
Usage
---

Basic import::

    from executor import execute          # via __init__.py
    # or
    from executor.executor import execute # direct

Open a screenshot with Pillow, then call execute with a plain-English
description of what to do next::

    from PIL import Image

    image = Image.open("screenshot.png")

    success = execute(
        action_text="tap the Search button",
        image=image,
        device_id="emulator-5554",
    )

The function returns True when the action was executed on the device,
False on any failure (bad image, MLLM error, ADB error).

Action examples and what the MLLM is expected to produce
---------------------------------------------------------

    "tap the Login button"
        → ActionOutput(action_type=TAP, position=[540, 920])

    "type 'hello world' into the search field at the top"
        → ActionOutput(action_type=INPUT, value="hello world", position=[540, 120])

    "scroll down to see more results"
        → ActionOutput(action_type=SWIPE, position=[[540, 900], [540, 300]])

    "long press on the first list item"
        → ActionOutput(action_type=LONG_PRESS, position=[540, 400])

    "open the Settings app"
        → ActionOutput(action_type=OPEN_APP, value="com.android.settings")

    "go back to the previous screen"
        → ActionOutput(action_type=NAVIGATE_BACK)

    "the task is complete"
        → ActionOutput(action_type=ANSWER, value="task complete")

Error handling::

    from executor import execute
    from mllm import MllmOutputError
    import litellm

    try:
        ok = execute(action_text, image_base64, device_id)
    except litellm.RateLimitError:
        # back off and retry
        ...
    except litellm.AuthenticationError:
        # check API_KEY in .env
        ...
    # MllmOutputError and ADB failures are caught internally and return False.
"""

import logging

import litellm
from PIL import Image

from adb import adb
from executor.skills import ActionOutput, PhoneAction, get_skills_prompt
from mllm import BaseMllm, MllmOutputError

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MLLM system prompt — built once at import time, injected with all skills
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a mobile GUI automation agent.\n\n"
    "Given the current screenshot and an action instruction, select the correct "
    "device action and provide its required parameters.\n\n"
    "Available actions:\n" + get_skills_prompt() + "\n\n"
    "Rules:\n"
    "- Select exactly one action_type from the list above.\n"
    "- Read the screenshot carefully to determine precise pixel coordinates.\n"
    "- Set value only for INPUT (text to type), OPEN_APP (Android package name, "
    "e.g. com.android.settings), or ANSWER (completion status).\n"
    "- Set position as [x, y] for TAP, INPUT, LONG_PRESS; "
    "or [[x1, y1], [x2, y2]] for SWIPE.\n"
    "- Set value and position to null when the action does not require them."
)


# ---------------------------------------------------------------------------
# Dedicated MLLM
# ---------------------------------------------------------------------------


class _ExecutorMllm(BaseMllm[ActionOutput]):
    """MLLM specialised for executor action decisions."""

    def __init__(self) -> None:
        super().__init__(system_prompt=_SYSTEM_PROMPT, output_class=ActionOutput)


# ---------------------------------------------------------------------------
# ADB mapping — one function per action
# ---------------------------------------------------------------------------


def _do_tap(pos: list, device_id: str) -> bool:
    if len(pos) < 2:
        _logger.error("TAP requires [x, y], got: %s", pos)
        return False
    return adb.click((int(pos[0]), int(pos[1])), device_id)


def _do_input(pos: list, value: str, device_id: str) -> bool:
    if len(pos) < 2:
        _logger.error("INPUT requires [x, y], got: %s", pos)
        return False
    if not value:
        _logger.error("INPUT requires a non-empty text value")
        return False
    adb.click((int(pos[0]), int(pos[1])), device_id)  # focus element first
    return adb.input_text(value, device_id)


_SWIPE_DURATION_MS = 150  # fast gesture, not a slow drag


def _do_swipe(pos: list, device_id: str) -> bool:
    if len(pos) < 2:
        _logger.error("SWIPE requires [[x1,y1],[x2,y2]], got: %s", pos)
        return False
    start = (int(pos[0][0]), int(pos[0][1]))
    end = (int(pos[1][0]), int(pos[1][1]))
    return adb.drag(start, end, device_id, duration=_SWIPE_DURATION_MS)


def _do_long_press(pos: list, device_id: str) -> bool:
    if len(pos) < 2:
        _logger.error("LONG_PRESS requires [x, y], got: %s", pos)
        return False
    return adb.long_press((int(pos[0]), int(pos[1])), device_id)


def _do_open_app(package_name: str, device_id: str) -> bool:
    if not package_name.strip():
        _logger.error("OPEN_APP requires a non-empty package name")
        return False
    _logger.info("Opening package: %s", package_name)
    # monkey -p <package> launches the app's LAUNCHER activity without
    # needing an explicit activity name, making it the most reliable
    # way to start an app given only a package name.
    cmd = [
        "shell",
        "monkey",
        "-p",
        package_name,
        "-c",
        "android.intent.category.LAUNCHER",
        "1",
    ]
    success, output = adb.run_adb_command(cmd, device_id=device_id)
    if not success:
        _logger.error("Failed to open '%s': %s", package_name, output)
    return success


def _map_to_adb(output: ActionOutput, device_id: str) -> bool:
    """Route an ActionOutput to the corresponding ADB call."""
    action = output.action_type
    pos = output.position or []
    value = output.value or ""

    if action == PhoneAction.TAP:
        return _do_tap(pos, device_id)

    if action == PhoneAction.INPUT:
        return _do_input(pos, value, device_id)

    if action == PhoneAction.SWIPE:
        return _do_swipe(pos, device_id)

    if action == PhoneAction.LONG_PRESS:
        return _do_long_press(pos, device_id)

    if action == PhoneAction.ENTER:
        return adb.press_enter(device_id)

    if action == PhoneAction.NAVIGATE_BACK:
        return adb.navigate_back(device_id)

    if action == PhoneAction.NAVIGATE_HOME:
        return adb.navigate_home(device_id)

    if action == PhoneAction.OPEN_APP:
        return _do_open_app(value, device_id)

    if action == PhoneAction.WAIT:
        return adb.wait_action()

    if action == PhoneAction.ANSWER:
        _logger.info("Task marked complete: %s", value)
        return True

    _logger.error("Unhandled action type: %s", action)
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def execute(action_text: str, image: Image.Image, device_id: str) -> bool:
    """
    Execute a natural language action on the device.

    Converts the PIL screenshot to bytes, asks the executor MLLM to decide
    the precise action, then maps the structured output to an ADB command.

    Args:
        action_text: Natural language description of what to do
                     (e.g. "tap the Login button").
        image:       Current device screenshot as a PIL Image.
        device_id:   Android device ID or emulator serial (e.g. "emulator-5554").

    Returns:
        True if the action executed successfully, False otherwise.
    """
    _logger.info("Executing: %.120s", action_text)

    mllm = _ExecutorMllm()

    try:
        output = mllm.complete(user_message=action_text, image=image)
    except MllmOutputError as e:
        _logger.error("MLLM output invalid: %s", e)
        return False
    except litellm.APIError as e:
        _logger.error("MLLM API error: %s", e)
        return False

    _logger.info(
        "Action decided — type: %s  value: %s  position: %s",
        output.action_type,
        output.value,
        output.position,
    )

    return _map_to_adb(output, device_id)
