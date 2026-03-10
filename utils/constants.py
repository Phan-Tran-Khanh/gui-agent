"""
Constants for GUI Agent

Centralized constants used across the application.

TODO - Implementation Instructions:
    1. Define action type constants (should match skill_manager)
    2. Define status constants
    3. Define config defaults
    4. Define timeout values
    5. Add any other shared constants
"""

# Action types (match skill_manager.py)
ACTION_CLICK = "CLICK"
ACTION_TYPE = "TYPE"
ACTION_SCROLL = "SCROLL"
ACTION_WAIT = "WAIT"
ACTION_BACK = "BACK"

# Execution statuses
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_STALLED = "stalled"

# Reflection actions
REFLECTION_ACTION_CONTINUE = "continue"
REFLECTION_ACTION_REPLAN = "replan"
REFLECTION_ACTION_EXPAND = "expand"
REFLECTION_ACTION_FAIL = "fail"

# Default configurations
DEFAULT_MAX_STEPS = 50
DEFAULT_MAX_REPLAN_ATTEMPTS = 3
DEFAULT_STALL_THRESHOLD = 0.95  # 95% visual similarity = stalled
DEFAULT_SCREENSHOT_TIMEOUT = 10  # seconds
DEFAULT_ACTION_TIMEOUT = 30  # seconds

# Vision preprocessing keys
ENABLE_HIGHLIGHTING = "enable_highlighting"
ENABLE_MASKING = "enable_masking"
ENABLE_CROPPING = "enable_cropping"
