"""
Planner Agent for MLLM Module

Specialized agent for planning decisions using AssistantAgent.
Decomposes user goals into sub-goals.
"""

import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from mllm.assistant_agent import AssistantAgent

@dataclass
class SubGoal:
    """Represents a decomposed sub-goal from the planner."""
    id: str
    description: str
    priority: int
    estimated_steps: int
    dependencies: List[str]
    success_criteria: str

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "description": self.description,
            "priority": self.priority,
            "estimated_steps": self.estimated_steps,
            "dependencies": self.dependencies,
            "success_criteria": self.success_criteria,
        }

class PlannerAgent:
    """
    Specialized agent for planning decisions using AssistantAgent.
    Decomposes user goals into sub-goals/milestones.
    """

    def __init__(self, assistant_agent: AssistantAgent):
        """
        Initialize the PlannerAgent.

        Args:
            assistant_agent: AssistantAgent instance for API calls
        """
        self._assistant_agent = assistant_agent
        self._logger = logging.getLogger(self.__class__.__name__)

    def plan_goal(
        self,
        goal: str,
        context: Dict,
        constraints: List[str],
        image_base64: Optional[str] = None
    ) -> List[SubGoal]:
        """
        Decompose a user goal into sub-goals.

        Args:
            goal: The user's goal/task description
            context: Context including history, past interactions
            constraints: List of constraints for planning
            image_base64: Optional base64 encoded image with highlighted UI elements

        Returns:
            List of SubGoal objects representing the decomposed plan
        """
        self._logger.info(f"Planning goal: {goal}")

        # Create the planning prompt
        prompt = self._create_planning_prompt(goal, context, constraints)
        self._logger.debug(f"Generated planning prompt: {prompt[:200]}...")

        # Query the AssistantAgent with optional image
        response = self._assistant_agent.query(prompt, image_bytes=self._base64_to_bytes(image_base64) if image_base64 else None)
        self._logger.debug(f"Received response: {response[:200]}...")

        # Parse the response into sub-goals
        subgoals = self._parse_plan_response(response)
        self._logger.info(f"Decomposed into {len(subgoals)} sub-goals")

        return subgoals

    def plan_goal_with_refinement(self, goal: str, context: Dict, constraints: List[str], image_base64: Optional[str], refinement_query: str) -> List[SubGoal]:
        """
        Decompose a user goal into sub-goals and refine the plan based on a query.

        Args:
            goal: The user's goal/task description
            context: Context including history, past interactions
            constraints: List of constraints for planning
            image_base64: Optional base64 encoded image with highlighted UI elements
            refinement_query: Additional query to refine the plan

        Returns:
            List of refined SubGoal objects
        """
        self._logger.info(f"Planning and refining goal: {goal}")

        # Step 1: Generate raw plan
        raw_prompt = self._create_planning_prompt(goal, context, constraints)
        self._logger.debug(f"Generated raw planning prompt: {raw_prompt[:200]}...")

        raw_response = self._assistant_agent.query(raw_prompt , image_bytes=self._base64_to_bytes(image_base64) if image_base64 else None)
        self._logger.debug(f"Received raw response: {raw_response[:200]}...")

        raw_subgoals = self._parse_plan_response(raw_response)
        self._logger.info(f"Generated raw plan with {len(raw_subgoals)} sub-goals")

        # Step 2: Refine the raw plan
        refined_prompt = self._create_refinement_prompt(raw_subgoals, refinement_query)
        self._logger.debug(f"Generated refinement prompt: {refined_prompt[:200]}...")

        refined_response = self._assistant_agent.query(refined_prompt, image_bytes=self._base64_to_bytes(image_base64) if image_base64 else None)
        self._logger.debug(f"Received refined response: {refined_response[:200]}...")

        refined_subgoals = self._parse_plan_response(refined_response)
        self._logger.info(f"Refined plan with {len(refined_subgoals)} sub-goals")

        return refined_subgoals

    def _create_planning_prompt(self, goal: str, context: Dict, constraints: List[str]) -> str:
        """
        Create a structured prompt for goal decomposition.

        Args:
            goal: The user's goal
            context: Context dictionary with history/interactions
            constraints: List of constraint strings

        Returns:
            Formatted prompt string for the LLM
        """
        context_str = "\n".join([f"- {k}: {v}" for k, v in context.items()]) if context else "None"
        constraints_str = "\n".join([f"- {c}" for c in constraints]) if constraints else "None"

        prompt = f"""
You are a task planner for a mobile GUI automation agent.

## User Goal
{goal}

## Context
{context_str}

## Constraints
{constraints_str}

## Instructions
Decompose the user goal into 3-5 sequential sub-goals (milestones).
Each sub-goal should be a concrete, verifiable step toward the main goal.

## Output Format
Respond with a JSON array of sub-goals. Each sub-goal must have:
- "id": unique identifier (e.g., "sg_1", "sg_2")
- "description": clear description of what to accomplish
- "priority": execution order (1 = first)
- "estimated_steps": estimated number of GUI actions needed
- "dependencies": list of sub-goal IDs that must complete first (empty for first sub-goal)
- "success_criteria": how to verify this sub-goal is complete

Example format:
[
  {{
    "id": "sg_1",
    "description": "Open the settings app",
    "priority": 1,
    "estimated_steps": 2,
    "dependencies": [],
    "success_criteria": "Settings app is open and visible"
  }}
]

Respond ONLY with the JSON array, no additional text.
"""
        return prompt

    def _create_refinement_prompt(self, raw_subgoals: List[SubGoal], refinement_query: str) -> str:
        """
        Create a structured prompt for refining a raw plan.

        Args:
            raw_subgoals: List of raw SubGoal objects
            refinement_query: Query to refine the plan

        Returns:
            Formatted prompt string for the LLM
        """
        # Format each sub-goal as a milestone
        raw_plan_lines = []
        for sg in raw_subgoals:
            raw_plan_lines.append(f"Milestone {sg.priority}: {sg.description}")
            raw_plan_lines.append(f"  - Estimated Steps: {sg.estimated_steps}")
            raw_plan_lines.append(f"  - Success Criteria: {sg.success_criteria}")
            if sg.dependencies:
                raw_plan_lines.append(f"  - Dependencies: {', '.join(sg.dependencies)}")
            raw_plan_lines.append("")  # Empty line for readability
        
        raw_plan_str = "\n".join(raw_plan_lines)

        prompt = f"""
You are a task planner for a mobile GUI automation agent.

## Raw Plan
{raw_plan_str}

## Refinement Query
{refinement_query}

## Instructions
Refine the raw plan based on the query. Update the sub-goals and subtasks as needed to align with the query.

## Output Format
Respond with a JSON array of refined sub-goals. Each sub-goal must have:
- "id": unique identifier (e.g., "sg_1", "sg_2")
- "description": clear description of what to accomplish
- "priority": execution order (1 = first)
- "estimated_steps": estimated number of GUI actions needed
- "dependencies": list of sub-goal IDs that must complete first (empty for first sub-goal)
- "success_criteria": how to verify this sub-goal is complete

Example format:
[
  {{"id": "sg_1", "description": "Open the settings app", "priority": 1, "estimated_steps": 2, "dependencies": [], "success_criteria": "Settings app is open and visible"}}
]

Respond ONLY with the JSON array, no additional text.
"""
        return prompt

    def _parse_plan_response(self, response: str) -> List[SubGoal]:
        """
        Parse the LLM response into SubGoal objects.

        Args:
            response: Raw response string from the LLM

        Returns:
            List of SubGoal objects
        """
        import json

        try:
            data = json.loads(response)
            subgoals = []

            for item in data:
                subgoal = SubGoal(
                    id=item["id"],
                    description=item["description"],
                    priority=item["priority"],
                    estimated_steps=item["estimated_steps"],
                    dependencies=item.get("dependencies", []),
                    success_criteria=item["success_criteria"],
                )
                subgoals.append(subgoal)

            return subgoals

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            self._logger.error(f"Failed to parse response: {response}")
            raise ValueError("Invalid response format") from e

    @staticmethod
    def _base64_to_bytes(base64_str: Optional[str]) -> Optional[bytes]:
        """
        Convert base64 string to bytes.

        Args:
            base64_str: Base64 encoded string

        Returns:
            Bytes object or None if input is None
        """
        if not base64_str:
            return None
        import base64
        return base64.b64decode(base64_str)
