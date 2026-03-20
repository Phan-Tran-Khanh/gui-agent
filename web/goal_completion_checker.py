"""
Goal Achievement Verification Module

Determines whether a user goal has been achieved by analyzing:
1. Original user goal/prompt
2. Current screenshot from device
3. Parsed UI elements from OmniParser
4. LLM judgment using AssistantAgent

This uses the AssistantAgent to make intelligent decisions about goal completion.
"""

import base64
import logging
from typing import Optional, Dict, Any, List

from mllm.assistant_agent import AssistantAgent


class GoalCompletionChecker:
    """
    Checks if a user goal has been completed by querying the AssistantAgent
    with the user goal, current screenshot, and parsed elements.
    """

    def __init__(self, assistant_agent: AssistantAgent, logger: logging.Logger):
        """
        Initialize the GoalCompletionChecker.

        Args:
            assistant_agent: AssistantAgent for LLM queries
            logger: Logger instance
        """
        self.assistant_agent = assistant_agent
        self.logger = logger

    def check_goal_achieved(
        self,
        user_goal: str,
        current_screenshot: Optional[bytes],
        parsed_elements: List[Dict[str, Any]],
        step_count: int,
        max_steps: int,
    ) -> tuple[bool, str]:
        """
        Check if the user goal has been achieved.

        Sends the user goal, current screenshot, and parsed elements to the LLM
        to make an intelligent judgment about whether the goal is complete.

        Args:
            user_goal: Original user goal/prompt
            current_screenshot: Current screenshot bytes from device
            parsed_elements: List of parsed UI elements from OmniParser
            step_count: Current step number
            max_steps: Maximum steps allowed

        Returns:
            Tuple[bool, str]: (goal_achieved, reasoning)
                - goal_achieved: True if LLM determines goal is complete
                - reasoning: LLM's reasoning/explanation
        """
        try:
            # Build verification prompt
            verification_prompt = self._build_verification_prompt(
                user_goal=user_goal,
                parsed_elements=parsed_elements,
                step_count=step_count,
                max_steps=max_steps,
            )

            self.logger.debug(f"Sending goal verification prompt to AssistantAgent")

            # Query AssistantAgent with screenshot and prompt
            response = self.assistant_agent.query(
                prompt=verification_prompt,
                image_bytes=current_screenshot,
                mime_type="image/png",
            )

            # Parse the response
            goal_achieved, reasoning = self._parse_verification_response(response)

            if goal_achieved:
                self.logger.info(f" Goal ACHIEVED (LLM judgment)")
                self.logger.info(f"  Reasoning: {reasoning}")
            else:
                self.logger.debug(f"Goal not achieved yet")
                self.logger.debug(f"  LLM: {reasoning[:100]}...")

            return goal_achieved, reasoning

        except Exception as e:
            self.logger.error(f"Error checking goal achievement: {e}")
            # On error, assume goal not achieved to continue execution
            return False, f"Error during verification: {str(e)}"

    def _build_verification_prompt(
        self,
        user_goal: str,
        parsed_elements: List[Dict[str, Any]],
        step_count: int,
        max_steps: int,
    ) -> str:
        """
        Build a verification prompt for the AssistantAgent.

        Args:
            user_goal: Original user goal
            parsed_elements: List of parsed UI elements
            step_count: Current step number
            max_steps: Maximum steps allowed

        Returns:
            Formatted prompt string
        """
        # Format elements for inclusion in prompt
        elements_description = self._format_elements_for_verification(
            parsed_elements
        )

        prompt = f"""You are a goal completion verifier for a mobile GUI automation agent.

## Original User Goal
{user_goal}

## Current State
- Step: {step_count}/{max_steps}
- Execution Progress: {(step_count/max_steps)*100:.1f}%

## UI Elements Currently Visible on Screen
{elements_description}

## Task
Analyze the current screenshot and the visible UI elements to determine if the original user goal has been ACHIEVED or COMPLETED.

Consider:
1. Is the user in the expected final state or application state?
2. Are the expected elements visible that would indicate successful goal completion?
3. Does the UI state match what would be required to consider the goal "done"?
4. Are there error messages or indicators that the action failed?

IMPORTANT: Respond with ONLY the following format, no additional text:

ACHIEVED: [YES or NO]
CONFIDENCE: [HIGH, MEDIUM, or LOW]
REASONING: [1-2 sentence explanation]

Example responses:
---
ACHIEVED: YES
CONFIDENCE: HIGH
REASONING: The GitHub website is now loaded and visible in the browser with the GitHub logo and navigation menu displayed.
---

---
ACHIEVED: NO
CONFIDENCE: HIGH
REASONING: Still on the Android home screen. The GitHub app icon needs to be tapped to open the app.
---

---
ACHIEVED: NO
CONFIDENCE: MEDIUM
REASONING: The screen shows a loading spinner, which indicates the app is opening. Need to wait for the interface to fully load.
---
"""
        return prompt

    def _format_elements_for_verification(
        self, parsed_elements: List[Dict[str, Any]]
    ) -> str:
        """
        Format parsed elements for the verification prompt.

        Args:
            parsed_elements: List of element dicts from OmniParser

        Returns:
            Formatted string describing visible elements
        """
        if not parsed_elements:
            return "No UI elements detected on screen."

        lines = ["Elements visible on screen:"]
        for idx, element in enumerate(parsed_elements[:15]):  # Limit to top 15 elements
            element_type = element.get("type", "unknown").upper()
            content = element.get("content", "")[:50]
            interactivity = "interactive" if element.get("interactivity") else "non-interactive"

            lines.append(
                f"  [{idx}] {element_type:12s} | {content:50s} | {interactivity}"
            )

        if len(parsed_elements) > 15:
            lines.append(f"  ... and {len(parsed_elements) - 15} more elements")

        return "\n".join(lines)

    def _parse_verification_response(self, response: str) -> tuple[bool, str]:
        """
        Parse the AssistantAgent's verification response.

        Expected format:
        ACHIEVED: [YES or NO]
        CONFIDENCE: [HIGH, MEDIUM, or LOW]
        REASONING: [explanation]

        Args:
            response: Raw response from AssistantAgent

        Returns:
            Tuple[bool, str]: (goal_achieved, reasoning)
        """
        try:
            lines = response.strip().split("\n")

            achieved = False
            confidence = "LOW"
            reasoning = "Unable to parse response"

            for line in lines:
                if line.startswith("ACHIEVED:"):
                    achieved = "YES" in line.upper()
                elif line.startswith("CONFIDENCE:"):
                    confidence = line.split(":", 1)[1].strip()
                elif line.startswith("REASONING:"):
                    reasoning = line.split(":", 1)[1].strip()

            return achieved, reasoning

        except Exception as e:
            self.logger.error(f"Failed to parse verification response: {e}")
            self.logger.debug(f"Response was: {response[:200]}")
            return False, "Failed to parse LLM response"
