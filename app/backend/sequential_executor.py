"""
Sequential Executor for Interactive GUI Agent

Implements the sequential flow:
1. Capture screenshot and parse with OmniParser to get annotated image
2. Send annotated screenshot to Planner with user goal/prompt
3. If goal not fulfilled, Planner creates action plan
4. Executor takes action, waits 5 seconds, captures new screenshot
5. Loop until goal fulfilled or 50 steps reached

This orchestrator manages the full conversation between perception (OmniParser),
planning (Planner), and action (Executor).
"""

import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Minimal 1×1 gray PNG returned by mock screenshot capture.
_MOCK_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

from adb import adb
from config import Config
from mllm import AssistantAgent, Plan, PlannerAgent
from planning.constraint_retriever import ConstraintRetriever
from planning.context_retriever import ContextRetriever
from planning.planner import Planner
from grounder.annotator import draw_parsed_elements
from .omniparser_client import OmniParserClient, OmniParserClientError, ParseScreenResult
from .goal_completion_checker import GoalCompletionChecker


@dataclass
class ExecutionStep:
    """Record of a single execution step"""
    step_number: int
    timestamp: str
    action_executed: Optional[str] = None
    screenshot_before: Optional[bytes] = None
    screenshot_annotated: Optional[bytes] = None
    elements_detected: int = 0
    parsed_elements: List[Dict[str, Any]] = field(default_factory=list)
    plan_generated: Optional[Plan] = None
    goal_achieved: bool = False
    goal_check_reasoning: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SequentialExecutionResult:
    """Final result of sequential execution"""
    success: bool
    goal_achieved: bool
    total_steps: int
    steps: List[ExecutionStep] = field(default_factory=list)
    final_screenshot: Optional[bytes] = None
    errors: List[str] = field(default_factory=list)
    completion_message: str = ""
    timestamp: str = ""


class SequentialExecutor:
    """
    Orchestrates sequential execution: OmniParser → Planner → Executor loop.

    Flow:
    1. Capture screenshot from device (or use provided image)
    2. Parse with OmniParser to detect UI elements with bounding boxes
    3. Annotate screenshot with detected elements
    4. Send annotated screenshot + parsed elements data to Planner with user goal
    5. Planner uses element data to decide which coordinates to click
    6. Check if goal is achieved using GoalCompletionChecker (AssistantAgent)
    7. If action needed: Executor performs it, waits 5 seconds
    8. Go to step 1 (loop until goal achieved or 50 steps)
    """

    def __init__(
        self,
        device_id: str,
        omniparser_client: Optional[OmniParserClient],
        config: Config,
        logger: logging.Logger,
        sequential_runner: Optional[Any] = None,
        max_steps: int = 15,
        step_delay_sec: float = 4.0,
        mock: bool = False,
    ):
        """
        Initialize the Sequential Executor.

        Args:
            device_id: Android device ID for ADB
            omniparser_client: OmniParserClient instance (may be None when mock=True)
            config: Config object with model/api_key
            logger: Logger instance
            sequential_runner: Optional SequentialRunner for emitting events
            max_steps: Maximum execution steps (default: 15)
            step_delay_sec: Delay after action execution (default: 3.0 seconds)
            mock: When True all external calls (OmniParser, ADB, LLM) return canned
                  data so the full event pipeline can be exercised without real devices
                  or API keys.
        """
        self.device_id = device_id
        self.omniparser_client = omniparser_client
        self.config = config
        self.logger = logger
        self.sequential_runner = sequential_runner
        self.max_steps = max_steps
        self.step_delay_sec = step_delay_sec
        self.mock = mock

        # Initialize planner components
        self.assistant_agent = AssistantAgent(model=config.model, api_key=config.api_key, request_timeout=config.request_timeout)
        self.planner_agent = PlannerAgent(self.assistant_agent)
        self.context_retriever = ContextRetriever(config)
        self.constraint_retriever = ConstraintRetriever(config)
        self.planner = Planner(
            planner_agent=self.planner_agent,
            context_retriever=self.context_retriever,
            constraint_retriever=self.constraint_retriever,
            logger=logger,
        )

        # Initialize goal completion checker
        self.goal_checker = GoalCompletionChecker(
            assistant_agent=self.assistant_agent,
            logger=logger,
        )

        self.logger.info(f"SequentialExecutor initialized for device: {device_id}")

    async def execute(
        self,
        user_goal: str,
        task_id: Optional[str] = None,
        initial_screenshot: Optional[bytes] = None,
        output_dir: str = "output",
    ) -> SequentialExecutionResult:
        """
        Execute the sequential flow until goal achieved or max steps reached.

        Args:
            user_goal: The user's goal/prompt (e.g., "Open Settings app")
            task_id: Optional task ID for event emission via SequentialRunner
            initial_screenshot: Optional initial screenshot bytes (for testing)
            output_dir: Directory to save annotated screenshots and logs

        Returns:
            SequentialExecutionResult with execution details
        """
        self.logger.info("=" * 80)
        self.logger.info("STARTING SEQUENTIAL EXECUTION")
        self.logger.info("=" * 80)
        self.logger.info(f"Goal: {user_goal}")
        self.logger.info(f"Max steps: {self.max_steps}")
        self.logger.info("")

        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Initialize result
        result = SequentialExecutionResult(
            success=False,
            goal_achieved=False,
            total_steps=0,
            timestamp=datetime.now().isoformat(),
        )

        # Emit task started event
        if task_id and self.sequential_runner:
            await self.sequential_runner.emit(
                task_id=task_id,
                stage="planning",
                event_type="task_started",
                title="Sequential Execution Started",
                description=f"Goal: {user_goal}",
            )

        # Step 0: Get initial screenshot if not provided
        current_screenshot = initial_screenshot
        if current_screenshot is None:
            self.logger.info("Capturing initial screenshot from device...")
            current_screenshot = self._mock_screenshot() if self.mock else self._capture_screenshot_from_device()
            if current_screenshot is None:
                result.errors.append("Failed to capture initial screenshot")
                result.completion_message = "Failed to capture initial screenshot"
                
                if task_id and self.sequential_runner:
                    await self.sequential_runner.emit(
                        task_id=task_id,
                        stage="failed",
                        event_type="task_failed",
                        title="Initial Screenshot Failed",
                        description="Could not capture screenshot from device",
                    )
                return result

        # Main execution loop
        step_count = 0
        while step_count < self.max_steps:
            step_count += 1
            self.logger.info("")
            self.logger.info("=" * 80)
            self.logger.info(f"STEP {step_count}/{self.max_steps}")
            self.logger.info("=" * 80)

            try:
                # ====================================================================
                # PHASE 1: PARSE SCREENSHOT WITH OMNIPARSER
                # ====================================================================
                self.logger.info("")
                self.logger.info("PHASE 1: Parsing screenshot with OmniParser...")
                self.logger.info("-" * 80)

                step_data = ExecutionStep(
                    step_number=step_count,
                    timestamp=datetime.now().isoformat(),
                    screenshot_before=current_screenshot,
                )

                parse_result = (
                    self._mock_parse_screen(step_count)
                    if self.mock
                    else await self.omniparser_client.parse_screen(
                        image_bytes=current_screenshot,
                        filename=f"step_{step_count}.png",
                    )
                )

                self.logger.info(
                    f" Parse completed in {parse_result.latency_ms:.2f}ms"
                )
                self.logger.info(
                    f"  Elements detected: {len(parse_result.parsed_screen)}"
                )

                step_data.elements_detected = len(parse_result.parsed_screen)
                step_data.parsed_elements = parse_result.parsed_screen
                step_data.metadata["parse_latency_ms"] = parse_result.latency_ms
                step_data.metadata["request_id"] = parse_result.request_id

                # Log parsed elements
                self._log_parsed_elements(parse_result.parsed_screen)

                # ====================================================================
                # PHASE 2: ANNOTATE SCREENSHOT
                # ====================================================================
                self.logger.info("")
                self.logger.info("PHASE 2: Annotating screenshot...")
                self.logger.info("-" * 80)

                annotated_image_path = output_path / f"step_{step_count}_annotated.png"
                temp_screenshot_path = output_path / f"step_{step_count}_raw.png"
                try:
                    with open(temp_screenshot_path, "wb") as f:
                        f.write(current_screenshot)

                    draw_parsed_elements(
                        image_path=str(temp_screenshot_path),
                        parsed_content_list=parse_result.parsed_screen,
                        output_path=str(annotated_image_path),
                        draw_bbox_config={
                            "text_scale": 0.4,
                            "text_padding": 5,
                            "text_thickness": 2,
                            "thickness": 3,
                        },
                    )

                    with open(annotated_image_path, "rb") as f:
                        annotated_screenshot_bytes = f.read()

                    step_data.screenshot_annotated = annotated_screenshot_bytes

                    self.logger.info(
                        f" Screenshot annotated: {annotated_image_path.name}"
                    )
                except Exception as e:
                    self.logger.warning(f"⚠ Failed to annotate screenshot: {e}")
                    step_data.screenshot_annotated = current_screenshot

                # Emit GUI state updated event
                if task_id and self.sequential_runner:
                    raw_screenshot_url = f"/output/{temp_screenshot_path.name}?t={int(time.time() * 1000)}"
                    await self.sequential_runner.emit(
                        task_id=task_id,
                        stage="executing_subgoal",
                        event_type="gui_state_updated",
                        title=f"Step {step_count}: GUI State Parsed",
                        description=f"Detected {len(parse_result.parsed_screen)} UI elements",
                        subgoal_index=step_count,
                        screenshot_url=raw_screenshot_url,
                        metadata={
                            "step": step_count,
                            "elements_count": len(parse_result.parsed_screen),
                            "parse_latency_ms": parse_result.latency_ms,
                            "raw_screenshot_url": raw_screenshot_url,
                        },
                    )

                # ====================================================================
                # PHASE 3: CHECK IF GOAL ACHIEVED (Using AssistantAgent)
                # ====================================================================
                self.logger.info("")
                self.logger.info("PHASE 3: Checking if goal is achieved...")
                self.logger.info("-" * 80)

                if self.mock:
                    goal_achieved, goal_reasoning = self._mock_goal_check(step_count)
                else:
                    goal_achieved, goal_reasoning = self.goal_checker.check_goal_achieved(
                        user_goal=user_goal,
                        current_screenshot=current_screenshot,
                        parsed_elements=parse_result.parsed_screen,
                        step_count=step_count,
                        max_steps=self.max_steps,
                    )

                step_data.goal_check_reasoning = goal_reasoning

                if goal_achieved:
                    step_data.goal_achieved = True
                    self.logger.info(" GOAL ACHIEVED!")
                    result.goal_achieved = True
                    result.success = True
                    result.total_steps = step_count
                    result.final_screenshot = current_screenshot
                    result.completion_message = f"Goal achieved in {step_count} steps"
                    result.steps.append(step_data)
                    
                    # Emit goal achieved event
                    if task_id and self.sequential_runner:
                        await self.sequential_runner.emit(
                            task_id=task_id,
                            stage="completed",
                            event_type="task_completed",
                            title="Goal Achieved",
                            description=f"Goal accomplished in {step_count} steps. {goal_reasoning}",
                        )
                    break

                # ====================================================================
                # PHASE 4: SEND TO PLANNER WITH PARSED ELEMENTS DATA
                # ====================================================================
                self.logger.info("")
                self.logger.info("PHASE 4: Sending to Planner with element data...")
                self.logger.info("-" * 80)

                planner_context = self._build_planner_context(
                    user_goal=user_goal,
                    step_number=step_count,
                    parsed_elements=parse_result.parsed_screen,
                )

                self.logger.info(f"  Current step: {step_count}/{self.max_steps}")
                self.logger.info(
                    f"  Elements available to planner: {len(parse_result.parsed_screen)}"
                )

                plan = (
                    self._mock_plan()
                    if self.mock
                    else self.planner.plan(
                        user_goal=planner_context,
                        image_base64=base64.b64encode(annotated_screenshot_bytes).decode("utf-8")
                        if step_data.screenshot_annotated
                        else None,
                        parsed_elements=parse_result.parsed_screen,
                    )
                )

                step_data.plan_generated = plan

                self.logger.info(f" Plan generated with {len(plan.milestones)} milestones")
                for milestone in plan.milestones:
                    self.logger.info(
                        f"  [{milestone.priority}] {milestone.id}: {milestone.description}"
                    )

                    for subtask in milestone.subtasks:
                        self.logger.info(
                            f"     - {subtask.id}: {subtask.description} (Action: {subtask.action_hint.value}, Element: {subtask.expected_ui_element})"
                        )
                        self.logger.debug(f"       Subtask details: {subtask.coordinates}, {subtask.alternative_ui_elements}")

                # Emit plan generated event
                if task_id and self.sequential_runner:
                    await self.sequential_runner.emit(
                        task_id=task_id,
                        stage="planning",
                        event_type="plan_generated",
                        title=f"Step {step_count}: Plan Generated",
                        description=f"Generated plan with {len(plan.milestones)} milestone(s)",
                        subgoal_index=step_count,
                        metadata={
                            "step": step_count,
                            "milestones_count": len(plan.milestones),
                            "milestones": [m.description for m in plan.milestones],
                        },
                    )

                # ====================================================================
                # PHASE 5: EXECUTE NEXT ACTION
                # ====================================================================
                self.logger.info("")
                self.logger.info("PHASE 5: Executing next action...")
                self.logger.info("-" * 80)

                if not plan.milestones:
                    self.logger.warning("No milestones in plan, waiting...")
                    await asyncio.sleep(self.step_delay_sec)
                    result.steps.append(step_data)
                    continue

                current_milestone = plan.milestones[0]
                if not current_milestone.subtasks:
                    self.logger.warning("No subtasks in milestone, waiting...")
                    await asyncio.sleep(self.step_delay_sec)
                    result.steps.append(step_data)
                    continue

                subtask = current_milestone.subtasks[0]

                self.logger.info(
                    f"Executing subtask: {subtask.id} - {subtask.description}"
                )
                self.logger.info(f"  Action: {subtask.action_hint.value}")
                self.logger.info(f"  Element: {subtask.expected_ui_element}")
                if subtask.coordinates:
                    self.logger.info(f"  Coordinates: {subtask.coordinates}")

                # Emit action decided event
                if task_id and self.sequential_runner:
                    await self.sequential_runner.emit(
                        task_id=task_id,
                        stage="executing_subgoal",
                        event_type="action_decided",
                        title=f"Step {step_count}: Action Decided",
                        description=f"Action: {subtask.action_hint.value} on {subtask.expected_ui_element}",
                        subgoal_index=step_count,
                        reasoning=subtask.description,
                        metadata={
                            "step": step_count,
                            "action_type": subtask.action_hint.value,
                            "element": subtask.expected_ui_element,
                            "coordinates": subtask.coordinates,
                        },
                    )

                action_dict = self._subtask_to_action(subtask)
                if action_dict:
                    if self.mock:
                        is_valid, validation_error = True, ""
                        success = True
                    else:
                        is_valid, validation_error = adb.validate_action(action_dict)
                        success = adb.execute_action(action_dict, self.device_id) if is_valid else False

                    if is_valid:
                        step_data.action_executed = action_dict.get("action_type")
                        step_data.metadata["action_details"] = action_dict

                        if success:
                            self.logger.info(
                                f" Action executed: {action_dict['action_type']}"
                            )

                            if task_id and self.sequential_runner:
                                await self.sequential_runner.emit(
                                    task_id=task_id,
                                    stage="executing_subgoal",
                                    event_type="action_executed",
                                    title=f"Step {step_count}: Action Executed",
                                    description=f"Executed: {action_dict['action_type']}",
                                    subgoal_index=step_count,
                                )
                        else:
                            self.logger.error(f"✗ Action execution failed")
                    else:
                        self.logger.error(f"Invalid action: {validation_error}")
                        step_data.error = validation_error
                else:
                    self.logger.warning("Could not convert subtask to action")

                # ====================================================================
                # PHASE 6: WAIT AND CAPTURE NEXT SCREENSHOT
                # ====================================================================
                self.logger.info("")
                self.logger.info(
                    f"PHASE 6: Waiting {self.step_delay_sec}s for UI update..."
                )
                self.logger.info("-" * 80)

                await asyncio.sleep(self.step_delay_sec)

                self.logger.info("Capturing next screenshot...")
                current_screenshot = self._mock_screenshot() if self.mock else self._capture_screenshot_from_device()
                if current_screenshot is None:
                    error_msg = "Failed to capture screenshot after action"
                    self.logger.error(error_msg)
                    step_data.error = error_msg
                    result.errors.append(error_msg)

                result.steps.append(step_data)

            except Exception as e:
                self.logger.exception(f"Error in step {step_count}: {e}")
                step_data.error = str(e)
                result.errors.append(f"Step {step_count}: {str(e)}")
                result.steps.append(step_data)
                
                if task_id and self.sequential_runner:
                    await self.sequential_runner.emit(
                        task_id=task_id,
                        stage="failed",
                        event_type="task_failed",
                        title=f"Step {step_count}: Error",
                        description=f"Error occurred: {str(e)}",
                    )

        # ====================================================================
        # FINAL SUMMARY
        # ====================================================================
        self.logger.info("")
        self.logger.info("=" * 80)
        self.logger.info("EXECUTION SUMMARY")
        self.logger.info("=" * 80)

        result.total_steps = step_count
        result.final_screenshot = current_screenshot

        if result.goal_achieved:
            self.logger.info(f" GOAL ACHIEVED in {step_count} steps!")
        elif step_count >= self.max_steps:
            result.completion_message = (
                f"Max steps ({self.max_steps}) reached without achieving goal"
            )
            self.logger.info(f"⚠ Max steps ({self.max_steps}) reached")
            
            if task_id and self.sequential_runner:
                await self.sequential_runner.emit(
                    task_id=task_id,
                    stage="completed",
                    event_type="task_completed",
                    title="Max Steps Reached",
                    description=f"Reached maximum {self.max_steps} steps without goal completion",
                )
        else:
            result.completion_message = "Execution stopped"
            self.logger.info("Execution stopped")

        self.logger.info(f"Total steps executed: {step_count}")
        if result.errors:
            self.logger.info(f"Errors encountered: {len(result.errors)}")
            for error in result.errors:
                self.logger.info(f"  - {error}")

        self.logger.info("=" * 80)

        return result

    def _build_planner_context(
        self,
        user_goal: str,
        step_number: int,
        parsed_elements: List[Dict[str, Any]],
    ) -> str:
        """
        Build a comprehensive context for the planner that includes:
        - User goal
        - Current step
        - Available UI elements with their properties and coordinates

        Args:
            user_goal: Original user goal
            step_number: Current step number
            parsed_elements: List of elements detected by OmniParser

        Returns:
            Formatted context string for the planner
        """
        # Format elements for planner
        elements_description = self._format_elements_for_planner(parsed_elements)

        context = f"""
User Goal: {user_goal}
Current Step: {step_number}

Available UI Elements on Screen:
{elements_description}

Task: Analyze the current screen and the available UI elements.
1. Determine if the goal has been achieved. If yes, indicate SUCCESS.
2. If not, decide the next action to take based on the available elements.
3. Provide specific coordinates from the element data for clicking or interacting.
4. Use the element_index or bbox coordinates to precisely identify which element to interact with.

For each action you plan:
- Use the element_index (0-based numbering) shown in the elements list
- Use the bbox coordinates [x_min_ratio, y_min_ratio, x_max_ratio, y_max_ratio] (normalized 0-1)
- Convert bbox to actual pixel coordinates: x = bbox_center_x * screen_width, y = bbox_center_y * screen_height
- Specify exact coordinates for clicks: [x_pixel, y_pixel]
"""
        return context

    def _format_elements_for_planner(
        self, parsed_elements: List[Dict[str, Any]]
    ) -> str:
        """
        Format parsed elements into a readable list for the planner.

        Args:
            parsed_elements: List of element dicts from OmniParser

        Returns:
            Formatted string describing available elements
        """
        if not parsed_elements:
            return "No UI elements detected on screen."

        lines = []
        for idx, element in enumerate(parsed_elements):
            element_type = element.get("type", "unknown")
            content = element.get("content", "")
            bbox = element.get("bbox", [])
            interactivity = element.get("interactivity", False)

            # Calculate center coordinates from bbox
            if bbox and len(bbox) == 4:
                x_min, y_min, x_max, y_max = bbox
                center_x = (x_min + x_max) / 2
                center_y = (y_min + y_max) / 2
                bbox_str = (
                    f"bbox=[{x_min:.3f}, {y_min:.3f}, {x_max:.3f}, {y_max:.3f}] "
                    f"center=[{center_x:.3f}, {center_y:.3f}]"
                )
            else:
                bbox_str = "bbox=unknown"

            interactive_str = "interactive" if interactivity else "non-interactive"

            lines.append(
                f"  [{idx}] {element_type.upper():12s} | Content: {content[:50]:50s} | {bbox_str} | {interactive_str}"
            )

        return "\n".join(lines)

    def _log_parsed_elements(self, parsed_elements: List[Dict[str, Any]]) -> None:
        """
        Log the parsed elements for debugging.

        Args:
            parsed_elements: List of element dicts from OmniParser
        """
        if not parsed_elements:
            self.logger.info("No elements detected")
            return

        self.logger.info(f"Detected {len(parsed_elements)} elements:")
        for idx, element in enumerate(parsed_elements):
            element_type = element.get("type", "unknown")
            content = element.get("content", "")[:40]
            bbox = element.get("bbox", [])
            self.logger.debug(
                f"  [{idx}] {element_type}: '{content}' bbox={bbox}"
            )

    # ------------------------------------------------------------------
    # Mock helpers — used when self.mock is True
    # ------------------------------------------------------------------

    def _mock_screenshot(self) -> bytes:
        self.logger.info("[MOCK] Returning synthetic screenshot")
        return _MOCK_PNG

    def _mock_parse_screen(self, step: int) -> "ParseScreenResult":
        self.logger.info(f"[MOCK] Returning synthetic OmniParser result for step {step}")
        return ParseScreenResult(
            request_id=f"mock-{step}",
            parsed_screen=[
                {"type": "button", "content": "Settings", "bbox": [0.1, 0.2, 0.4, 0.25], "interactivity": True, "element_index": 0},
                {"type": "text", "content": "Home Screen", "bbox": [0.3, 0.05, 0.7, 0.1], "interactivity": False, "element_index": 1},
                {"type": "icon", "content": "Apps", "bbox": [0.6, 0.8, 0.75, 0.9], "interactivity": True, "element_index": 2},
            ],
            latency_ms=1.0,
        )

    def _mock_goal_check(self, step: int) -> tuple[bool, str]:
        if step >= 2:
            self.logger.info("[MOCK] Goal marked achieved at step %d", step)
            return True, "Mock: simulated goal achieved after one action cycle"
        self.logger.info("[MOCK] Goal not yet achieved at step %d — will plan and act", step)
        return False, "Mock: proceeding with planning and action"

    def _mock_plan(self) -> "Plan":
        from mllm import ActionType, Milestone, Plan, SubTask
        self.logger.info("[MOCK] Returning synthetic plan")
        return Plan(
            milestones=[
                Milestone(
                    id="m_1",
                    description="Mock: tap Settings icon",
                    priority=1,
                    estimated_steps=1,
                    dependencies=[],
                    success_criteria="Settings app is open",
                    subtasks=[
                        SubTask(
                            id="m_1_1",
                            description="Mock: tap on Settings button",
                            action_hint=ActionType.CLICK,
                            expected_ui_element="Settings",
                            coordinates=[540, 960],
                        )
                    ],
                )
            ]
        )

    # ------------------------------------------------------------------

    def _capture_screenshot_from_device(self) -> Optional[bytes]:
        """
        Capture screenshot from device using ADB.

        Returns:
            Screenshot bytes or None if failed
        """
        try:
            temp_local_path = "output/temp_screenshot.png"
            device_screenshot_path = "/sdcard/gui_agent_screenshot.png"

            # Execute screencap on device
            screencap_cmd = ["shell", "screencap", "-p", device_screenshot_path]
            success, output = adb.run_adb_command(
                screencap_cmd,
                device_id=self.device_id,
            )

            if not success:
                self.logger.error(f"Failed to execute screencap: {output}")
                return None

            # Pull screenshot from device
            pull_cmd = ["pull", device_screenshot_path, temp_local_path]
            success, output = adb.run_adb_command(
                pull_cmd,
                device_id=self.device_id,
                timeout=60,
            )

            if not success:
                self.logger.error(f"Failed to pull screenshot: {output}")
                return None

            # Read screenshot bytes
            with open(temp_local_path, "rb") as f:
                screenshot_bytes = f.read()

            return screenshot_bytes

        except Exception as e:
            self.logger.error(f"Error capturing screenshot: {e}")
            return None

    def _subtask_to_action(self, subtask) -> Optional[Dict[str, Any]]:
        """
        Convert a SubTask to an ADB action dictionary.

        Args:
            subtask: SubTask object from planner

        Returns:
            Action dictionary or None
        """
        try:
            action_hint = subtask.action_hint
            target_x = subtask.coordinates[0] if subtask.coordinates else 540
            target_y = subtask.coordinates[1] if subtask.coordinates else 920

            if action_hint.value == "click":
                return {"action_type": "click", "target": [target_x, target_y]}

            elif action_hint.value == "long_press":
                return {
                    "action_type": "long_press",
                    "target": [target_x, target_y],
                    "duration": 1000,
                }

            elif action_hint.value == "type":
                text = subtask.input_text or subtask.expected_ui_element or "text"
                return {"action_type": "input_text", "text": text}

            elif action_hint.value == "scroll":
                direction = subtask.scroll_direction or "down"
                distance = subtask.scroll_distance or "medium"
                return {
                    "action_type": "swipe",
                    "start": [target_x, target_y],
                    "direction": direction,
                    "distance": distance,
                }

            elif action_hint.value == "drag":
                end_x = target_x + 200
                end_y = target_y + 200
                return {
                    "action_type": "drag",
                    "start": [target_x, target_y],
                    "end": [end_x, end_y],
                    "duration": 500,
                }

            elif action_hint.value == "enter":
                return {"action_type": "enter"}

            elif action_hint.value == "back":
                return {"action_type": "navigate_back"}

            elif action_hint.value == "home":
                return {"action_type": "navigate_home"}

            elif action_hint.value == "recent":
                return {"action_type": "navigate_recent"}

            elif action_hint.value == "identify":
                return None

            elif action_hint.value == "wait":
                return {"action_type": "wait"}

            else:
                self.logger.warning(f"Unknown action hint: {action_hint}")
                return None

        except Exception as e:
            self.logger.error(f"Error converting subtask to action: {e}")
            return None

