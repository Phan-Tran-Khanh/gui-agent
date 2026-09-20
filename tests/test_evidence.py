"""Tests for persisted closed-loop action evidence."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from execution.models import (
    ActionKind,
    GroundedAction,
    Observation,
    ScreenElement,
    TapIntent,
    TransportResult,
    VerificationResult,
)


class ActionEvidenceTests(unittest.TestCase):
    def test_saves_before_after_all_boxes_and_tap_marker(self) -> None:
        """Evidence must preserve raw screens, all boxes, and the actual tap point."""
        try:
            from execution.evidence import save_action_evidence
        except ModuleNotFoundError as error:
            self.fail(f"action evidence module is missing: {error}")

        before = Observation(
            observation_id="before",
            width=100,
            height=200,
            image=Image.new("RGB", (100, 200), "white"),
            elements=[
                ScreenElement(
                    element_id="settings",
                    bounds=(0.2, 0.3, 0.6, 0.5),
                    text="Settings",
                    source="uiautomator",
                    interactive=True,
                ),
                ScreenElement(
                    element_id="context",
                    bounds=(0.7, 0.1, 0.9, 0.2),
                    text="Clock",
                    source="vision",
                ),
            ],
        )
        after = before.model_copy(
            update={
                "observation_id": "after",
                "image": Image.new("RGB", (100, 200), "green"),
            }
        )
        action = GroundedAction(
            kind=ActionKind.TAP,
            element_id="settings",
            point=(40, 80),
            expected_effect="open settings",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            evidence = save_action_evidence(
                temp_dir,
                task_id="task-evidence",
                step_index=1,
                goal="open settings",
                intent=TapIntent(element_id="settings", expected_effect="open settings"),
                action=action,
                transport=TransportResult(success=True),
                verification=VerificationResult(verified=True, goal_achieved=True),
                before=before,
                after=after,
            )

            directory = Path(evidence["directory"])
            for filename in (
                "before.png",
                "before-annotated.png",
                "after.png",
                "after-annotated.png",
                "action.json",
            ):
                self.assertTrue((directory / filename).is_file(), filename)

            manifest = json.loads((directory / "action.json").read_text(encoding="utf-8"))
            self.assertEqual([100, 200], manifest["before"]["dimensions"])
            self.assertEqual(2, len(manifest["before"]["elements"]))
            self.assertEqual([40, 80], manifest["action"]["point"])
            self.assertEqual([40, 80], manifest["action_marker"]["point"])
            self.assertEqual("settings", manifest["action_marker"]["element_id"])

            annotated = Image.open(directory / "before-annotated.png").convert("RGB")
            self.assertNotEqual((255, 255, 255), annotated.getpixel((40, 80)))


if __name__ == "__main__":
    unittest.main()
