# ADB Module - Implementation Instructions

## Overview
The ADB module provides an interface to Android Debug Bridge for device control.
Allows executing actions on Android devices via adb commands.

## Components

### 1. adb_interface.py
Interface for ADB device interaction.

**Key Responsibilities:**
- Detect and connect to Android devices
- Execute adb commands (tap, text input, swipe, etc.)
- Capture screenshots
- Handle multiple devices
- Error handling and connection validation

**TODO - Implementation:**
- [ ] Define ADBInterface class
- [ ] Implement __init__ with device_id selection
- [ ] Implement execute_click(x, y) method
- [ ] Implement execute_type(text) method
- [ ] Implement execute_scroll(direction, steps) method
- [ ] Implement execute_keyevent(keycode) method
- [ ] Implement screenshot_capture() method
- [ ] Implement connected_devices() method
- [ ] Add error handling and validation
- [ ] Add logging
- [ ] Add command timeout handling

## ADB Command Reference

**Core Actions:**
```
# Click at coordinates
adb shell input tap x y

# Type text
adb shell input text "hello"

# Swipe (scroll)
adb shell input swipe x1 y1 x2 y2 duration

# Key press
adb shell input keyevent KEYCODE_BACK

# Screenshot
adb shell screencap -p /sdcard/screen.png
adb pull /sdcard/screen.png output.png
```

## Integration Points

- **Configuration**: Gets device_id from config
- **Executor**: Receives action execution requests
- **Environment**: Reads adb executable path from environment
