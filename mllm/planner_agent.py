"""
Planner Agent for MLLM Module

Specialized agent for planning decisions using AssistantAgent.
Decomposes user goals into milestones and subtasks with grounded execution data.
Uses coordinates directly from OmniParser parsed elements.
"""

import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from mllm.assistant_agent import AssistantAgent
from mllm.enums import ExecutionStatus, ActionType


@dataclass
class SubTask:
    """Individual action within a milestone with grounded execution data"""
    id: str                              # "m_1_1"
    description: str                     # "Tap 'Privacy' button"
    action_hint: ActionType              # ActionType.CLICK, ActionType.TYPE, etc.
    expected_ui_element: str             # "Privacy" - what element to look for
    alternative_ui_elements: List[str] = field(default_factory=list)  # ["Privacy Settings", "Privacy & Security"]
    
    coordinates: Optional[List[int]] = None      # [x, y] - actual screen coordinates from OmniParser
    bounding_box: Optional[Dict[str, int]] = None  # {x, y, width, height} - element bounds
    element_type: Optional[str] = None           # "button", "text", "toggle", "icon", etc.
    confidence: Optional[float] = None           # 0.0-1.0 - detection confidence
    orientation: Optional[str] = None            # "horizontal", "vertical" - element orientation
    scroll_direction: Optional[str] = None       # "up", "down", "left", "right" - for SCROLL action
    scroll_distance: Optional[str] = None        # "short", "medium", "long" - for SCROLL action
    input_text: Optional[str] = None             # Text to input for TYPE action
    element_index: Optional[int] = None          # Index in parsed_elements list from OmniParser
    
    # Execution state
    status: ExecutionStatus = ExecutionStatus.PENDING
    executed_element: Optional[str] = None  # What element was actually interacted with
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
    
    def is_completed(self) -> bool:
        """Check if entire plan is completed"""
        return self.current_milestone_index >= len(self.milestones)
    
    def get_execution_summary(self) -> Dict:
        """Get summary of plan execution so far"""
        summary = {
            "total_milestones": len(self.milestones),
            "current_milestone": self.current_milestone_index + 1,
            "milestones_status": []
        }
        for m in self.milestones:
            summary["milestones_status"].append({
                "id": m.id,
                "description": m.description,
                "status": m.status.value,
                "subtask": f"{m.current_subtask_index + 1}/{len(m.subtasks)}"
            })
        return summary


class PlannerAgent:
    """
    Specialized agent for planning decisions using AssistantAgent.
    Decomposes user goals into milestones and grounded subtasks with execution data.
    Uses coordinates directly from OmniParser parsed elements.
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
        image_base64: Optional[str] = None,
        parsed_elements: Optional[List[Dict[str, Any]]] = None
    ) -> Plan:
        """
        Decompose a user goal into milestones with grounded subtasks.

        Args:
            goal: The user's goal/task description
            context: Context including history, past interactions
            constraints: List of constraints for planning
            image_base64: Optional base64 encoded image with highlighted UI elements from GUI Parser
            parsed_elements: Optional list of parsed elements from OmniParser with coordinates

        Returns:
            Plan object containing milestones and grounded subtasks
        """
        self._logger.info(f"Planning goal: {goal}")

        # Create the planning prompt with parsed elements info
        prompt = self._create_planning_prompt(goal, context, constraints, parsed_elements)

        # Query the AssistantAgent with optional image from GUI Parser
        response = self._assistant_agent.query(
            prompt, 
            image_bytes=self._base64_to_bytes(image_base64) if image_base64 else None
        )

        # Parse the response into Plan
        plan = self._parse_plan_response(response, parsed_elements)
        self._logger.info(f"Generated plan with {len(plan.milestones)} milestones")

        return plan

    def _create_planning_prompt(
        self, 
        goal: str, 
        context: Dict, 
        constraints: List[str],
        parsed_elements: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Create a structured prompt for goal decomposition with grounded subtasks.
        
        The planner receives GUI state information and parsed element data.
        It should select which element to interact with by its element_index.

        Args:
            goal: The user's goal
            context: Context dictionary with history/interactions
            constraints: List of constraint strings
            parsed_elements: List of elements detected by OmniParser

        Returns:
            Formatted prompt string for the LLM
        """
        context_str = "\n".join([f"- {k}: {v}" for k, v in context.items()]) if context else "None"
        constraints_str = "\n".join([f"- {c}" for c in constraints]) if constraints else "None"
        
        # Build elements reference for the planner
        elements_ref = self._build_elements_reference(parsed_elements)

        prompt = f"""You are a task planner for a mobile GUI automation agent.

## User Goal
{goal}

## Context
{context_str}

## Constraints
{constraints_str}

## Available UI Elements (from OmniParser)
{elements_ref}

## Instructions
Decompose the user goal into 2-4 sequential MILESTONES (major phases).
For each milestone, break it down into 1-3 specific SUBTASKS (concrete GUI actions).

IMPORTANT: You must use element_index from the available elements list above.
DO NOT generate new coordinates - use the coordinates from the parsed elements.

For each subtask, you MUST provide:
1. The element_index of the UI element to interact with (from the list above)
2. The ACTION TYPE needed (click, type, scroll, identify, wait, back, home, recent, enter, long_press, drag)
3. Alternative element_indices in case the primary is not available

Think step-by-step:
1. What is the ultimate objective?
2. What are the major phases to achieve it?
3. For each phase, what specific GUI interactions are needed?
4. Which elements (by element_index) need to be interacted with?
5. What action should be performed on each element?
6. How can the user verify each subtask succeeded?

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
  - "action_hint": type of action (click, type, scroll, identify, wait, back, home, recent, enter, long_press, drag)
  - "expected_ui_element": the UI element content/description
  - "element_index": the index of the element from the available elements list above
  - "alternative_element_indices": list of alternative element indices if primary is not available
  - "scroll_direction": "up", "down", "left", "right" (for SCROLL action only)
  - "scroll_distance": "short", "medium", "long" (for SCROLL action only)
  - "input_text": text to input (for TYPE action only)

Example format:
[
  {{
    "id": "m_1",
    "description": "Navigate to and open Privacy settings",
    "priority": 1,
    "estimated_steps": 2,
    "dependencies": [],
    "success_criteria": "Privacy settings screen is displayed",
    "subtasks": [
      {{
        "id": "m_1_1",
        "description": "Scroll down to find Settings icon",
        "action_hint": "scroll",
        "expected_ui_element": "Screen scrolling",
        "element_index": null,
        "alternative_element_indices": [],
        "scroll_direction": "down",
        "scroll_distance": "medium",
        "input_text": null
      }},
      {{
        "id": "m_1_2",
        "description": "Click Settings icon at element [8]",
        "action_hint": "click",
        "expected_ui_element": "Settings",
        "element_index": 8,
        "alternative_element_indices": [],
        "scroll_direction": null,
        "scroll_distance": null,
        "input_text": null
      }}
    ]
  }}
]

Respond ONLY with the JSON array, no additional text.
"""
        return prompt

    def _build_elements_reference(
        self, 
        parsed_elements: Optional[List[Dict[str, Any]]]
    ) -> str:
        """
        Build a reference list of available elements for the planner.

        Args:
            parsed_elements: List of elements from OmniParser

        Returns:
            Formatted string describing available elements with indices
        """
        if not parsed_elements:
            return "No UI elements detected on screen."

        lines = ["Elements available on screen (use element_index to reference):"]
        for element in parsed_elements:
            idx = element.get("element_index", "?")
            elem_type = element.get("type", "unknown")
            content = element.get("content", "")[:50]
            bbox = element.get("bbox", [])
            interactivity = element.get("interactivity", False)
            
            interactive_str = "" if interactivity else "✗"
            
            if bbox and len(bbox) == 4:
                # bbox is [x_min, y_min, x_max, y_max] (normalized 0-1)
                x_min, y_min, x_max, y_max = bbox
                center_x = (x_min + x_max) / 2
                center_y = (y_min + y_max) / 2
                bbox_str = f"center_norm=[{center_x:.2f}, {center_y:.2f}]"
            else:
                bbox_str = "bbox=unknown"
            
            lines.append(
                f"  [{idx:2d}] {elem_type:8s} | {content:50s} | {bbox_str} | interactive:{interactive_str}"
            )

        return "\n".join(lines)

    def _parse_plan_response(
        self, 
        response: str,
        parsed_elements: Optional[List[Dict[str, Any]]] = None
    ) -> Plan:
        """
        Parse the LLM response into a Plan object with Milestones and grounded SubTasks.
        
        Uses element_index from parsed_elements to populate coordinates.

        Args:
            response: Raw response string from the LLM
            parsed_elements: List of parsed elements to map indices to coordinates

        Returns:
            Plan object with milestones and grounded subtasks
        """
        import json
        import re

        try:
            # Extract JSON from markdown code fences if present
            json_str = response.strip()
            
            # Check if response is wrapped in markdown code fences
            if json_str.startswith("```"):
                # Remove markdown wrapper
                match = re.search(r'```(?:json)?\s*\n(.*?)\n```', json_str, re.DOTALL)
                if match:
                    json_str = match.group(1)
                else:
                    # Try alternate pattern without newlines
                    json_str = re.sub(r'^```(?:json)?\s*', '', json_str)
                    json_str = re.sub(r'```\s*$', '', json_str)
            
            data = json.loads(json_str)
            milestones = []
            
            # Create a map of element_index to element data
            element_map = {}
            if parsed_elements:
                for elem in parsed_elements:
                    idx = elem.get("element_index")
                    if idx is not None:
                        element_map[idx] = elem

            for item in data:
                # Parse subtasks
                subtasks = []
                if "subtasks" in item:
                    for st in item["subtasks"]:
                        # Convert action_hint string to ActionType enum
                        action_type = ActionType(st["action_hint"])
                        
                        # Extract element_index and get coordinates from parsed_elements
                        element_index = st.get("element_index")
                        coordinates = None
                        element_type = None
                        bbox = None
                        
                        if element_index is not None and element_index in element_map:
                            element = element_map[element_index]
                            
                            # Extract coordinates from bbox (normalized 0-1)
                            elem_bbox = element.get("bbox", [])
                            if elem_bbox and len(elem_bbox) == 4:
                                # bbox is [x_min, y_min, x_max, y_max] (normalized 0-1)
                                # Calculate center point for clicking
                                x_min, y_min, x_max, y_max = elem_bbox
                                center_x = (x_min + x_max) / 2
                                center_y = (y_min + y_max) / 2
                                
                                pixel_x = int(center_x * 720)
                                pixel_y = int(center_y * 1600)
                                coordinates = [pixel_x, pixel_y]
                                
                                bbox = {
                                    "x": int(x_min * 720),
                                    "y": int(y_min * 1600),
                                    "width": int((x_max - x_min) * 720),
                                    "height": int((y_max - y_min) * 1600)
                                }
                            
                            element_type = element.get("type")
                        
                        subtask = SubTask(
                            id=st["id"],
                            description=st["description"],
                            action_hint=action_type,
                            expected_ui_element=st["expected_ui_element"],
                            alternative_ui_elements=st.get("alternative_element_indices", []),
                            # Grounded data from OmniParser
                            coordinates=coordinates,
                            bounding_box=bbox,
                            element_type=element_type,
                            element_index=element_index,
                            scroll_direction=st.get("scroll_direction"),
                            scroll_distance=st.get("scroll_distance"),
                            input_text=st.get("input_text")
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
