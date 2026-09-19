"""Behavioral tests for independent before/after action verification."""

from __future__ import annotations

import unittest

from PIL import Image

from execution.models import ActionKind, FailureClass, GroundedAction, Observation, ScreenElement
from execution.verifier import (
    SemanticVerdict,
    Verifier,
    compare_observations,
    observation_fingerprint,
)


def _observation(
    observation_id: str,
    *,
    color: str,
    tree_text: str,
    element_text: str,
    include_capture_data: bool = True,
) -> Observation:
    state = (
        {
            "ui_hierarchy_xml": (
                '<hierarchy><node class="android.widget.TextView" '
                f'text="{tree_text}" resource-id="" bounds="[0,0][100,100]" />'
                "</hierarchy>"
            )
        }
        if include_capture_data
        else {}
    )
    return Observation(
        observation_id=observation_id,
        width=100,
        height=100,
        image=Image.new("RGB", (100, 100), color) if include_capture_data else None,
        device_state=state,
        elements=[
            ScreenElement(
                element_id="wifi-toggle",
                bounds=(0.1, 0.1, 0.4, 0.4),
                text=element_text,
                role="Switch",
                source="uiautomator",
                interactive=True,
            )
        ],
    )


def _action(expected_effect: str = "Wi-Fi enabled") -> GroundedAction:
    return GroundedAction(
        kind=ActionKind.TAP,
        expected_effect=expected_effect,
        element_id="wifi-toggle",
        point=(25, 25),
    )


class VerifierTests(unittest.TestCase):
    """These tests catch success claims that lack semantic before/after evidence."""

    def test_transport_success_without_expected_change_is_failure(self) -> None:
        """An unchanged screen and UI tree cannot verify an ADB-successful tap."""
        before = _observation(
            "before", color="white", tree_text="Wi-Fi disabled", element_text="Wi-Fi disabled"
        )
        after = _observation(
            "after", color="white", tree_text="Wi-Fi disabled", element_text="Wi-Fi disabled"
        )

        result = Verifier(goal="Wi-Fi enabled").verify(before, _action(), after)

        self.assertFalse(result.verified)
        self.assertEqual(FailureClass.NO_EFFECT, result.failure_class)
        self.assertIn("screenshot_changed=False", result.evidence)
        self.assertIn("tree_changed=False", result.evidence)

    def test_changed_state_without_the_expected_effect_is_wrong_effect(self) -> None:
        """A screen change alone cannot be mistaken for the requested semantic result."""
        before = _observation(
            "before", color="white", tree_text="Wi-Fi disabled", element_text="Wi-Fi disabled"
        )
        after = _observation(
            "after", color="blue", tree_text="Bluetooth enabled", element_text="Bluetooth enabled"
        )

        result = Verifier(goal="Wi-Fi enabled").verify(before, _action(), after)

        self.assertFalse(result.verified)
        self.assertEqual(FailureClass.WRONG_EFFECT, result.failure_class)
        self.assertIn("screenshot_changed=True", result.evidence)
        self.assertIn("tree_changed=True", result.evidence)

    def test_new_expected_effect_is_verified_and_marks_the_goal_complete(self) -> None:
        """A new semantic effect visible in post-action state is valid completion evidence."""
        before = _observation(
            "before", color="white", tree_text="Wi-Fi disabled", element_text="Wi-Fi disabled"
        )
        after = _observation(
            "after", color="green", tree_text="Wi-Fi enabled", element_text="Wi-Fi enabled"
        )

        result = Verifier(
            goal="Wi-Fi enabled",
            semantic_judge=lambda *_: SemanticVerdict(
                matched=True,
                goal_achieved=True,
                reason="The independent check confirmed the new checked state.",
                confidence=0.9,
            ),
        ).verify(before, _action(), after)

        self.assertTrue(result.verified)
        self.assertTrue(result.goal_achieved)
        self.assertIsNone(result.failure_class)

    def test_semantic_judge_receives_goal_action_and_both_observations(self) -> None:
        """The independent semantic boundary gets all evidence, not only an image delta."""
        calls: list[object] = []

        def judge(goal, expected_effect, action, before, after, comparison):
            calls.append((goal, expected_effect, action, before, after, comparison))
            return SemanticVerdict(
                matched=True,
                goal_achieved=True,
                reason="The checked state changed as requested.",
                evidence=["semantic judge matched the post-action state"],
                confidence=0.95,
            )

        before = _observation(
            "before", color="white", tree_text="Wi-Fi disabled", element_text="Wi-Fi disabled"
        )
        after = _observation(
            "after", color="green", tree_text="Wi-Fi enabled", element_text="Wi-Fi enabled"
        )

        result = Verifier(goal="enable Wi-Fi", semantic_judge=judge).verify(
            before, _action(), after
        )

        self.assertTrue(result.verified)
        self.assertEqual(1, len(calls))
        goal, effect, action, recorded_before, recorded_after, comparison = calls[0]
        self.assertEqual("enable Wi-Fi", goal)
        self.assertEqual("Wi-Fi enabled", effect)
        self.assertEqual(_action(), action)
        self.assertIs(before, recorded_before)
        self.assertIs(after, recorded_after)
        self.assertTrue(comparison.screenshot_changed)
        self.assertTrue(comparison.tree_changed)

    def test_volatile_observation_ids_do_not_count_as_semantic_change(self) -> None:
        """Parser request IDs must not make an unchanged UI look like a verified effect."""
        before = _observation(
            "request-one", color="white", tree_text="Wi-Fi disabled", element_text="Wi-Fi disabled"
        )
        after = _observation(
            "request-two", color="white", tree_text="Wi-Fi disabled", element_text="Wi-Fi disabled"
        )

        result = Verifier(goal="Wi-Fi enabled").verify(before, _action(), after)

        self.assertEqual(FailureClass.NO_EFFECT, result.failure_class)

    def test_unavailable_capture_data_is_recorded_in_comparison_evidence(self) -> None:
        """Missing screenshot or hierarchy data must be explicit, never silently treated as equal."""
        before = _observation(
            "before", color="white", tree_text="", element_text="Wi-Fi disabled", include_capture_data=False
        )
        after = _observation(
            "after", color="white", tree_text="", element_text="Bluetooth enabled", include_capture_data=False
        )

        result = Verifier(goal="Wi-Fi enabled").verify(before, _action(), after)

        self.assertFalse(result.verified)
        self.assertIn("screenshot_changed=unavailable", result.evidence)
        self.assertIn("tree_changed=unavailable", result.evidence)

    def test_negated_expected_effect_is_not_semantic_success(self) -> None:
        """The words in a negated state must not accidentally satisfy a free-text effect."""
        before = _observation(
            "before", color="white", tree_text="Bluetooth disabled", element_text="Bluetooth disabled"
        )
        after = _observation(
            "after", color="blue", tree_text="Not Wi-Fi enabled", element_text="Not Wi-Fi enabled"
        )

        result = Verifier(goal="Wi-Fi enabled").verify(before, _action(), after)

        self.assertFalse(result.verified)
        self.assertEqual(FailureClass.WRONG_EFFECT, result.failure_class)

    def test_free_text_state_words_do_not_self_verify_without_an_independent_judge(self) -> None:
        """A phrase such as 'Wi-Fi enabled: false' cannot be proof of an enabled state."""
        before = _observation(
            "before", color="white", tree_text="Bluetooth disabled", element_text="Bluetooth disabled"
        )
        after = _observation(
            "after", color="blue", tree_text="Wi-Fi enabled: false", element_text="Wi-Fi enabled: false"
        )

        result = Verifier(goal="Wi-Fi enabled").verify(before, _action(), after)

        self.assertFalse(result.verified)
        self.assertEqual(FailureClass.WRONG_EFFECT, result.failure_class)

    def test_checked_native_state_changes_the_tree_and_semantic_fingerprints(self) -> None:
        """A toggled native checked state must be observable even when labels and pixels stay put."""
        def native_state(observation_id: str, checked: str) -> Observation:
            return Observation(
                observation_id=observation_id,
                width=100,
                height=100,
                image=Image.new("RGB", (100, 100), "white"),
                device_state={
                    "ui_hierarchy_xml": (
                        '<hierarchy><node class="android.widget.CheckBox" text="Wi-Fi" '
                        f'checked="{checked}" selected="false" bounds="[0,0][100,100]" />'
                        "</hierarchy>"
                    )
                },
                elements=[
                    ScreenElement(
                        element_id="wifi-toggle",
                        bounds=(0.1, 0.1, 0.4, 0.4),
                        text="Wi-Fi",
                        role="CheckBox",
                        source="uiautomator",
                        interactive=True,
                        metadata={"checked": checked == "true"},
                    )
                ],
            )

        before = native_state("before", "false")
        after = native_state("after", "true")
        comparison = compare_observations(before, after)

        self.assertTrue(comparison.tree_changed)
        self.assertTrue(comparison.semantic_changed)
        self.assertNotEqual(observation_fingerprint(before), observation_fingerprint(after))


if __name__ == "__main__":
    unittest.main()
