"""
Planner Agent for MLLM Module

Specialized agent for planning decisions using Gemini.
Decomposes user goals into sub-goals.

TODO - Implementation Instructions:
    1. Define PlannerAgent class:
        - Constructor takes GeminiClient
        - Store configuration
    2. Implement plan_goal(goal: str, context: dict, constraints: List[str]) -> List[SubGoal]:
        - Create planning prompt using create_planning_prompt()
        - Call gemini_client.query_text()
        - Parse response using parse_plan_response()
        - Return list of SubGoal objects
    3. Implement create_planning_prompt(goal, context, constraints) -> str:
        - Format nicely for LLM
        - Include goal, context, constraints
        - Request JSON output
        - Request 3-5 sub-goals
    4. Implement parse_plan_response(response: str) -> List[SubGoal]:
        - Extract JSON from response
        - Create SubGoal objects
        - Validate structure
        - Return list
    5. Add error handling and logging
"""

from typing import List, Optional


class PlannerAgent:
    """
    TODO - Implementation Instructions:
        1. Define __init__(self, gemini_client, config=None):
            - Store gemini_client
            - Store config
            - Initialize logger
        2. Implement plan_goal(goal: str, context: dict, constraints: List) -> List:
            - Call create_planning_prompt()
            - Call gemini_client.query_text()
            - Call parse_plan_response()
            - Return list of SubGoal
        3. Implement create_planning_prompt() -> str:
            - Include goal clearly
            - Include context (past interactions, history)
            - Include constraints (app category, instruction category)
            - Request JSON format with specific fields
            - Request confidence for each step
    """
    pass


def create_planning_prompt(goal: str, context: dict, constraints: List[str]) -> str:
    """
    TODO - Implementation Instructions:
        1. Create structured prompt for goal decomposition
        2. Include user goal, context, constraints
        3. Request JSON output
        4. Specify expected format
        5. Return formatted prompt string
    """
    pass


def parse_plan_response(response: str) -> List:
    """
    TODO - Implementation Instructions:
        1. Extract JSON from response
        2. Parse sub-goals
        3. Create SubGoal objects
        4. Validate no duplicate goals
        5. Validate no circular dependencies
        6. Return list of SubGoal
    """
    pass
