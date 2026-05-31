"""
Executor: translates a natural language action + grounded screenshot into an ADB command.

Exported function
-----------------
    execute(action_text, image, device_id, elements, screen_info) -> bool

---
Usage
---

The executor is designed to work directly with the output of ground():

    from grounder import ground
    from executor import execute
    from PIL import Image

    # Step 1: ground the screenshot
    raw_image = Image.open("screenshot.png")
    enhanced_image, screen_info = await ground(raw_image)

    # Step 2: execute an action using the grounded result
    #   enhanced_image — annotated PIL Image with numbered bounding boxes
    #                    (input to the MLLM as the visual context)
    #   screen_info    — set-of-mark text injected into the MLLM user message
    #   elements       — OmniParserResult.interactable, used to resolve
    #                    element_id → screen coordinates before ADB dispatch
    success = execute(
        action_text="tap the Search button",
        image=enhanced_image,
        device_id="emulator-5554",
        elements=result.interactable,
        screen_info=screen_info,
    )

Action examples and what the MLLM is expected to produce
---------------------------------------------------------

    "tap the Login button"
        → ActionOutput(action_type=TAP, element_id=3)

    "type 'hello world' into the search field"
        → ActionOutput(action_type=INPUT, element_id=7, value="hello world")

    "long press on the first list item"
        → ActionOutput(action_type=LONG_PRESS, element_id=12)

    "scroll down to see more results"
        → ActionOutput(action_type=SWIPE, position=[[0.5, 0.8], [0.5, 0.2]])

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
        ok = execute(action_text, image, device_id, elements, screen_info)
    except litellm.RateLimitError:
        # back off and retry
        ...
    except litellm.AuthenticationError:
        # check API_KEY in .env
        ...
    # MllmOutputError and ADB failures are caught internally and return False.
"""

import logging
from typing import List, Optional, Tuple

import litellm
from PIL import Image

from adb import adb
from executor.skills import ActionOutput, PhoneAction, get_skills_prompt
from grounder.models import ParsedElement
from mllm import BaseMllm, MllmOutputError

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MLLM system prompt — built once at import time, injected with all skills
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a mobile GUI automation agent.\n\n"
    "You receive:\n"
    "  1. An annotated screenshot with numbered bounding boxes on every "
    "interactable UI element.\n"
    "  2. A screen_info list naming each element by its ID.\n"
    "  3. A natural language action instruction.\n\n"
    "Your task: select the correct action and identify the target element "
    "by its ID (for TAP, INPUT, LONG_PRESS) or provide the required parameters "
    "(value for INPUT/OPEN_APP/ANSWER, position for SWIPE).\n\n"
    "Available actions:\n" + get_skills_prompt() + "\n\n"
    "Rules:\n"
    "- Select exactly one action_type.\n"
    "- For TAP, INPUT, LONG_PRESS: set element_id to the ID shown on the "
    "annotated screenshot / listed in screen_info. Do NOT set position.\n"
    "- For SWIPE: set position as [[x1, y1], [x2, y2]] in normalised 0-1 "
    "coordinates. Do NOT set element_id.\n"
    "- For INPUT: also set value to the text to type.\n"
    "- For OPEN_APP: set value to the Android package name "
    "(e.g. com.android.settings).\n"
    "- For ANSWER: set value to a short completion status message.\n"
    "- Set all unused fields to null."
)


# ---------------------------------------------------------------------------
# Dedicated MLLM
# ---------------------------------------------------------------------------


class _ExecutorMllm(BaseMllm[ActionOutput]):
    """MLLM specialised for executor action decisions."""

    def __init__(self) -> None:
        super().__init__(system_prompt=_SYSTEM_PROMPT, output_class=ActionOutput)


# ---------------------------------------------------------------------------
# Element-to-pixel resolution
# ---------------------------------------------------------------------------


def _resolve_center(
    element_id: int,
    elements: List[ParsedElement],
    img_width: int,
    img_height: int,
) -> Optional[Tuple[int, int]]:
    """
    Convert an element ID to pixel coordinates using the OmniParser element list.

    Looks up the element whose idx matches element_id, then computes the
    centre of its normalised bbox scaled to actual image dimensions.
    """
    elem = next((e for e in elements if e.idx == element_id), None)
    if elem is None:
        _logger.error(
            "Element ID %d not found in %d elements", element_id, len(elements)
        )
        return None
    x1, y1, x2, y2 = elem.bbox
    cx = int(((x1 + x2) / 2) * img_width)
    cy = int(((y1 + y2) / 2) * img_height)
    return cx, cy


# ---------------------------------------------------------------------------
# ADB mapping — one function per action
# ---------------------------------------------------------------------------


def _do_tap(
    element_id: Optional[int],
    elements: List[ParsedElement],
    img_width: int,
    img_height: int,
    device_id: str,
) -> bool:
    if element_id is None:
        _logger.error("TAP requires element_id")
        return False
    coords = _resolve_center(element_id, elements, img_width, img_height)
    if coords is None:
        return False
    return adb.click(coords, device_id)


def _do_input(
    element_id: Optional[int],
    value: str,
    elements: List[ParsedElement],
    img_width: int,
    img_height: int,
    device_id: str,
) -> bool:
    if element_id is None:
        _logger.error("INPUT requires element_id")
        return False
    if not value:
        _logger.error("INPUT requires a non-empty text value")
        return False
    coords = _resolve_center(element_id, elements, img_width, img_height)
    if coords is None:
        return False
    adb.click(coords, device_id)  # focus element first
    return adb.input_text(value, device_id)


def _do_long_press(
    element_id: Optional[int],
    elements: List[ParsedElement],
    img_width: int,
    img_height: int,
    device_id: str,
) -> bool:
    if element_id is None:
        _logger.error("LONG_PRESS requires element_id")
        return False
    coords = _resolve_center(element_id, elements, img_width, img_height)
    if coords is None:
        return False
    return adb.long_press(coords, device_id)


_SWIPE_DURATION_MS = 150  # fast gesture, not a slow drag


def _do_swipe(pos: list, img_width: int, img_height: int, device_id: str) -> bool:
    if len(pos) < 2:
        _logger.error("SWIPE requires [[x1,y1],[x2,y2]], got: %s", pos)
        return False
    start = (int(pos[0][0] * img_width), int(pos[0][1] * img_height))
    end = (int(pos[1][0] * img_width), int(pos[1][1] * img_height))
    return adb.drag(start, end, device_id, duration=_SWIPE_DURATION_MS)


def _do_open_app(package_name: str, device_id: str) -> bool:
    if not package_name.strip():
        _logger.error("OPEN_APP requires a non-empty package name")
        return False
    _logger.info("Opening package: %s", package_name)
    # monkey -p <package> launches the app's LAUNCHER activity without
    # needing an explicit activity name.
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


def _map_to_adb(
    output: ActionOutput,
    elements: List[ParsedElement],
    img_width: int,
    img_height: int,
    device_id: str,
) -> bool:
    """Route an ActionOutput to the corresponding ADB call."""
    action = output.action_type
    pos = output.position or []
    value = output.value or ""

    if action == PhoneAction.TAP:
        return _do_tap(output.element_id, elements, img_width, img_height, device_id)

    if action == PhoneAction.INPUT:
        return _do_input(
            output.element_id, value, elements, img_width, img_height, device_id
        )

    if action == PhoneAction.LONG_PRESS:
        return _do_long_press(
            output.element_id, elements, img_width, img_height, device_id
        )

    if action == PhoneAction.SWIPE:
        return _do_swipe(pos, img_width, img_height, device_id)

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


def execute(
    action_text: str,
    image: Image.Image,  # enhanced annotated PIL Image from ground()
    device_id: str,
    elements: List[ParsedElement],  # OmniParserResult.interactable from ground()
    screen_info: str,  # set-of-mark text from ground()
) -> bool:
    """
    Execute a natural language action on the device.

    Composes the set-of-mark screen_info into the MLLM user message alongside
    the annotated screenshot, receives a structured ActionOutput with an
    element_id (for element-based actions) or position (for SWIPE), resolves
    element_id to pixel coordinates via the OmniParser element list, then
    dispatches the ADB command.

    Args:
        action_text:  Natural language description (e.g. "tap the Login button").
        image:        Enhanced annotated PIL Image returned by ground().
        device_id:    Android device ID or emulator serial (e.g. "emulator-5554").
        elements:     Interactable elements from OmniParserResult, used to
                      resolve element_id → screen coordinates.
        screen_info:  Set-of-mark text from ground() injected into the MLLM
                      user message as visual context.

    Returns:
        True if the action executed successfully, False otherwise.
    """
    _logger.info("Executing: %.120s", action_text)

    # Composite screen_info and action into the user message so the MLLM
    # sees both the element list and the instruction in one turn.
    user_message = (
        "Interactable elements detected on screen (idx-based):\n"
        f"{screen_info}\n\n"
        "Each line is formatted as: ID: <idx>, <Type>: <content>\n"
        "Use the idx as element_id when the action targets a specific element.\n\n"
        f"Action to perform:\n{action_text}"
    )

    mllm = _ExecutorMllm()

    try:
        output = mllm.complete(user_message=user_message, image=image)
    except MllmOutputError as e:
        _logger.error("MLLM output invalid: %s", e)
        return False
    except litellm.APIError as e:
        _logger.error("MLLM API error: %s", e)
        return False

    _logger.info(
        "Action decided — type: %s  element_id: %s  value: %s  position: %s",
        output.action_type,
        output.element_id,
        output.value,
        output.position,
    )

    return _map_to_adb(output, elements, image.width, image.height, device_id)
