"""
Skill Manager for Execution Module

Manages the action space and available skills for the MLLM.
Provides atomic actions (click, type, scroll) and optional composite actions.

Reference: https://arxiv.org/abs/2509.17328, https://arxiv.org/abs/2411.17465

TODO - Implementation Instructions:
    1. Define Action dataclass with fields:
        - action_type: str (CLICK, TYPE, SCROLL, WAIT, BACK)
        - parameters: dict (x, y, text, direction)
        - description: str
    2. Define ActionSpace as collection of available actions
    3. Implement SkillManager class:
        - Constructor takes config
        - Maintains atomic and composite actions
    4. Implement get_available_actions() method:
        - Return all available actions for MLLM
        - Include descriptions
    5. Implement filter_actions_by_state(gui_elements) method:
        - Given detected GUI elements from vision
        - Return only applicable actions for those elements
        - E.g., only CLICK if clickable elements present
    6. Implement get_action_description(action_type) method:
        - Return natural language description for MLLM prompts
    7. Add validation for action parameters
    8. Add logging
"""

from typing import List, Dict, Any


class Action:
    """
    TODO - Implementation Instructions:
        1. Define __init__ with action_type, parameters, description
        2. Implement validate() method
        3. Implement to_dict() for serialization
        4. Implement __repr__ for logging
    """
    pass


class SkillManager:
    """
    TODO - Implementation Instructions:
        1. Define __init__(self, config):
            - Store atomic action types (CLICK, TYPE, SCROLL, WAIT, BACK)
            - Initialize action descriptions
            - Set up logger
        2. Implement get_available_actions() -> List[Action]:
            - Return complete action space
            - Include minimal examples
        3. Implement filter_actions_by_state(gui_elements: List) -> List[Action]:
            - Given GUI elements detected by vision
            - Filter to applicable actions
            - E.g., CLICK if clickable elements
            - E.g., TYPE if input fields present
        4. Implement get_action_description(action_type: str) -> str:
            - Return human-readable description
            - Include parameter requirements
    """
    pass


# Action Type Constants
ACTION_TYPE_CLICK = "CLICK"
ACTION_TYPE_TYPE = "TYPE"
ACTION_TYPE_SCROLL = "SCROLL"
ACTION_TYPE_WAIT = "WAIT"
ACTION_TYPE_BACK = "BACK"

ATOMIC_ACTIONS = [
    ACTION_TYPE_CLICK,
    ACTION_TYPE_TYPE,
    ACTION_TYPE_SCROLL,
    ACTION_TYPE_WAIT,
    ACTION_TYPE_BACK
]

# Action descriptions for MLLM prompts
ACTION_DESCRIPTIONS = {
    ACTION_TYPE_CLICK: "Click at coordinates (x, y) on the screen",
    ACTION_TYPE_TYPE: "Type text into the currently focused field",
    ACTION_TYPE_SCROLL: "Scroll in direction (up/down/left/right)",
    ACTION_TYPE_WAIT: "Wait for specified seconds",
    ACTION_TYPE_BACK: "Press back button"
}
