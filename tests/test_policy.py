"""Behavioral tests for the structured, safe closed-loop policy."""

from __future__ import annotations

import json
import unittest

from PIL import Image

from execution.models import (
    ActionKind,
    ActionOutcome,
    GroundedAction,
    Observation,
    ScreenElement,
    StepDecision,
    StrategyPlan,
    TapIntent,
    TransportResult,
    VerificationResult,
)
from execution.policy import Policy, PolicyValidationError


def _observation() -> Observation:
    return Observation(
        observation_id="policy-observation",
        width=1000,
        height=2000,
        image=Image.new("RGB", (1000, 2000), "white"),
        device_state={"installed_packages": ["com.android.settings"]},
        elements=[
            ScreenElement(
                element_id="volume-slider",
                bounds=(0.1, 0.4, 0.9, 0.5),
                text="Media volume",
                role="SeekBar",
                source="uiautomator",
                interactive=True,
            ),
            ScreenElement(
                element_id="uncertain-volume-icon",
                bounds=(0.8, 0.1, 0.9, 0.2),
                text="Volume",
                role="icon",
                source="vision",
                interactive=False,
                requires_inspection=True,
            ),
        ],
    )


def _tap_payload(**action_overrides: object) -> dict[str, object]:
    action: dict[str, object] = {
        "kind": "TAP",
        "element_id": "volume-slider",
        "expected_effect": "open the media volume control",
    }
    action.update(action_overrides)
    return {
        "action": action,
        "target_evidence": "The current native slider is labelled Media volume.",
        "confidence": 0.9,
        "alternate_element_ids": [],
    }


class PolicyTests(unittest.TestCase):
    """These tests catch model-output validation and fallback-order regressions."""

    def test_raw_coordinates_are_rejected_before_the_resolver_can_receive_them(self) -> None:
        """Adding x/y fields must not turn a model response into an ungrounded tap."""
        policy = Policy(
            decision_provider=lambda _: _tap_payload(x=500, y=900),
        )

        with self.assertRaises(PolicyValidationError):
            policy.decide(policy.plan("increase media volume", _observation()), _observation(), [])

    def test_unknown_primary_or_alternate_element_ids_are_rejected(self) -> None:
        """A response may only target IDs present in the current observation."""
        policy = Policy(
            decision_provider=lambda _: {
                **_tap_payload(element_id="invented-target"),
                "alternate_element_ids": ["also-invented"],
            },
        )

        with self.assertRaises(PolicyValidationError):
            policy.decide(policy.plan("increase media volume", _observation()), _observation(), [])

    def test_invented_open_app_package_is_rejected_against_the_observed_registry(self) -> None:
        """A policy must not send a model-invented package toward ADB dispatch."""
        policy = Policy(
            decision_provider=lambda _: {
                "action": {
                    "kind": "OPEN_APP",
                    "package": "com.example.invented",
                    "expected_effect": "open a settings screen",
                },
                "target_evidence": "The model guessed a package name.",
                "confidence": 0.7,
                "alternate_element_ids": [],
            }
        )

        with self.assertRaises(PolicyValidationError):
            policy.decide(policy.plan("open settings", _observation()), _observation(), [])

    def test_missing_expected_effect_is_rejected(self) -> None:
        """Every policy action needs a semantic effect for the verifier to check."""
        policy = Policy(
            decision_provider=lambda _: _tap_payload(expected_effect=""),
        )

        with self.assertRaises(PolicyValidationError):
            policy.decide(policy.plan("increase media volume", _observation()), _observation(), [])

    def test_multi_action_response_is_rejected(self) -> None:
        """A policy response must contain one action, never an implicit batch."""
        policy = Policy(
            decision_provider=lambda _: {
                "actions": [_tap_payload()["action"], _tap_payload()["action"]],
                "target_evidence": "Two actions are unsafe in one decision.",
                "confidence": 0.9,
                "alternate_element_ids": [],
            }
        )

        with self.assertRaises(PolicyValidationError):
            policy.decide(policy.plan("increase media volume", _observation()), _observation(), [])

    def test_volume_plan_uses_gui_routes_before_an_allowlisted_system_fallback(self) -> None:
        """Hardware volume keys remain a fallback after visible GUI routes fail."""
        policy = Policy()
        observation = _observation()

        plan = policy.plan("increase media volume", observation)
        fallback = policy.system_fallback("increase media volume", observation)

        self.assertGreaterEqual(len(plan.routes), 2)
        self.assertTrue(all(route for route in plan.routes))
        self.assertTrue(
            all("system" not in milestone.casefold() for route in plan.routes for milestone in route)
        )
        self.assertIsNotNone(fallback)
        self.assertEqual(ActionKind.SYSTEM_KEY, fallback.intent.kind)
        self.assertEqual("VOLUME_UP", fallback.intent.key)

    def test_system_key_from_a_model_is_rejected_until_the_controller_allows_fallback(self) -> None:
        """A model cannot bypass GUI-route exhaustion by requesting a hardware key."""
        policy = Policy(
            decision_provider=lambda _: {
                "action": {
                    "kind": "SYSTEM_KEY",
                    "key": "VOLUME_UP",
                    "expected_effect": "increase media volume",
                },
                "target_evidence": "A system key is requested.",
                "confidence": 0.8,
                "alternate_element_ids": [],
            }
        )
        observation = _observation()
        plan = policy.plan("increase media volume", observation)

        with self.assertRaises(PolicyValidationError):
            policy.decide(plan, observation, [])

        decision = policy.decide(plan, observation, [], allow_system_fallback=True)
        self.assertEqual(ActionKind.SYSTEM_KEY, decision.intent.kind)

    def test_disputed_or_vision_only_icon_is_rewritten_to_inspection(self) -> None:
        """An uncertain icon must be re-observed before a policy can interact with it."""
        policy = Policy(
            decision_provider=lambda _: _tap_payload(
                element_id="uncertain-volume-icon",
                expected_effect="open the volume controls",
            )
        )
        observation = _observation()

        decision = policy.decide(policy.plan("increase media volume", observation), observation, [])

        self.assertEqual(ActionKind.INSPECT_REGION, decision.intent.kind)
        self.assertEqual("uncertain-volume-icon", decision.intent.element_id)
        self.assertIsNotNone(decision.deferred_intent)
        self.assertEqual(ActionKind.TAP, decision.deferred_intent.kind)
        self.assertEqual("uncertain-volume-icon", decision.deferred_intent.element_id)

    def test_open_settings_prefers_the_interactive_native_settings_target(self) -> None:
        """An obvious localized Settings control must beat unrelated vision labels."""
        observation = Observation(
            observation_id="launcher-settings",
            width=720,
            height=1600,
            image=Image.new("RGB", (720, 1600), "white"),
            elements=[
                ScreenElement(
                    element_id="native-settings",
                    bounds=(0.5, 0.6925, 0.7389, 0.815),
                    text="Cài đặt",
                    role="TextView",
                    source="uiautomator",
                    interactive=True,
                    metadata={"content_description": "Cài đặt có 1 thông báo"},
                ),
                ScreenElement(
                    element_id="wrong-vision-icon",
                    bounds=(0.3, 0.3, 0.45, 0.4),
                    text="A library or library-related application.",
                    role="icon",
                    source="vision",
                    requires_inspection=True,
                ),
            ],
        )
        provider_calls: list[dict[str, object]] = []
        policy = Policy(
            decision_provider=lambda context: provider_calls.append(context)
            or {
                "action": {
                    "kind": "INSPECT_REGION",
                    "element_id": "wrong-vision-icon",
                    "expected_effect": "inspect the unrelated icon",
                },
                "target_evidence": "wrong vision target",
                "confidence": 0.5,
                "alternate_element_ids": [],
            }
        )

        plan = policy.plan("Open the Settings app", observation)
        decision = policy.decide(plan, observation, [], route_index=0, milestone_index=0)

        self.assertEqual(ActionKind.TAP, decision.intent.kind)
        self.assertEqual("native-settings", decision.intent.element_id)
        self.assertIn("native", decision.target_evidence.casefold())
        self.assertEqual([], provider_calls)

    def test_typed_step_decision_provider_is_accepted_at_the_policy_boundary(self) -> None:
        """A provider advertised as returning StepDecision must not be rejected as a raw payload."""
        typed_decision = StepDecision(
            intent=TapIntent(
                element_id="volume-slider",
                expected_effect="open the media volume control",
            ),
            target_evidence="The native Media volume slider is visible.",
            confidence=0.9,
        )
        policy = Policy(decision_provider=lambda _: typed_decision)
        observation = _observation()

        decision = policy.decide(policy.plan("increase media volume", observation), observation, [])

        self.assertEqual(ActionKind.TAP, decision.intent.kind)
        self.assertEqual("volume-slider", decision.intent.element_id)

    def test_inspection_rewrite_still_rejects_an_unknown_alternate_target(self) -> None:
        """Inspection gating must not skip validation of every alternate ID in the response."""
        policy = Policy(
            decision_provider=lambda _: {
                **_tap_payload(element_id="uncertain-volume-icon"),
                "alternate_element_ids": ["invented-alternate"],
            }
        )
        observation = _observation()

        with self.assertRaises(PolicyValidationError):
            policy.decide(policy.plan("increase media volume", observation), observation, [])

    def test_noninteractive_alternate_target_is_rejected_before_recovery(self) -> None:
        """An alternate must be dispatchable in the current observation, not merely known."""
        policy = Policy(
            decision_provider=lambda _: {
                **_tap_payload(),
                "alternate_element_ids": ["uncertain-volume-icon"],
            }
        )
        observation = _observation()

        with self.assertRaises(PolicyValidationError):
            policy.decide(policy.plan("increase media volume", observation), observation, [])

    def test_default_policy_uses_set_slider_for_android_seekbar(self) -> None:
        """Android's native SeekBar role must map to a typed slider action, not a tap."""
        observation = Observation(
            observation_id="seekbar-observation",
            width=1000,
            height=2000,
            elements=[
                ScreenElement(
                    element_id="media-seekbar",
                    bounds=(0.1, 0.4, 0.9, 0.5),
                    text="Media volume",
                    role="SeekBar",
                    source="uiautomator",
                    interactive=True,
                    metadata={"normalized_value": 0.9},
                )
            ],
        )
        policy = Policy()

        decision = policy.decide(policy.plan("increase media volume", observation), observation, [])

        self.assertEqual(ActionKind.SET_SLIDER, decision.intent.kind)
        self.assertEqual(1.0, decision.intent.value)

    def test_default_policy_inspects_a_slider_when_its_current_value_is_unknown(self) -> None:
        """Relative volume goals must not turn a hard-coded absolute slider value into a reversal."""
        observation = Observation(
            observation_id="unknown-seekbar-observation",
            width=1000,
            height=2000,
            elements=[
                ScreenElement(
                    element_id="media-seekbar",
                    bounds=(0.1, 0.4, 0.9, 0.5),
                    text="Media volume",
                    role="SeekBar",
                    source="uiautomator",
                    interactive=True,
                )
            ],
        )
        policy = Policy()

        decision = policy.decide(policy.plan("increase media volume", observation), observation, [])

        self.assertEqual(ActionKind.INSPECT_REGION, decision.intent.kind)

    def test_system_fallback_requires_an_explicit_relative_volume_operation(self) -> None:
        """Informational or navigation-only volume goals must never default to VOLUME_UP."""
        policy = Policy()
        observation = _observation()

        self.assertIsNone(policy.system_fallback("open volume settings", observation))
        self.assertIsNone(policy.system_fallback("set volume to 25 percent", observation))
        self.assertIsNone(policy.system_fallback("check media volume", observation))

    def test_conflicting_volume_operations_fail_closed(self) -> None:
        """A mixed directional request must not be collapsed into a destructive key fallback."""
        fallback = Policy().system_fallback("increase then mute media volume", _observation())

        self.assertIsNone(fallback)

    def test_quieter_volume_goal_uses_the_down_hardware_fallback(self) -> None:
        """A relative 'quieter' goal must not fall through to the upward key."""
        fallback = Policy().system_fallback("make media volume quieter", _observation())

        self.assertIsNotNone(fallback)
        self.assertEqual("VOLUME_DOWN", fallback.intent.key)

    def test_quieter_volume_goal_lowers_a_known_slider_value(self) -> None:
        """The same 'quieter' operation must lower, rather than raise, native slider state."""
        observation = Observation(
            observation_id="quieter-seekbar-observation",
            width=1000,
            height=2000,
            elements=[
                ScreenElement(
                    element_id="media-seekbar",
                    bounds=(0.1, 0.4, 0.9, 0.5),
                    text="Media volume",
                    role="SeekBar",
                    source="uiautomator",
                    interactive=True,
                    metadata={"normalized_value": 0.5},
                )
            ],
        )
        policy = Policy()

        decision = policy.decide(
            policy.plan("make media volume quieter", observation), observation, []
        )

        self.assertEqual(ActionKind.SET_SLIDER, decision.intent.kind)
        self.assertEqual(0.4, decision.intent.value)

    def test_model_context_is_json_safe_image_free_and_history_bounded(self) -> None:
        """The model boundary must receive only bounded serializable controller state."""
        captured: list[dict[str, object]] = []
        policy = Policy(
            decision_provider=lambda context: captured.append(context) or _tap_payload(),
            history_limit=2,
        )
        observation = _observation()
        outcome = ActionOutcome(
            action=GroundedAction(
                kind=ActionKind.TAP,
                expected_effect="open the volume control",
                element_id="volume-slider",
                point=(500, 900),
            ),
            transport=TransportResult(success=True),
            verification=VerificationResult(verified=True, confidence=0.9),
        )

        policy.decide(policy.plan("increase media volume", observation), observation, [outcome] * 3)

        self.assertEqual(1, len(captured))
        context = captured[0]
        self.assertEqual(2, len(context["history"]))
        self.assertNotIn("image", context["observation"])
        self.assertNotIn("bounds", context["observation"]["elements"][0])
        json.dumps(context)

    def test_model_context_exposes_only_the_active_route_and_milestone(self) -> None:
        """A policy provider must decide against the controller's current GUI milestone."""
        captured: list[dict[str, object]] = []
        policy = Policy(decision_provider=lambda context: captured.append(context) or _tap_payload())
        plan = StrategyPlan(
            goal="increase media volume",
            routes=[
                ["Open Quick Settings", "Adjust the visible media volume slider"],
                ["Open Settings", "Open Sound and vibration"],
            ],
        )

        policy.decide(plan, _observation(), [], route_index=1, milestone_index=0)

        self.assertEqual(1, captured[0]["active_route_index"])
        self.assertEqual(
            ["Open Settings", "Open Sound and vibration"], captured[0]["active_route"]
        )
        self.assertEqual(0, captured[0]["active_milestone_index"])
        self.assertEqual("Open Settings", captured[0]["active_milestone"])

    def test_invalid_active_route_or_milestone_is_rejected(self) -> None:
        """A controller cannot select an unplanned GUI route or milestone by index."""
        policy = Policy()
        plan = StrategyPlan(goal="increase media volume", routes=[["Open Quick Settings"]])

        with self.assertRaises(PolicyValidationError):
            policy.decide(plan, _observation(), [], route_index=1)
        with self.assertRaises(PolicyValidationError):
            policy.decide(plan, _observation(), [], milestone_index=1)


if __name__ == "__main__":
    unittest.main()
