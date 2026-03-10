"""
ADB Interface for ADB Module

Interface to Android Debug Bridge for device interaction.
Executes actions on Android devices via adb commands.

TODO - Implementation Instructions:
    1. Define ADBInterface class:
        - Constructor takes device_id or auto-detect
        - Verify device is connected
        - Initialize logger
    2. Implement __init__(self, device_id: str = None, adb_path: str = "adb"):
        - Store adb_path (from config or env)
        - Set device_id (from config or auto-detect)
        - Verify connection
        - Initialize command timeout
    3. Implement execute_click(x: int, y: int) -> bool:
        - Run: adb -s <device_id> shell input tap x y
        - Return success status
    4. Implement execute_type(text: str) -> bool:
        - Escape special characters in text
        - Run: adb shell input text "<text>"
        - Return success status
    5. Implement execute_scroll(direction: str, steps: int = 5) -> bool:
        - Calculate swipe coordinates based on direction (up, down, left, right)
        - Run: adb shell input swipe x1 y1 x2 y2 300
        - Return success status
    6. Implement execute_keyevent(keycode: str) -> bool:
        - Run: adb shell input keyevent <KEYCODE>
        - Return success status
    7. Implement screenshot() -> Optional[bytes]:
        - Run: adb shell screencap -p /sdcard/temp_screen.png
        - adb pull /sdcard/temp_screen.png
        - Return image bytes or None
    8. Implement list_connected_devices() -> List[str]:
        - Run: adb devices
        - Parse output
        - Return list of device IDs
    9. Implement verify_device_connected() -> bool:
        - Check if device_id is in list_connected_devices()
        - Return boolean
    10. Helper: _run_adb_command(cmd_args) -> (success, output):
        - Run adb command with timeout
        - Handle errors
        - Return (bool, str)
    11. Add logging for all commands
    12. Add error handling
"""

from typing import Optional, List, Tuple
import subprocess


class ADBInterface:
    """
    TODO - Implementation Instructions:
        1. Define __init__(self, device_id: Optional[str] = None, config=None):
            - Get adb_path from env or config
            - Get or detect device_id
            - Verify connection
            - Set up logger
            - Set command timeout (e.g., 30s)
        2. Implement execute_click(x: int, y: int) -> bool:
            - Validate coordinates
            - Run tap command
            - Return success status
        3. Implement execute_type(text: str) -> bool:
            - Escape special chars (quotes, spaces, etc.)
            - Run input text command
            - Return success
        4. Implement execute_scroll(direction: str, steps: int) -> bool:
            - Calculate swipe based on direction and steps
            - Run swipe command
            - Return success
        5. Implement execute_keyevent(keycode: str) -> bool:
            - Run input keyevent command
            - Return success
        6. Implement screenshot() -> Optional[bytes]:
            - Capture screenshot
            - Pull from device
            - Return as bytes
        7. Implement list_connected_devices() -> List[str]
        8. Implement verify_device_connected() -> bool
        9. Implement _run_adb_command(cmd_args) -> Tuple[bool, str]:
            - Run command with timeout
            - Handle exceptions
            - Return (success, output_or_error)
    """
    pass


# ADB Key Codes
KEYCODE_BACK = "4"
KEYCODE_HOME = "3"
KEYCODE_ENTER = "66"
KEYCODE_DEL = "67"

# Scroll directions
SCROLL_UP = "up"
SCROLL_DOWN = "down"
SCROLL_LEFT = "left"
SCROLL_RIGHT = "right"
