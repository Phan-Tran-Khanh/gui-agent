"""
Executor Agent for MLLM Module

Specialized agent for execution decisions using Gemini.
Decides next action given GUI state and sub-goal.
Note: This agent SUGGESTS actions; final coordinates come from Grounder.

TODO - Implementation Instructions:
    1. Define ExecutorAgent class:
        - Constructor takes GeminiClient
        - Store configuration
    2. Implement decide_action(visual_state: dict, subgoal: str, available_actions: List) -> dict:
        - Create execution prompt using create_execution_prompt()
        - Call gemini_client.query_with_image() (pass screenshot)
        - Parse response using parse_action_response()
        - Return action dict with type, reasoning
    3. Implement create_execution_prompt(visual_state, subgoal, available_actions) -> str:
        - Describe current GUI state
        - Describe available actions
        - Ask for next action reasoning
        - Request structured response
    4. Implement parse_action_response(response: str) -> dict:
        - Extract action type
        - Extract parameters
        - Extract reasoning
        - Return action dict
    5. Add error handling and logging
"""

from typing import List, Dict, Any, Optional


class ExecutorAgent:
    """
    TODO - Implementation Instructions:
        1. Define __init__(self, gemini_client, config=None):
            - Store gemini_client
            - Store config
            - Initialize logger
        2. Implement decide_action(visual_state: dict, subgoal: str, available_actions: List) -> dict:
            - Call create_execution_prompt()
            - Call gemini_client.query_with_image(prompt, screenshot)
            - Call parse_action_response()
            - Return action dict with keys: action_type, reasoning, parameters (if any)
        3. Implement create_execution_prompt(visual_state, subgoal, available_actions) -> str:
            - Describe current GUI state from visual_state
            - List available actions
            - Describe active sub-goal
            - Request: "What is the NEXT action to accomplish this sub-goal?"
            - Request JSON output
    """
    pass


def create_execution_prompt(visual_state: dict, subgoal: str, available_actions: List[str]) -> str:
    """
    TODO - Implementation Instructions:
        1. Create prompt for action decision
        2. Include visual state description (detected elements, text)
        3. Include available actions (CLICK, TYPE, SCROLL, BACK, WAIT)
        4. Include current sub-goal
        5. Request JSON response with action_type and reasoning
        6. Return formatted prompt string
    """
    pass


def parse_action_response(response: str) -> Dict:
    """
    TODO - Implementation Instructions:
        1. Extract JSON from response
        2. Get action_type field
        3. Get reasoning field
        4. Get parameters (if present)
        5. Validate action_type is valid (CLICK, TYPE, SCROLL, BACK, WAIT)
        6. Return dict with action_type, reasoning, parameters
    """
    pass
