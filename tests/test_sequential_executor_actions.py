"""Regression tests for legacy action grounding."""

from __future__ import annotations

import logging
import unittest

from app.backend.sequential_executor import SequentialExecutor
from config import Config
from mllm import ActionType, SubTask


class SequentialExecutorActionTests(unittest.TestCase):
    def test_scroll_uses_bounding_box_when_planner_omits_coordinates(self) -> None:
        logger = logging.getLogger("test.sequential_actions")
        logger.disabled = True
        executor = SequentialExecutor(
            device_id="emulator-5554",
            omniparser_client=None,
            config=Config(mock_mode=True),
            logger=logger,
            max_steps=1,
            step_delay_sec=0.0,
            mock=True,
        )
        subtask = SubTask(
            id="scroll-hour-wheel",
            description="Scroll the hour picker",
            action_hint=ActionType.SCROLL,
            expected_ui_element="hour picker",
            bounding_box={"x": 120, "y": 224, "width": 239, "height": 320},
            scroll_direction="up",
            scroll_distance="medium",
        )

        action = executor._subtask_to_action(subtask, screen_size=(720, 1600))

        self.assertEqual("swipe", action["action_type"])
        self.assertEqual([239, 384], action["start"])
        self.assertEqual("up", action["direction"])

    def test_time_picker_scroll_fallback_starts_inside_wheel(self) -> None:
        logger = logging.getLogger("test.sequential_actions.fallback")
        logger.disabled = True
        executor = SequentialExecutor(
            device_id="emulator-5554",
            omniparser_client=None,
            config=Config(mock_mode=True),
            logger=logger,
            max_steps=1,
            step_delay_sec=0.0,
            mock=True,
        )
        subtask = SubTask(
            id="scroll-hour-wheel",
            description="Scroll the hour wheel to the requested time",
            action_hint=ActionType.SCROLL,
            expected_ui_element="hour wheel",
            scroll_direction="up",
            scroll_distance="medium",
        )

        action = executor._subtask_to_action(subtask, screen_size=(720, 1600))

        self.assertEqual([240, 400], action["start"])

    def test_generic_scroll_uses_numeric_picker_element_when_available(self) -> None:
        logger = logging.getLogger("test.sequential_actions.numeric")
        logger.disabled = True
        executor = SequentialExecutor(
            device_id="emulator-5554",
            omniparser_client=None,
            config=Config(mock_mode=True),
            logger=logger,
            max_steps=1,
            step_delay_sec=0.0,
            mock=True,
        )
        subtask = SubTask(
            id="scroll-picker",
            description="Scroll to the requested value",
            action_hint=ActionType.SCROLL,
            expected_ui_element="Screen scrolling",
            scroll_direction="up",
            scroll_distance="medium",
        )

        action = executor._subtask_to_action(
            subtask,
            parsed_elements=[
                {"content": "22", "bbox": [0.30, 0.14, 0.37, 0.18]},
                {"content": "00", "bbox": [0.30, 0.22, 0.37, 0.28]},
                {"content": "01", "bbox": [0.30, 0.28, 0.37, 0.34]},
                {"content": "57", "bbox": [0.61, 0.22, 0.68, 0.28]},
            ],
            screen_size=(720, 1600),
        )

        self.assertEqual([241, 400], action["start"])


if __name__ == "__main__":
    unittest.main()
