"""
Task Planner for Planning Phase

Responsible for decomposing user goal into sub-goals/milestones:
- Accept user goal
- Retrieve context and constraints
- Decompose goal using MLLM (Gemini PlannerAgent)
- Generate prioritized sub-goal list

Reference: https://arxiv.org/abs/2312.13108

TODO - Implementation Instructions:
    1. Define Planner class with constructor taking config
    2. Integrate with ContextRetriever and ConstraintRetriever
    3. Integrate with PlannerAgent from MLLM module
    4. Implement plan(user_goal, app_category, instruction_category) method:
        - Retrieve context and constraints
        - Call PlannerAgent with goal and context
        - Parse response into sub-goals
        - Validate sub-goals
        - Return SubGoal list
    5. Implement decompose_goal_into_milestones() method:
        - Uses graph/DAG structure for dependencies
        - Generates milestone sequence
        - Estimates steps per milestone
    6. Implement prioritize_subgoals() method:
        - Order sub-goals by dependency
        - Assign confidence scores
        - Handle parallel vs sequential execution
    7. Add caching for identical goals
    8. Add comprehensive logging
    9. Implement error recovery for invalid decompositions
"""

from typing import List, Dict, Any, Optional


class SubGoal:
    """
    TODO - Implementation Instructions:
        1. Define __init__ with fields:
            - id: str (unique identifier)
            - description: str (natural language description)
            - priority: int (execution order)
            - estimated_steps: int (estimated actions needed)
            - dependencies: List[str] (prerequisite sub-goal ids)
            - success_criteria: str (how to verify completion)
        2. Implement __repr__ for debugging
        3. Add validation method to ensure valid structure
    """
    pass


class Planner:
    """
    TODO - Implementation Instructions:
        1. Define __init__(self, config):
            - Store config
            - Initialize ContextRetriever
            - Initialize ConstraintRetriever
            - Initialize PlannerAgent from MLLM
            - Set up logger
        2. Implement plan(user_goal: str, app_category: Optional[str], instruction_category: Optional[str]) -> List[SubGoal]:
            - Call retrieve_context_for_planning()
            - Call retrieve_constraints_for_planning()
            - Prompt PlannerAgent with goal, context, constraints
            - Parse MLLM response into SubGoal objects
            - Validate generated sub-goals
            - Call prioritize_subgoals()
            - Return sorted sub-goals
        3. Implement decompose_goal_into_milestones(goal: str) -> List[str]:
            - Break goal into logical milestones
            - Identify dependencies
            - Return ordered milestone list
        4. Implement prioritize_subgoals(subgoals: List[SubGoal]) -> List[SubGoal]:
            - Topologically sort by dependencies
            - Assign execution priority
            - Return ordered subgoals
        5. Implement validate_subgoals(subgoals: List[SubGoal]) -> bool:
            - Check no circular dependencies
            - Verify all subgoals are achievable
            - Return validation result
    """
    pass


def create_plan_prompt(goal: str, context: Dict, constraints: List[str]) -> str:
    """
    TODO - Implementation Instructions:
        1. Create structured prompt for PlannerAgent
        2. Include:
            - User goal clearly stated
            - Relevant context from history
            - Applicable constraints
            - Expected output format (JSON with sub-goals)
        3. Return formatted prompt string
    """
    pass


def parse_plan_response(response: str) -> List[SubGoal]:
    """
    TODO - Implementation Instructions:
        1. Parse MLLM response (likely JSON format)
        2. Extract sub-goals from response
        3. Create SubGoal objects
        4. Validate parsed structure
        5. Return SubGoal list
        6. Handle parsing errors gracefully
    """
    pass
