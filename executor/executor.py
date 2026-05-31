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
        → ActionOutput(action_type=SWIPE, direction="down", distance="medium")

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
from config import Config
from executor.skills import ActionOutput, PhoneAction, get_skills_prompt
from grounder.models import ParsedElement
from mllm import BaseMllm, MllmOutputError

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MLLM system prompt — built once at import time, injected with all skills
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a precise mobile GUI automation agent.\n\n"
    "Every turn you receive an annotated screenshot with numbered bounding boxes "
    "marking each interactable element, a screen_info list that names every element "
    "by its ID, and a plain-English action instruction.\n\n"
    "Your sole responsibility is to translate that instruction into exactly one "
    "structured action with the correct parameters.\n\n"
    "Available actions:\n" + get_skills_prompt() + "\n\n"
    "How to fill each field:\n"
    "- action_type: always pick the single most appropriate action from the list.\n"
    "- element_id: for TAP, INPUT, and LONG_PRESS, identify the target element "
    "by reading its ID from the annotated screenshot or screen_info, then set "
    "element_id to that integer.\n"
    "- direction + distance: for SWIPE, set direction to one of "
    "'up', 'down', 'left', 'right' and distance to 'short', 'medium', or 'long'.\n"
    "- value: supply the text to type for INPUT, the Android package name for "
    "OPEN_APP (e.g. com.android.settings), or a brief completion message for ANSWER.\n"
    "- Leave every field that the chosen action does not require as null."
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


_VALID_DIRECTIONS = {"up", "down", "left", "right"}

# Fraction of screen dimension swept per distance category.
# Both start and end are placed symmetrically around the centre, so the
# gesture always stays within bounds regardless of screen size.
_SWIPE_FRACTION = {"short": 0.20, "medium": 0.40, "long": 0.60}
_SWIPE_DURATION_MS = 200  # ms — smooth enough for both scroll and fling


def _do_swipe(
    direction: Optional[str],
    distance: Optional[str],
    img_width: int,
    img_height: int,
    device_id: str,
) -> bool:
    if direction not in _VALID_DIRECTIONS:
        _logger.error(
            "SWIPE direction must be one of %s, got: %s", _VALID_DIRECTIONS, direction
        )
        return False

    # Convert the distance category to a fraction of the relevant screen
    # dimension (height for vertical swipes, width for horizontal).
    fraction = _SWIPE_FRACTION.get(distance or "medium", 0.40)

    # Anchor at the screen centre so the gesture is always reachable and
    # naturally positioned regardless of screen resolution.
    cx, cy = img_width // 2, img_height // 2

    # Place start and end symmetrically around the centre: each point is
    # half the total travel distance away, guaranteeing both stay on-screen.
    if direction == "up":
        # Finger moves upward → start below centre, end above.
        dy = int(img_height * fraction / 2)
        start, end = (cx, cy + dy), (cx, cy - dy)
    elif direction == "down":
        # Finger moves downward → start above centre, end below.
        dy = int(img_height * fraction / 2)
        start, end = (cx, cy - dy), (cx, cy + dy)
    elif direction == "left":
        # Finger moves leftward → start right of centre, end left.
        dx = int(img_width * fraction / 2)
        start, end = (cx + dx, cy), (cx - dx, cy)
    else:  # right
        # Finger moves rightward → start left of centre, end right.
        dx = int(img_width * fraction / 2)
        start, end = (cx - dx, cy), (cx + dx, cy)

    _logger.debug(
        "SWIPE %s/%s  %s -> %s  (screen %dx%d)",
        direction,
        distance,
        start,
        end,
        img_width,
        img_height,
    )
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
        return _do_swipe(
            output.direction, output.distance, img_width, img_height, device_id
        )

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
    element_id (for element-based actions) or direction/distance (for SWIPE), resolves
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

    if Config().mock_mode:
        # In mock mode skip the MLLM call. Tap the first available element so
        # the full _map_to_adb → ADB path is still exercised end-to-end.
        first = elements[0] if elements else None
        output = (
            ActionOutput(action_type=PhoneAction.TAP, element_id=first.idx)
            if first
            else ActionOutput(action_type=PhoneAction.WAIT)
        )
        _logger.info("[MOCK] Synthetic action: %s", output)
    else:
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
        "Action decided — type: %s  element_id: %s  value: %s  direction: %s  distance: %s",
        output.action_type,
        output.element_id,
        output.value,
        output.direction,
        output.distance,
    )

    return _map_to_adb(output, elements, image.width, image.height, device_id)
