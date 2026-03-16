"""
Planner Agent for MLLM Module

Specialized agent for planning decisions using AssistantAgent.
Decomposes user goals into milestones and subtasks.
"""

import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from mllm.assistant_agent import AssistantAgent
from mllm.enums import ExecutionStatus, ActionType


@dataclass
class SubTask:
    """Individual action within a milestone"""
    id: str                              # "m_1_1"
    description: str                     # "Tap 'Privacy' button"
    action_hint: ActionType              # ActionType.CLICK, ActionType.TYPE, etc.
    expected_ui_element: str             # "Privacy" - what element to look for
    alternative_ui_elements: List[str] = field(default_factory=list)  # ["Privacy Settings", "Privacy & Security"]
    
    # Execution state
    status: ExecutionStatus = ExecutionStatus.PENDING
    executed_element: Optional[str] = None  # What element was actually clicked
    error_message: Optional[str] = None


@dataclass
class Milestone:
    """Major phase of the task"""
    id: str                              # "m_1"
    description: str                     # "Open Privacy settings"
    priority: int                        # Execution order (1, 2, 3...)
    estimated_steps: int                 # Total steps in this milestone
    dependencies: List[str]              # Prerequisites (e.g., ["m_1"])
    success_criteria: str                # How to verify completion
    
    subtasks: List[SubTask]              # Actual subtasks from planning
    
    # Execution state
    status: ExecutionStatus = ExecutionStatus.PENDING
    current_subtask_index: int = 0       # Which subtask are we on?
    
    # Execution history
    execution_history: List[Dict] = field(default_factory=list)


@dataclass
class Plan:
    """Complete plan with all milestones"""
    milestones: List[Milestone]
    
    # Execution state
    status: ExecutionStatus = ExecutionStatus.PENDING
    current_milestone_index: int = 0     # Track which milestone we're on
    
    def get_current_milestone(self) -> Optional[Milestone]:
        """Get the currently active milestone"""
        if 0 <= self.current_milestone_index < len(self.milestones):
            return self.milestones[self.current_milestone_index]
        return None
    
    def get_next_subtask(self) -> Optional[SubTask]:
        """Get the next subtask to execute"""
        current_m = self.get_current_milestone()
        if not current_m:
            return None
        if current_m.current_subtask_index < len(current_m.subtasks):
            return current_m.subtasks[current_m.current_subtask_index]
        return None
    
    def advance_subtask(self):
        """Move to next subtask"""
        current_m = self.get_current_milestone()
        if current_m:
            current_m.current_subtask_index += 1
            if current_m.current_subtask_index >= len(current_m.subtasks):
                # Move to next milestone
                self.current_milestone_index += 1
                current_m.status = ExecutionStatus.COMPLETED
    
class PlannerAgent:
    """
    Specialized agent for planning decisions using AssistantAgent.
    Decomposes user goals into milestones and subtasks.
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
    ) -> Plan:
        """
        Decompose a user goal into milestones with subtasks.

        Args:
            goal: The user's goal/task description
            context: Context including history, past interactions
            constraints: List of constraints for planning
            image_base64: Optional base64 encoded image with highlighted UI elements

        Returns:
            Plan object containing milestones and subtasks
        """
        self._logger.info(f"Planning goal: {goal}")

        # Create the planning prompt
        prompt = self._create_planning_prompt(goal, context, constraints)

        # Query the AssistantAgent with optional image
        response = self._assistant_agent.query(prompt, image_bytes=self._base64_to_bytes(image_base64) if image_base64 else None)

        # Parse the response into Plan
        plan = self._parse_plan_response(response)
        self._logger.info(f"Generated plan with {len(plan.milestones)} milestones")

        return plan

    def _create_planning_prompt(self, goal: str, context: Dict, constraints: List[str]) -> str:
        """
        Create a structured prompt for goal decomposition with milestones and subtasks.

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
Decompose the user goal into 3-5 sequential MILESTONES (major phases).
For each milestone, break it down into 2-3 specific SUBTASKS (concrete GUI actions).

Think step-by-step:
1. What is the ultimate objective?
2. What are the major phases to achieve it?
3. For each phase, what specific GUI interactions are needed?
4. What UI elements need to be found and interacted with?
5. How can the user verify each subtask succeeded?

## Output Format
Respond with a JSON array of milestones. Each milestone must have:
- "id": unique identifier (e.g., "m_1", "m_2")
- "description": clear description of the milestone
- "priority": execution order (1 = first)
- "estimated_steps": estimated total number of GUI actions for this milestone
- "dependencies": list of milestone IDs that must complete first (empty for first milestone)
- "success_criteria": how to verify this milestone is complete
- "subtasks": array of subtasks, each with:
  - "id": unique identifier (e.g., "m_1_1", "m_1_2")
  - "description": specific GUI action description
  - "action_hint": type of action (click, type, scroll, identify, wait, back)
  - "expected_ui_element": the UI element to find/interact with
  - "alternative_ui_elements": alternative names for the same element (e.g., ["Help", "Support"])

Example format:
[
  {{
    "id": "m_1",
    "description": "Open Privacy settings",
    "priority": 1,
    "estimated_steps": 2,
    "dependencies": [],
    "success_criteria": "Privacy settings screen is displayed",
    "subtasks": [
      {{
        "id": "m_1_1",
        "description": "Locate 'Privacy' in the settings menu",
        "action_hint": "identify",
        "expected_ui_element": "Privacy",
        "alternative_ui_elements": ["Privacy Settings", "Privacy & Security"]
      }},
      {{
        "id": "m_1_2",
        "description": "Tap 'Privacy' to open the privacy settings",
        "action_hint": "click",
        "expected_ui_element": "Privacy",
        "alternative_ui_elements": []
      }}
    ]
  }},
  {{
    "id": "m_2",
    "description": "Open Ads settings",
    "priority": 2,
    "estimated_steps": 2,
    "dependencies": ["m_1"],
    "success_criteria": "Ads settings screen is displayed",
    "subtasks": [
      {{
        "id": "m_2_1",
        "description": "Locate 'Ads' in the privacy menu",
        "action_hint": "identify",
        "expected_ui_element": "Ads",
        "alternative_ui_elements": []
      }},
      {{
        "id": "m_2_2",
        "description": "Tap 'Ads' to open ads settings",
        "action_hint": "click",
        "expected_ui_element": "Ads",
        "alternative_ui_elements": []
      }}
    ]
  }}
]

Respond ONLY with the JSON array, no additional text.
"""
        return prompt

    def _parse_plan_response(self, response: str) -> Plan:
        """
        Parse the LLM response into a Plan object with Milestones and SubTasks.

        Args:
            response: Raw response string from the LLM

        Returns:
            Plan object with milestones and subtasks
        """
        import json

        try:
            data = json.loads(response)
            milestones = []

            for item in data:
                # Parse subtasks
                subtasks = []
                if "subtasks" in item:
                    for st in item["subtasks"]:
                        # Convert action_hint string to ActionType enum
                        action_type = ActionType(st["action_hint"])
                        
                        subtask = SubTask(
                            id=st["id"],
                            description=st["description"],
                            action_hint=action_type,
                            expected_ui_element=st["expected_ui_element"],
                            alternative_ui_elements=st.get("alternative_ui_elements", [])
                        )
                        subtasks.append(subtask)
                
                # Create milestone
                milestone = Milestone(
                    id=item["id"],
                    description=item["description"],
                    priority=item["priority"],
                    estimated_steps=item["estimated_steps"],
                    dependencies=item.get("dependencies", []),
                    success_criteria=item["success_criteria"],
                    subtasks=subtasks
                )
                milestones.append(milestone)
            
            # Create and return Plan
            plan = Plan(milestones=milestones)
            return plan

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
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
