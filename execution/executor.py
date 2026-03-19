"""
Executor for Step 3 of ASSIST-GUI Pipeline

Responsible for executing a Plan by:
1. Receiving Plan with Milestones and SubTasks
2. Converting SubTask actions to ADB commands
3. Executing actions on mobile device
4. Capturing screenshots after each action
5. Tracking execution state and handling failures

Integration:
- Input: Plan object from Planner
- Process: Execute each SubTask sequentially
- Output: ExecutionResult with status and screenshots
- Error Handling: Catch and log execution failures
"""

import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from mllm.planner_agent import Plan, Milestone, SubTask
from mllm.enums import ExecutionStatus, ActionType
from adb import adb


@dataclass
class ExecutionResult:
    """Result of executing a single action"""
    subtask_id: str
    action_type: ActionType
    success: bool
    timestamp: str
    screenshot_before: Optional[bytes] = None
    screenshot_after: Optional[bytes] = None
    error_message: Optional[str] = None
    executed_element: Optional[str] = None


@dataclass
class MilestoneExecutionResult:
    """Result of executing a complete milestone"""
    milestone_id: str
    success: bool
    timestamp: str
    completed_subtasks: int
    failed_subtask_id: Optional[str] = None
    error_message: Optional[str] = None
    execution_history: List[ExecutionResult] = field(default_factory=list)


class Executor:
    """
    Executes a Plan on a mobile device using ADB.
    
    Converts high-level SubTasks (with ActionType enums) into low-level ADB commands.
    Tracks execution state and captures screenshots for verification.
    """

    def __init__(
        self,
        device_id: str,
        logger: logging.Logger,
        adb_path: str = adb.DEFAULT_ADB_PATH
    ):
        """
        Initialize the Executor.

        Args:
            device_id: Android device ID or emulator name
            logger: Logger instance for logging
            adb_path: Path to adb executable
        """
        self._device_id = device_id
        self._logger = logger
        self._adb_path = adb_path
        
        self._logger.info(f"Executor initialized for device: {device_id}")
        
        # Verify device is connected
        if not adb.verify_device_connected(device_id, adb_path):
            self._logger.warning(f"Device {device_id} may not be connected")

    def execute_plan(self, plan: Plan) -> Tuple[bool, List[MilestoneExecutionResult]]:
        """
        Execute the complete plan.

        Args:
            plan: Plan object with milestones and subtasks

        Returns:
            Tuple[bool, List[MilestoneExecutionResult]]: 
            - success: True if all milestones completed
            - results: List of milestone execution results
        """
        self._logger.info(f"Starting plan execution with {len(plan.milestones)} milestones")
        
        results = []
        all_success = True
        
        # Execute each milestone in order
        for milestone_idx, milestone in enumerate(plan.milestones):
            self._logger.info(f"Executing milestone {milestone_idx + 1}/{len(plan.milestones)}: {milestone.id}")
            
            milestone_result = self._execute_milestone(milestone)
            results.append(milestone_result)
            
            if not milestone_result.success:
                self._logger.error(f"Milestone {milestone.id} failed: {milestone_result.error_message}")
                all_success = False
                break  # Stop execution on first failure
            
            # Update plan state
            plan.current_milestone_index += 1
            if milestone_idx < len(plan.milestones) - 1:
                plan.milestones[milestone_idx].status = ExecutionStatus.COMPLETED
        
        self._logger.info(f"Plan execution {'completed' if all_success else 'failed'}")
        return all_success, results

    def _execute_milestone(self, milestone: Milestone) -> MilestoneExecutionResult:
        """
        Execute a single milestone.

        Args:
            milestone: Milestone to execute

        Returns:
            MilestoneExecutionResult with execution status
        """
        self._logger.debug(f"Executing milestone: {milestone.id}")
        
        milestone.status = ExecutionStatus.IN_PROGRESS
        execution_history = []
        completed_count = 0
        
        # Execute each subtask in the milestone
        for subtask_idx, subtask in enumerate(milestone.subtasks):
            self._logger.debug(f"Executing subtask {subtask_idx + 1}/{len(milestone.subtasks)}: {subtask.id}")
            
            subtask_result = self._execute_subtask(subtask)
            execution_history.append(subtask_result)
            
            if subtask_result.success:
                completed_count += 1
                subtask.status = ExecutionStatus.COMPLETED
                milestone.current_subtask_index += 1
            else:
                self._logger.error(f"Subtask {subtask.id} failed: {subtask_result.error_message}")
                subtask.status = ExecutionStatus.FAILED
                subtask.error_message = subtask_result.error_message
                
                # Return failure immediately
                milestone.status = ExecutionStatus.FAILED
                return MilestoneExecutionResult(
                    milestone_id=milestone.id,
                    success=False,
                    timestamp=datetime.now().isoformat(),
                    completed_subtasks=completed_count,
                    failed_subtask_id=subtask.id,
                    error_message=f"Subtask {subtask.id} failed: {subtask_result.error_message}",
                    execution_history=execution_history
                )
        
        # All subtasks completed successfully
        milestone.status = ExecutionStatus.COMPLETED
        return MilestoneExecutionResult(
            milestone_id=milestone.id,
            success=True,
            timestamp=datetime.now().isoformat(),
            completed_subtasks=completed_count,
            execution_history=execution_history
        )

    def _execute_subtask(self, subtask: SubTask) -> ExecutionResult:
        """
        Execute a single subtask.

        Args:
            subtask: SubTask to execute

        Returns:
            ExecutionResult with execution details
        """
        self._logger.debug(f"Executing subtask: {subtask.id} (action: {subtask.action_hint.value})")
        
        subtask.status = ExecutionStatus.IN_PROGRESS
        
        # # Capture screenshot before action
        screenshot_before = self._capture_screenshot(subtask.id)
        
        # self._logger.info(f"Captured screenshot before executing subtask: {subtask}")

        if(subtask.action_hint == ActionType.IDENTIFY):
            # IDENTIFY doesn't execute an action, just returns success
            self._logger.debug(f"IDENTIFY action for {subtask.expected_ui_element}")
            return ExecutionResult(
                subtask_id=subtask.id,
                action_type=subtask.action_hint,
                success=True,
                timestamp=datetime.now().isoformat(),
                screenshot_before=screenshot_before,
                error_message=None
            )

        # Convert SubTask to ADB action
        action_dict = self._convert_subtask_to_action(subtask)

        self._logger.info(f"Converted subtask {subtask.id} to action: {action_dict}")
        
        if not action_dict:
            error_msg = f"Failed to convert subtask {subtask.id} to action"
            self._logger.error(error_msg)
            return ExecutionResult(
                subtask_id=subtask.id,
                action_type=subtask.action_hint,
                success=False,
                timestamp=datetime.now().isoformat(),
                screenshot_before=screenshot_before,
                error_message=error_msg
            )
        
        # Validate action before execution
        is_valid, validation_error = adb.validate_action(action_dict)
        if not is_valid:
            error_msg = f"Invalid action for {subtask.id}: {validation_error}"
            self._logger.error(error_msg)
            return ExecutionResult(
                subtask_id=subtask.id,
                action_type=subtask.action_hint,
                success=False,
                timestamp=datetime.now().isoformat(),
                screenshot_before=screenshot_before,
                error_message=error_msg
            )
        
        # Execute action via ADB
        self._logger.debug(f"Executing ADB action: {action_dict}")
        success = adb.execute_action(action_dict, self._device_id, self._adb_path)
        
        # Add delay after action for UI to update
        time.sleep(5)
        
        # Capture screenshot after action
        screenshot_after = self._capture_screenshot(subtask.id)
        
        if success:
            self._logger.debug(f"Subtask {subtask.id} executed successfully")
        else:
            self._logger.error(f"Subtask {subtask.id} execution failed")
        
        return ExecutionResult(
            subtask_id=subtask.id,
            action_type=subtask.action_hint,
            success=success,
            timestamp=datetime.now().isoformat(),
            screenshot_before=screenshot_before,
            screenshot_after=screenshot_after,
            error_message=None if success else "ADB execution failed"
        )

    def _convert_subtask_to_action(self, subtask: SubTask) -> Optional[Dict[str, Any]]:
        """
        Convert a SubTask with grounded execution data to ADB action dict.
        
        Uses actual coordinates and parameters from the planner instead of placeholders.

        Args:
            subtask: SubTask with grounded execution data (coordinates, element_type, etc.)

        Returns:
            ADB action dictionary or None if conversion fails
        """
        action_hint = subtask.action_hint
        
        # Use grounded coordinates from planner, fallback to center if not available
        target_x = subtask.coordinates[0] if subtask.coordinates else 540
        target_y = subtask.coordinates[1] if subtask.coordinates else 920
        
        try:
            if action_hint == ActionType.CLICK:
                return {
                    "action_type": "click",
                    "target": [target_x, target_y]
                }
            
            elif action_hint == ActionType.LONG_PRESS:
                return {
                    "action_type": "long_press",
                    "target": [target_x, target_y],
                    "duration": 1000  # milliseconds
                }
            
            elif action_hint == ActionType.TYPE:
                # Use input_text from subtask if available, otherwise use element name
                text = subtask.input_text or subtask.expected_ui_element or "text"
                return {
                    "action_type": "input_text",
                    "text": text
                }
            
            elif action_hint == ActionType.SCROLL:
                # Use scroll direction and distance from subtask
                direction = subtask.scroll_direction or "down"
                distance = subtask.scroll_distance or "medium"
                return {
                    "action_type": "swipe",
                    "start": [target_x, target_y],
                    "direction": direction,
                    "distance": distance
                }
            
            elif action_hint == ActionType.DRAG:
                # Calculate end position based on bounding box if available
                if subtask.bounding_box:
                    end_x = subtask.bounding_box.get("x", target_x) + subtask.bounding_box.get("width", 100)
                    end_y = subtask.bounding_box.get("y", target_y)
                else:
                    end_x = target_x + 200
                    end_y = target_y + 200
                
                return {
                    "action_type": "drag",
                    "start": [target_x, target_y],
                    "end": [end_x, end_y],
                    "duration": 500
                }
            
            elif action_hint == ActionType.ENTER:
                return {
                    "action_type": "press_enter"
                }
            
            elif action_hint == ActionType.BACK:
                return {
                    "action_type": "navigate_back"
                }
            
            elif action_hint == ActionType.HOME:
                return {
                    "action_type": "navigate_home"
                }
            
            elif action_hint == ActionType.RECENT:
                return {
                    "action_type": "navigate_recent"
                }
            
            elif action_hint == ActionType.IDENTIFY:
                # IDENTIFY doesn't execute an action, just returns success
                self._logger.debug(f"IDENTIFY action for {subtask.expected_ui_element}")
                return None
            
            elif action_hint == ActionType.WAIT:
                return {
                    "action_type": "wait"
                }
            
            else:
                self._logger.error(f"Unknown action hint: {action_hint}")
                return None
        
        except Exception as e:
            self._logger.error(f"Error converting subtask to action: {e}")
            return None

    def _capture_screenshot(self, subtask_id: str) -> Optional[bytes]:
        """
        Capture a screenshot from the device using ADB screencap.

        Process:
        1. Execute "adb shell screencap -p /sdcard/screen.png" on device
        2. Pull the file from device to local temp location
        3. Read the file as bytes
        4. Clean up the temp file
        5. Return screenshot bytes

        Returns:
            Screenshot bytes or None if capture failed
        """
        try:
            temp_local_path = f"img/screenshot_{subtask_id}.png"
            device_screenshot_path = "/sdcard/gui_agent_screenshot.png"
            
            self._logger.info(f"Capturing screenshot from device {self._device_id}")
            
            # Step 1: Execute screencap on device
            screencap_cmd = ["shell", "screencap", "-p", device_screenshot_path]
            success, output = adb.run_adb_command(
                screencap_cmd,
                device_id=self._device_id,
            )
            
            if not success:
                self._logger.error(f"Failed to execute screencap on device: {output}")
                return None
            
            self._logger.info(f"Screencap executed successfully on device")
            
            # Step 2: Pull the screenshot file from device to local path
            pull_cmd = ["pull", device_screenshot_path, temp_local_path]
            success, output = adb.run_adb_command(
                pull_cmd,
                device_id=self._device_id,
                timeout=60
            )
            
            if not success:
                self._logger.error(f"Failed to pull screenshot from device: {output}")
                return None
            
            self._logger.info(f"Screenshot pulled to {temp_local_path}")
            
            # Step 3: Read the screenshot file as bytes
            try:
                with open(temp_local_path, "rb") as f:
                    screenshot_bytes = f.read()
                
                self._logger.info(f"Screenshot read successfully ({len(screenshot_bytes)} bytes)")
            except Exception as e:
                self._logger.error(f"Failed to read screenshot file: {e}")
                return None
            
            # # Step 4: Clean up the temp file
            # try:
            #     self._logger.info(f"Temp screenshot file cleaned up")
            # except Exception as e:
            #     self._logger.warning(f"Failed to clean up temp screenshot file: {e}")
            
            # Step 5: Clean up the screenshot on device
            # cleanup_cmd = ["shell", "rm", device_screenshot_path]
            # adb.run_adb_command(
            #     cleanup_cmd,
            #     device_id=self._device_id,
            #     adb_path=self._adb_path
            # )
            
            return screenshot_bytes
        
        except Exception as e:
            self._logger.error(f"Unexpected error capturing screenshot: {e}")
            return None

    def get_execution_summary(self, results: List[MilestoneExecutionResult]) -> Dict[str, Any]:
        """
        Get a summary of execution results.

        Args:
            results: List of MilestoneExecutionResult

        Returns:
            Dictionary with execution summary
        """
        total_milestones = len(results)
        completed_milestones = sum(1 for r in results if r.success)
        total_subtasks = sum(r.completed_subtasks for r in results)
        failed_milestone = next((r for r in results if not r.success), None)
        
        summary = {
            "total_milestones": total_milestones,
            "completed_milestones": completed_milestones,
            "total_subtasks": total_subtasks,
            "status": "completed" if completed_milestones == total_milestones else "failed",
            "failed_milestone": failed_milestone.milestone_id if failed_milestone else None,
            "timestamp": datetime.now().isoformat()
        }
        
        return summary
