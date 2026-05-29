"""
ADB Interface for Action Execution

Pure function-based interface to Android Debug Bridge for device interaction.
Implements the ActionSpace specification with stateless ADB command execution.

Reference: ActionSpace.md
    - Each action is a pure function
    - Direct mapping to ADB shell commands
    - Coordinate system: (0,0) at top-left, X increases right, Y increases down
    - All actions are atomic (single adb command or sequence)

Core Actions:
    - click(target) → adb shell input tap
    - long_press(target) → adb shell input swipe (same start/end)
    - swipe(start, direction, distance) → adb shell input swipe (computed end)
    - input_text(text) → adb shell input text (escaped)
    - drag(start, end) → adb shell input swipe (with duration)
    - press_enter() → adb shell input keyevent 66
    - navigate_back() → adb shell input keyevent 4
    - navigate_home() → adb shell input keyevent 3
    - navigate_recent() → adb shell input keyevent 187
    - wait_action() → sleep 2 seconds

Dispatcher:
    - execute_action(action_dict, device_id) → routes to appropriate function
    - validate_action(action_dict) → validates action specification

Utility:
    - run_adb_command(cmd_args, device_id, timeout) → executes adb command
    - list_connected_devices() → returns list of device IDs
"""
import logging
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# Initialize logger
logger = logging.getLogger(__name__)

# ADB Configuration

# Get the directory where adb.py is located
ADB_DIR = os.path.dirname(os.path.abspath(__file__))
_ADB_BINARY = "adb.exe" if sys.platform == "win32" else "adb"
DEFAULT_ADB_PATH = os.path.join(ADB_DIR, "platform-tools", _ADB_BINARY)
DEFAULT_COMMAND_TIMEOUT = 30  # seconds
DEFAULT_LONG_PRESS_DURATION = 1000  # milliseconds

# Key Codes (from ActionSpace.md)
KEYCODE_BACK = "4"
KEYCODE_HOME = "3"
KEYCODE_RECENT = "187"
KEYCODE_ENTER = "66"
KEYCODE_DEL = "67"

# Swipe Distances (from ActionSpace.md)
SWIPE_DISTANCE_SHORT = 300
SWIPE_DISTANCE_MEDIUM = 600
SWIPE_DISTANCE_LONG = 1000

# Swipe Directions
SWIPE_UP = "up"
SWIPE_DOWN = "down"
SWIPE_LEFT = "left"
SWIPE_RIGHT = "right"


def run_adb_command(
    cmd_args: List[str],
    device_id: Optional[str] = None,
    adb_path: str = DEFAULT_ADB_PATH,
    timeout: int = DEFAULT_COMMAND_TIMEOUT
) -> Tuple[bool, str]:
    """
    Execute an ADB command and return success status and output.

    Helper function to manage ADB command execution with error handling.

    Args:
        cmd_args (List[str]): Command arguments (without 'adb' prefix)
                            Example: ["shell", "input", "tap", "540", "920"]
        device_id (str, optional): Device ID/serial number
                                 If provided, includes "-s device_id" in command
        adb_path (str): Path to adb executable
                       Default: "adb" (assumes in PATH)
        timeout (int): Command timeout in seconds
                      Default: 30 seconds

    Returns:
        Tuple[bool, str]: (success, output_or_error_message)
        - success: True if command executed, False on error
        - output: Command stdout/stderr

    Example:
        ```python
        success, output = run_adb_command(
            ["shell", "input", "tap", "540", "920"],
            device_id="emulator-5554"
        )
        ```
    """
    try:
        # Build full command
        full_cmd = [adb_path]

        # Add device specification if provided
        if device_id:
            full_cmd.extend(["-s", device_id])

        # Add command arguments
        full_cmd.extend(cmd_args)

        logger.debug("Executing ADB: %s", " ".join(full_cmd))

        # Execute command
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )

        # Check result
        if result.returncode == 0:
            logger.debug("ADB command succeeded")
            return True, result.stdout.strip()
        else:
            error_msg = result.stderr.strip() or "Command failed"
            logger.warning("ADB command failed: %s", error_msg)
            return False, error_msg

    except subprocess.TimeoutExpired:
        error_msg = f"ADB command timeout (>{timeout}s)"
        logger.error(error_msg)
        return False, error_msg

    except FileNotFoundError:
        error_msg = f"ADB executable not found at: {adb_path}"
        logger.error(error_msg)
        return False, error_msg

    except OSError as e:
        error_msg = f"ADB command error: {e}"
        logger.error(error_msg)
        return False, error_msg


def list_connected_devices(adb_path: str = DEFAULT_ADB_PATH) -> List[str]:
    """
    Get list of connected ADB devices.

    Args:
        adb_path (str): Path to adb executable

    Returns:
        List[str]: List of device IDs (empty if none connected)

    Example:
        ```python
        devices = list_connected_devices()
        # Returns: ['emulator-5554', 'FA7AX0A01234']
        ```
    """
    success, output = run_adb_command(["devices"], adb_path=adb_path)

    if not success:
        logger.warning("Failed to retrieve device list")
        return []

    # Parse output: "List of attached devices\ndevice1\ndevice2\n..."
    devices = []
    for line in output.split('\n'):
        line = line.strip()
        # Skip header and empty lines
        if line and line != "List of attached devices":
            # Extract device ID (before any status indicator)
            device_id = line.split('\t')[0].strip()
            if device_id:
                devices.append(device_id)

    logger.debug("Found %d connected device(s)", len(devices))
    return devices


def verify_device_connected(
    device_id: str,
    adb_path: str = DEFAULT_ADB_PATH
) -> bool:
    """
    Verify that a device is connected.

    Args:
        device_id (str): Device ID/serial to verify
        adb_path (str): Path to adb executable

    Returns:
        bool: True if device is connected, False otherwise
    """
    devices = list_connected_devices(adb_path)
    is_connected = device_id in devices

    if is_connected:
        logger.debug("Device %s is connected", device_id)
    else:
        logger.warning("Device %s is NOT connected", device_id)

    return is_connected


# ============================================================================
# ACTION IMPLEMENTATIONS (Following ActionSpace.md)
# ============================================================================

def click(
    target: Tuple[int, int],
    device_id: str,
    adb_path: str = DEFAULT_ADB_PATH
) -> bool:
    """
    Execute click action (single tap).

    Simulates a single tap at the specified screen coordinate.

    From ActionSpace.md:
        Receives target coordinate (x, y) and executes:
        adb shell input tap x y

    Args:
        target (Tuple[int, int]): Screen coordinates as (x, y)
        device_id (str): Target device ID
        adb_path (str): Path to adb executable

    Returns:
        bool: True if command executed successfully

    Example:
        ```python
        success = click((540, 920), device_id="emulator-5554")
        ```
    """
    x, y = target

    if not isinstance(x, int) or not isinstance(y, int):
        logger.error("Invalid click coordinates: (%s, %s)", x, y)
        return False

    logger.debug("Click action: (%s, %s)", x, y)

    success, _ = run_adb_command(
        ["shell", "input", "tap", str(x), str(y)],
        device_id=device_id,
        adb_path=adb_path
    )

    return success


def long_press(
    target: Tuple[int, int],
    device_id: str,
    duration: int = DEFAULT_LONG_PRESS_DURATION,
    adb_path: str = DEFAULT_ADB_PATH
) -> bool:
    """
    Execute long press action (press and hold).

    Simulates pressing and holding at a location using swipe with identical
    start and end points (ADB limitation - no native long_press).

    From ActionSpace.md:
        Receives target (x, y) and duration.
        Executes: adb shell input swipe x y x y duration

    Args:
        target (Tuple[int, int]): Screen coordinates as (x, y)
        device_id (str): Target device ID
        duration (int): Press duration in milliseconds
                       Default: 1000ms
        adb_path (str): Path to adb executable

    Returns:
        bool: True if command executed successfully

    Example:
        ```python
        success = long_press((540, 920), device_id="emulator-5554", duration=1000)
        ```
    """
    x, y = target

    if not isinstance(x, int) or not isinstance(y, int):
        logger.error("Invalid long_press coordinates: (%s, %s)", x, y)
        return False

    if not isinstance(duration, int) or duration <= 0:
        logger.error("Invalid long_press duration: %s", duration)
        return False

    logger.debug("Long press action: (%s, %s) duration=%sms", x, y, duration)

    # Use swipe with identical start/end (ADB limitation)
    success, _ = run_adb_command(
        ["shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration)],
        device_id=device_id,
        adb_path=adb_path
    )

    return success


def swipe(
    start: Tuple[int, int],
    direction: str,
    distance: str,
    device_id: str,
    adb_path: str = DEFAULT_ADB_PATH
) -> bool:
    """
    Execute swipe action (viewport movement).

    Changes the viewport by performing a swipe gesture in the specified
    direction for the specified distance.

    From ActionSpace.md:
        Step 1: Convert distance tag to pixels
        Step 2: Compute end coordinate based on direction
        Step 3: Execute swipe command

    Args:
        start (Tuple[int, int]): Starting coordinates as (x, y)
        direction (str): Swipe direction: "up", "down", "left", "right"
        distance (str): Distance category: "short", "medium", "long"
                       Maps to: 300, 600, 1000 pixels
        device_id (str): Target device ID
        adb_path (str): Path to adb executable

    Returns:
        bool: True if command executed successfully

    Example:
        ```python
        success = swipe((540, 900), direction="up", distance="medium", device_id="emulator-5554")
        ```
    """
    x, y = start

    # Validate inputs
    if not isinstance(x, int) or not isinstance(y, int):
        logger.error("Invalid swipe start coordinates: (%s, %s)", x, y)
        return False

    if direction not in [SWIPE_UP, SWIPE_DOWN, SWIPE_LEFT, SWIPE_RIGHT]:
        logger.error("Invalid swipe direction: %s", direction)
        return False

    # Map distance to pixels
    distance_map = {
        "short": SWIPE_DISTANCE_SHORT,
        "medium": SWIPE_DISTANCE_MEDIUM,
        "long": SWIPE_DISTANCE_LONG
    }

    if distance not in distance_map:
        logger.error("Invalid swipe distance: %s", distance)
        return False

    d = distance_map[distance]

    # Calculate end coordinates based on direction
    if direction == SWIPE_UP:
        x2, y2 = x, y - d
    elif direction == SWIPE_DOWN:
        x2, y2 = x, y + d
    elif direction == SWIPE_LEFT:
        x2, y2 = x - d, y
    else:  # SWIPE_RIGHT
        x2, y2 = x + d, y

    logger.debug("Swipe action: (%s, %s) -> (%s, %s) (%s, %s)", x, y, x2, y2, direction, distance)

    success, _ = run_adb_command(
        ["shell", "input", "swipe", str(x), str(y), str(x2), str(y2)],
        device_id=device_id,
        adb_path=adb_path
    )

    return success


def input_text(
    text: str,
    device_id: str,
    adb_path: str = DEFAULT_ADB_PATH
) -> bool:
    """
    Execute input text action (type text).

    Types text into the currently focused input field.
    Spaces and special characters are escaped for ADB compatibility.

    From ActionSpace.md:
        Step 1: Escape spaces in text
        Step 2: Execute: adb shell input text "text"

    Args:
        text (str): Text to type
        device_id (str): Target device ID
        adb_path (str): Path to adb executable

    Returns:
        bool: True if command executed successfully

    Example:
        ```python
        success = input_text("hello world", device_id="emulator-5554")
        ```
    """
    if not isinstance(text, str):
        logger.error("Invalid input_text type: %s", type(text))
        return False

    # Escape spaces and special characters for ADB
    # ADB requires spaces to be escaped or quoted
    escaped_text = text.replace(" ", "%s")

    logger.debug("Input text action: '%s'", text)

    success, _ = run_adb_command(
        ["shell", "input", "text", escaped_text],
        device_id=device_id,
        adb_path=adb_path
    )

    return success


def drag(
    start: Tuple[int, int],
    end: Tuple[int, int],
    device_id: str,
    duration: int = 500,
    adb_path: str = DEFAULT_ADB_PATH
) -> bool:
    """
    Execute drag action (object displacement).

    Simulates dragging an object from one position to another.

    From ActionSpace.md:
        Step 1: Receive start and end coordinates
        Step 2: Execute swipe with specified duration

    Args:
        start (Tuple[int, int]): Starting coordinates as (x1, y1)
        end (Tuple[int, int]): Ending coordinates as (x2, y2)
        device_id (str): Target device ID
        duration (int): Drag duration in milliseconds
                       Default: 500ms
        adb_path (str): Path to adb executable

    Returns:
        bool: True if command executed successfully

    Example:
        ```python
        success = drag((100, 100), (500, 500), device_id="emulator-5554")
        ```
    """
    x1, y1 = start
    x2, y2 = end

    if not all(isinstance(v, int) for v in [x1, y1, x2, y2]):
        logger.error("Invalid drag coordinates: (%s, %s) -> (%s, %s)", x1, y1, x2, y2)
        return False

    if not isinstance(duration, int) or duration <= 0:
        logger.error("Invalid drag duration: %s", duration)
        return False

    logger.debug("Drag action: (%s, %s) -> (%s, %s) duration=%sms", x1, y1, x2, y2, duration)

    success, _ = run_adb_command(
        ["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)],
        device_id=device_id,
        adb_path=adb_path
    )

    return success


def press_enter(
    device_id: str,
    adb_path: str = DEFAULT_ADB_PATH
) -> bool:
    """
    Execute enter key press action.

    Simulates pressing the Enter key.

    From ActionSpace.md:
        Execution: adb shell input keyevent 66

    Args:
        device_id (str): Target device ID
        adb_path (str): Path to adb executable

    Returns:
        bool: True if command executed successfully
    """
    logger.debug("Press enter action")

    success, _ = run_adb_command(
        ["shell", "input", "keyevent", KEYCODE_ENTER],
        device_id=device_id,
        adb_path=adb_path
    )

    return success


def navigate_back(
    device_id: str,
    adb_path: str = DEFAULT_ADB_PATH
) -> bool:
    """
    Execute navigate back action.

    Returns to the previous screen (back button).

    From ActionSpace.md:
        Execution: adb shell input keyevent 4

    Args:
        device_id (str): Target device ID
        adb_path (str): Path to adb executable

    Returns:
        bool: True if command executed successfully
    """
    logger.debug("Navigate back action")

    success, _ = run_adb_command(
        ["shell", "input", "keyevent", KEYCODE_BACK],
        device_id=device_id,
        adb_path=adb_path
    )

    return success


def navigate_home(
    device_id: str,
    adb_path: str = DEFAULT_ADB_PATH
) -> bool:
    """
    Execute navigate home action.

    Returns to the Android home screen.

    From ActionSpace.md:
        Execution: adb shell input keyevent 3

    Args:
        device_id (str): Target device ID
        adb_path (str): Path to adb executable

    Returns:
        bool: True if command executed successfully
    """
    logger.debug("Navigate home action")

    success, _ = run_adb_command(
        ["shell", "input", "keyevent", KEYCODE_HOME],
        device_id=device_id,
        adb_path=adb_path
    )

    return success


def navigate_recent(
    device_id: str,
    adb_path: str = DEFAULT_ADB_PATH
) -> bool:
    """
    Execute navigate recent action.

    Opens the recent applications view.

    From ActionSpace.md:
        Execution: adb shell input keyevent 187

    Args:
        device_id (str): Target device ID
        adb_path (str): Path to adb executable

    Returns:
        bool: True if command executed successfully
    """
    logger.debug("Navigate recent apps action")

    success, _ = run_adb_command(
        ["shell", "input", "keyevent", KEYCODE_RECENT],
        device_id=device_id,
        adb_path=adb_path
    )

    return success


def wait_action(duration: int = 2) -> bool:
    """
    Execute wait action (pause execution).

    Pauses execution to allow interface updates or content loading.

    From ActionSpace.md:
        Execution: sleep(2 seconds)

    Args:
        duration (int): Wait duration in seconds
                       Default: 2 seconds

    Returns:
        bool: Always returns True (no device command needed)
    """
    if not isinstance(duration, int) or duration < 0:
        logger.error("Invalid wait duration: %s", duration)
        return False

    logger.debug("Wait action: %ss", duration)
    time.sleep(duration)

    return True


# ============================================================================
# ACTION VALIDATION AND DISPATCHER
# ============================================================================

def validate_action(action: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate action specification before execution.

    From ActionSpace.md:
        - Ensure "action_type" exists
        - For coordinate-based actions: ensure coordinates exist
        - For swipe: validate direction and distance

    Args:
        action (Dict): Action specification

    Returns:
        Tuple[bool, str]: (is_valid, error_message)

    Example:
        ```python
        valid, msg = validate_action({
            "action_type": "click",
            "target": [540, 920]
        })
        ```
    """
    if not isinstance(action, dict):
        return False, "Action must be a dictionary"

    if "action_type" not in action:
        return False, "Action must have 'action_type' field"

    action_type = action["action_type"]

    # Validate based on action type
    if action_type == "click":
        if "target" not in action:
            return False, "click action requires 'target' field"
        if not isinstance(action["target"], (list, tuple)) or len(action["target"]) != 2:
            return False, "click 'target' must be [x, y]"

    elif action_type == "long_press":
        if "target" not in action:
            return False, "long_press action requires 'target' field"
        if not isinstance(action["target"], (list, tuple)) or len(action["target"]) != 2:
            return False, "long_press 'target' must be [x, y]"

    elif action_type == "swipe":
        if "start" not in action:
            return False, "swipe action requires 'start' field"
        if "direction" not in action:
            return False, "swipe action requires 'direction' field"
        if "distance" not in action:
            return False, "swipe action requires 'distance' field"

        if action["direction"] not in [SWIPE_UP, SWIPE_DOWN, SWIPE_LEFT, SWIPE_RIGHT]:
            return False, f"Invalid swipe direction: {action['direction']}"

        if action["distance"] not in ["short", "medium", "long"]:
            return False, f"Invalid swipe distance: {action['distance']}"

    elif action_type == "input_text":
        if "text" not in action:
            return False, "input_text action requires 'text' field"
        if not isinstance(action["text"], str):
            return False, "input_text 'text' must be a string"

    elif action_type == "drag":
        if "start" not in action or "end" not in action:
            return False, "drag action requires 'start' and 'end' fields"
        if not isinstance(action["start"], (list, tuple)) or len(action["start"]) != 2:
            return False, "drag 'start' must be [x, y]"
        if not isinstance(action["end"], (list, tuple)) or len(action["end"]) != 2:
            return False, "drag 'end' must be [x, y]"

    elif action_type in ["enter", "navigate_back", "navigate_home", "navigate_recent", "wait"]:
        # These actions require no additional fields
        pass

    else:
        return False, f"Unknown action type: {action_type}"

    return True, ""


def execute_action(
    action: Dict[str, Any],
    device_id: str,
    adb_path: str = DEFAULT_ADB_PATH
) -> bool:
    """
    Execute an action by routing to the appropriate function.

    From ActionSpace.md - Action Dispatcher:
        Routes action JSON to the correct function based on action_type.

    Args:
        action (Dict): Action specification
        device_id (str): Target device ID
        adb_path (str): Path to adb executable

    Returns:
        bool: True if action executed successfully

    Example:
        ```python
        success = execute_action(
            {
                "action_type": "click",
                "target": [540, 920]
            },
            device_id="emulator-5554"
        )
        ```
    """
    # Validate action
    is_valid, error_msg = validate_action(action)
    if not is_valid:
        logger.error("Invalid action: %s", error_msg)
        return False

    action_type = action["action_type"]

    try:
        if action_type == "click":
            return click(tuple(action["target"]), device_id, adb_path)

        elif action_type == "long_press":
            return long_press(tuple(action["target"]), device_id, adb_path=adb_path)

        elif action_type == "swipe":
            return swipe(
                tuple(action["start"]),
                action["direction"],
                action["distance"],
                device_id,
                adb_path
            )

        elif action_type == "input_text":
            return input_text(action["text"], device_id, adb_path)

        elif action_type == "drag":
            return drag(
                tuple(action["start"]),
                tuple(action["end"]),
                device_id,
                adb_path=adb_path
            )

        elif action_type == "enter":
            return press_enter(device_id, adb_path)

        elif action_type == "navigate_back":
            return navigate_back(device_id, adb_path)

        elif action_type == "navigate_home":
            return navigate_home(device_id, adb_path)

        elif action_type == "navigate_recent":
            return navigate_recent(device_id, adb_path)

        elif action_type == "wait":
            return wait_action()

        else:
            logger.error("Unknown action type: %s", action_type)
            return False

    except (ValueError, KeyError, TypeError) as e:
        logger.error("Error executing action: %s", e)
        return False
