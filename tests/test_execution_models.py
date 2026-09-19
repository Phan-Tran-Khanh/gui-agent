"""Contract tests for typed, safe Android action models."""

from __future__ import annotations

import unittest

from PIL import Image
from pydantic import TypeAdapter, ValidationError

from execution.models import (
    ActionIntent,
    ActionKind,
    Observation,
    ScreenElement,
)


ACTION_INTENT_ADAPTER = TypeAdapter(ActionIntent)


class ExecutionModelTests(unittest.TestCase):
    """The production changes these tests catch are unsafe action contracts."""

    def test_tap_intent_requires_an_observation_scoped_target(self) -> None:
        """A missing target ID must not be allowed to reach coordinate resolution."""
        with self.assertRaises(ValidationError):
            ACTION_INTENT_ADAPTER.validate_python(
                {"kind": "TAP", "expected_effect": "open Wi-Fi settings"}
            )

    def test_system_key_rejects_a_key_outside_the_safety_allowlist(self) -> None:
        """A model-invented system key must be rejected before device dispatch."""
        with self.assertRaises(ValidationError):
            ACTION_INTENT_ADAPTER.validate_python(
                {
                    "kind": "SYSTEM_KEY",
                    "key": "POWER",
                    "expected_effect": "turn off the display",
                }
            )

    def test_slider_value_must_stay_inside_the_normalized_range(self) -> None:
        """A slider coordinate must never be created from an unsafe requested value."""
        with self.assertRaises(ValidationError):
            ACTION_INTENT_ADAPTER.validate_python(
                {
                    "kind": "SET_SLIDER",
                    "element_id": "slider:media",
                    "value": 1.01,
                    "expected_effect": "increase media volume",
                }
            )

    def test_edge_swipe_rejects_unknown_edges(self) -> None:
        """An invalid edge must not produce a gesture with unspecified coordinates."""
        with self.assertRaises(ValidationError):
            ACTION_INTENT_ADAPTER.validate_python(
                {
                    "kind": "EDGE_SWIPE",
                    "edge": "CENTER",
                    "extent": 0.5,
                    "expected_effect": "open the notification shade",
                }
            )

    def test_expected_effect_cannot_be_empty(self) -> None:
        """A dispatched action needs a semantic result that Phase 3 can verify."""
        with self.assertRaises(ValidationError):
            ACTION_INTENT_ADAPTER.validate_python(
                {"kind": "BACK", "expected_effect": "   "}
            )

    def test_observation_excludes_the_raw_image_from_serialized_data(self) -> None:
        """Observation telemetry must retain dimensions/elements without serializing pixels."""
        observation = Observation(
            observation_id="observation-1",
            width=1080,
            height=2400,
            image=Image.new("RGB", (1080, 2400)),
            elements=[
                ScreenElement(
                    element_id="wifi-toggle",
                    bounds=(0.10, 0.20, 0.30, 0.30),
                    text="Wi-Fi",
                    role="switch",
                )
            ],
        )

        serialized = observation.model_dump(mode="json")

        self.assertEqual("observation-1", serialized["observation_id"])
        self.assertEqual(1080, serialized["width"])
        self.assertEqual("wifi-toggle", serialized["elements"][0]["element_id"])
        self.assertNotIn("image", serialized)

    def test_valid_tap_intent_uses_the_typed_action_kind(self) -> None:
        """The policy-facing parser must return a typed action rather than text commands."""
        intent = ACTION_INTENT_ADAPTER.validate_python(
            {
                "kind": "TAP",
                "element_id": "wifi-toggle",
                "expected_effect": "toggle Wi-Fi",
            }
        )

        self.assertEqual(ActionKind.TAP, intent.kind)
        self.assertEqual("wifi-toggle", intent.element_id)


if __name__ == "__main__":
    unittest.main()
