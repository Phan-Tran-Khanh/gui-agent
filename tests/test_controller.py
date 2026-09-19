"""Behavioral recovery tests for the verified Android closed-loop controller."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Sequence
import unittest

from PIL import Image

from execution.controller import ClosedLoopController
from execution.models import (
    ActionKind,
    FailureClass,
    GroundedAction,
    InspectRegionIntent,
    Observation,
    ScreenElement,
    StepDecision,
    StrategyPlan,
    SystemKeyIntent,
    TapIntent,
    TransportResult,
    VerificationResult,
)
from execution.policy import Policy
from execution.verifier import Verifier


def _observation(
    observation_id: str,
    *,
    color: str = "white",
    tree_text: str = "screen",
    ambiguous: bool = False,
) -> Observation:
    return Observation(
        observation_id=observation_id,
        width=100,
        height=200,
        image=Image.new("RGB", (100, 200), color),
        device_state={
            "ui_hierarchy_xml": (
                '<hierarchy><node class="android.widget.TextView" '
                f'text="{tree_text}" bounds="[0,0][100,200]" />'
                "</hierarchy>"
            )
        },
        elements=[
            ScreenElement(
                element_id="primary",
                bounds=(0.1, 0.1, 0.4, 0.3),
                text="Primary",
                role="Button",
                source="uiautomator",
                interactive=not ambiguous,
                requires_inspection=ambiguous,
            ),
            ScreenElement(
                element_id="alternate",
                bounds=(0.5, 0.1, 0.8, 0.3),
                text="Alternate",
                role="Button",
                source="uiautomator",
                interactive=True,
            ),
            ScreenElement(
                element_id="secondary",
                bounds=(0.1, 0.5, 0.4, 0.7),
                text="Secondary",
                role="Button",
                source="uiautomator",
                interactive=True,
            ),
        ],
    )


def _volume_route_observation(
    observation_id: str,
    *,
    include_slider: bool = False,
) -> Observation:
    """A stable screen with controls for both built-in volume GUI routes."""

    elements = [
        ScreenElement(
            element_id="quick-settings",
            bounds=(0.1, 0.1, 0.4, 0.3),
            text="Quick Settings",
            role="Button",
            source="uiautomator",
            interactive=True,
        ),
        ScreenElement(
            element_id="settings",
            bounds=(0.5, 0.1, 0.8, 0.3),
            text="Settings",
            role="Button",
            source="uiautomator",
            interactive=True,
        ),
        ScreenElement(
            element_id="unrelated",
            bounds=(0.1, 0.5, 0.4, 0.7),
            text="Unrelated control",
            role="Button",
            source="uiautomator",
            interactive=True,
        ),
    ]
    if include_slider:
        elements.append(
            ScreenElement(
                element_id="media-slider",
                bounds=(0.1, 0.75, 0.9, 0.85),
                text="Media volume",
                role="SeekBar",
                source="uiautomator",
                interactive=True,
                metadata={"normalized_value": 0.5},
            )
        )
    return Observation(
        observation_id=observation_id,
        width=100,
        height=200,
        image=Image.new("RGB", (100, 200), "white"),
        device_state={
            "ui_hierarchy_xml": (
                '<hierarchy><node class="android.widget.TextView" '
                'text="Volume controls" bounds="[0,0][100,200]" />'
                "</hierarchy>"
            )
        },
        elements=elements,
    )


def _decision(
    element_id: str,
    *,
    alternates: Sequence[str] = (),
    expected_effect: str = "goal complete",
) -> StepDecision:
    return StepDecision(
        intent=TapIntent(element_id=element_id, expected_effect=expected_effect),
        target_evidence=f"{element_id} is visible in the current observation.",
        confidence=0.9,
        alternate_element_ids=list(alternates),
    )


def _inspection_decision() -> StepDecision:
    return StepDecision(
        intent=InspectRegionIntent(
            element_id="primary",
            expected_effect="inspect the disputed primary control",
        ),
        target_evidence="The primary control is ambiguous.",
        confidence=0.6,
    )


class QueuedObserver:
    """A real async observation boundary with deterministic queued evidence."""

    def __init__(self, observations: Sequence[Observation | Exception]) -> None:
        self._observations = deque(observations)
        self.calls = 0

    async def __call__(self) -> Observation:
        self.calls += 1
        if not self._observations:
            raise AssertionError("controller requested an unexpected observation")
        item = self._observations.popleft()
        if isinstance(item, Exception):
            raise item
        return item


class RecordingDispatcher:
    """Records actual dispatches while returning deterministic ADB transport outcomes."""

    def __init__(self, outcomes: Sequence[TransportResult]) -> None:
        self._outcomes = deque(outcomes)
        self.actions: list[GroundedAction] = []

    def __call__(self, action: GroundedAction) -> TransportResult:
        self.actions.append(action)
        if not self._outcomes:
            raise AssertionError("controller dispatched more actions than expected")
        return self._outcomes.popleft()


class ScriptedPolicy:
    """Small policy fake whose observable decisions exercise the real controller."""

    def __init__(
        self,
        plan: StrategyPlan,
        decisions: Sequence[StepDecision],
        fallback: StepDecision | None = None,
    ) -> None:
        self._plan = plan
        self._decisions = deque(decisions)
        self._fallback = fallback
        self.decide_calls = 0
        self.fallback_calls = 0
        self.route_indices: list[int] = []
        self.milestone_indices: list[int] = []

    def plan(self, goal: str, observation: Observation) -> StrategyPlan:
        self.asserted_goal = goal
        self.asserted_observation = observation
        return self._plan

    def decide(
        self,
        plan: StrategyPlan,
        observation: Observation,
        history: Sequence[object],
        *,
        route_index: int = 0,
        milestone_index: int = 0,
    ) -> StepDecision:
        self.decide_calls += 1
        self.route_indices.append(route_index)
        self.milestone_indices.append(milestone_index)
        if not self._decisions:
            raise AssertionError("controller requested an unexpected policy decision")
        return self._decisions.popleft()

    def system_fallback(self, goal: str, observation: Observation) -> StepDecision | None:
        self.fallback_calls += 1
        return self._fallback


class ScriptedVerifier:
    """Records semantic checks while keeping controller recovery tests deterministic."""

    def __init__(self, results: Sequence[VerificationResult]) -> None:
        self._results = deque(results)
        self.calls: list[tuple[Observation, GroundedAction, Observation]] = []

    def verify(
        self,
        before: Observation,
        action: GroundedAction,
        after: Observation,
    ) -> VerificationResult:
        self.calls.append((before, action, after))
        if not self._results:
            raise AssertionError("controller requested an unexpected verification")
        return self._results.popleft()


def _controller(
    policy: ScriptedPolicy,
    verifier: ScriptedVerifier,
    observer: QueuedObserver,
    dispatcher: RecordingDispatcher,
) -> ClosedLoopController:
    return ClosedLoopController(
        policy=policy,
        verifier=verifier,
        observe=observer,
        dispatch=dispatcher,
        settle_timeout_s=1.0,
        poll_interval_s=0.0,
        max_settle_polls=3,
    )


def _verified(*, goal_achieved: bool) -> VerificationResult:
    return VerificationResult(
        verified=True,
        goal_achieved=goal_achieved,
        evidence=["scripted semantic verifier matched"],
        confidence=0.9,
    )


def _failed() -> VerificationResult:
    return VerificationResult(
        verified=False,
        failure_class=FailureClass.NO_EFFECT,
        reason="no expected effect",
    )


class ClosedLoopControllerTests(unittest.TestCase):
    """These tests catch recovery ordering and false-completion regressions."""

    def test_every_dispatched_action_is_verified(self) -> None:
        """A transport call must always have one semantic before/after verification."""
        before = _observation("before")
        after = _observation("after", color="green", tree_text="complete")
        observer = QueuedObserver([before, before, after, after])
        dispatcher = RecordingDispatcher([TransportResult(success=True)])
        verifier = ScriptedVerifier([_verified(goal_achieved=True)])
        policy = ScriptedPolicy(
            StrategyPlan(goal="goal complete", routes=[["GUI route"]]), [_decision("primary")]
        )

        result = asyncio.run(_controller(policy, verifier, observer, dispatcher).run("goal complete", 3))

        self.assertTrue(result.completed)
        self.assertEqual(1, len(dispatcher.actions))
        self.assertEqual(len(dispatcher.actions), len(verifier.calls))

    def test_ambiguous_target_retries_perception_once_without_dispatching_it(self) -> None:
        """Inspection is internal; the controller refreshes perception once before acting."""
        ambiguous = _observation("ambiguous", ambiguous=True)
        clear = _observation("clear", color="yellow", tree_text="clear target")
        after = _observation("after", color="green", tree_text="complete")
        observer = QueuedObserver([ambiguous, ambiguous, clear, clear, after, after])
        dispatcher = RecordingDispatcher([TransportResult(success=True)])
        verifier = ScriptedVerifier([_verified(goal_achieved=True)])
        policy = ScriptedPolicy(
            StrategyPlan(goal="goal complete", routes=[["GUI route"]]),
            [_inspection_decision(), _decision("primary")],
        )

        result = asyncio.run(_controller(policy, verifier, observer, dispatcher).run("goal complete", 3))

        self.assertTrue(result.completed)
        self.assertEqual(["primary"], [action.element_id for action in dispatcher.actions])
        self.assertEqual(2, policy.decide_calls)
        self.assertEqual(1, len(verifier.calls))

    def test_persistent_inspection_uses_an_evidenced_interactive_alternate(self) -> None:
        """After one re-perception, persistent ambiguity may recover only through its named alternate."""
        ambiguous = _observation("ambiguous", ambiguous=True)
        after = _observation("after", color="green", tree_text="complete")
        observer = QueuedObserver([ambiguous, ambiguous, ambiguous, ambiguous, after, after])
        dispatcher = RecordingDispatcher([TransportResult(success=True)])
        verifier = ScriptedVerifier([_verified(goal_achieved=True)])
        policy = Policy(
            decision_provider=lambda _: {
                "action": {
                    "kind": "TAP",
                    "element_id": "primary",
                    "expected_effect": "goal complete",
                },
                "target_evidence": "The primary control is plausible but disputed.",
                "confidence": 0.8,
                "alternate_element_ids": ["alternate"],
            }
        )

        result = asyncio.run(_controller(policy, verifier, observer, dispatcher).run("goal complete", 1))

        self.assertTrue(result.completed)
        self.assertEqual(["alternate"], [action.element_id for action in dispatcher.actions])
        self.assertEqual(1, len(verifier.calls))
        self.assertEqual(2, len([outcome for outcome in result.outcomes if outcome.action and outcome.action.internal]))

    def test_failed_primary_target_uses_one_alternate(self) -> None:
        """A failed primary control may use only the first evidenced alternate target."""
        before = _observation("before")
        after_primary = _observation("after-primary", color="yellow", tree_text="unchanged goal")
        after_alternate = _observation("after-alternate", color="green", tree_text="complete")
        observer = QueuedObserver(
            [before, before, after_primary, after_primary, after_alternate, after_alternate]
        )
        dispatcher = RecordingDispatcher([TransportResult(success=True), TransportResult(success=True)])
        verifier = ScriptedVerifier([_failed(), _verified(goal_achieved=True)])
        policy = ScriptedPolicy(
            StrategyPlan(goal="goal complete", routes=[["GUI route"]]),
            [_decision("primary", alternates=["alternate", "secondary"])]
        )

        result = asyncio.run(_controller(policy, verifier, observer, dispatcher).run("goal complete", 3))

        self.assertTrue(result.completed)
        self.assertEqual(
            ["primary", "alternate"], [action.element_id for action in dispatcher.actions]
        )
        self.assertEqual(1, policy.decide_calls)

    def test_failed_route_switches_to_next_gui_route(self) -> None:
        """After its recovery budget is spent, a failed GUI route advances to the next route."""
        before = _observation("before")
        after_primary = _observation("after-primary", color="yellow", tree_text="route one failed")
        after_secondary = _observation("after-secondary", color="green", tree_text="complete")
        observer = QueuedObserver(
            [before, before, after_primary, after_primary, after_secondary, after_secondary]
        )
        dispatcher = RecordingDispatcher([TransportResult(success=True), TransportResult(success=True)])
        verifier = ScriptedVerifier([_failed(), _verified(goal_achieved=True)])
        policy = ScriptedPolicy(
            StrategyPlan(goal="goal complete", routes=[["first GUI route"], ["second GUI route"]]),
            [_decision("primary"), _decision("secondary")],
        )

        result = asyncio.run(_controller(policy, verifier, observer, dispatcher).run("goal complete", 3))

        self.assertTrue(result.completed)
        self.assertEqual(
            ["primary", "secondary"], [action.element_id for action in dispatcher.actions]
        )

    def test_system_key_is_used_only_after_gui_routes_fail(self) -> None:
        """A hardware key must follow, never replace, failed visible GUI routes."""
        before = _observation("before")
        after_primary = _observation("after-primary", color="yellow", tree_text="first route failed")
        after_secondary = _observation("after-secondary", color="orange", tree_text="second route failed")
        after_fallback = _observation("after-fallback", color="green", tree_text="complete")
        observer = QueuedObserver(
            [
                before,
                before,
                after_primary,
                after_primary,
                after_secondary,
                after_secondary,
                after_fallback,
                after_fallback,
            ]
        )
        dispatcher = RecordingDispatcher(
            [TransportResult(success=True), TransportResult(success=True), TransportResult(success=True)]
        )
        verifier = ScriptedVerifier([_failed(), _failed(), _verified(goal_achieved=True)])
        fallback = StepDecision(
            intent=SystemKeyIntent(key="VOLUME_UP", expected_effect="goal complete"),
            target_evidence="All visible routes failed.",
            confidence=0.5,
        )
        policy = ScriptedPolicy(
            StrategyPlan(goal="goal complete", routes=[["first GUI route"], ["second GUI route"]]),
            [_decision("primary"), _decision("secondary")],
            fallback=fallback,
        )

        result = asyncio.run(_controller(policy, verifier, observer, dispatcher).run("goal complete", 4))

        self.assertTrue(result.completed)
        self.assertEqual(
            [ActionKind.TAP, ActionKind.TAP, ActionKind.SYSTEM_KEY],
            [action.kind for action in dispatcher.actions],
        )
        self.assertEqual(1, policy.fallback_calls)

    def test_real_policy_attempts_distinct_gui_routes_before_system_fallback(self) -> None:
        """Active route state must prevent an unrelated repeat from unlocking a hardware key."""
        stable = _volume_route_observation("volume-routes")
        observer = QueuedObserver([stable, stable, stable, stable, stable, stable, stable, stable])
        dispatcher = RecordingDispatcher(
            [TransportResult(success=True), TransportResult(success=True), TransportResult(success=True)]
        )
        verifier = ScriptedVerifier([_failed(), _failed(), _verified(goal_achieved=True)])

        result = asyncio.run(
            _controller(Policy(), verifier, observer, dispatcher).run("increase media volume", 3)
        )

        self.assertTrue(result.completed)
        self.assertEqual(
            ["quick-settings", "settings", None],
            [action.element_id for action in dispatcher.actions],
        )
        self.assertEqual(
            [ActionKind.TAP, ActionKind.TAP, ActionKind.SYSTEM_KEY],
            [action.kind for action in dispatcher.actions],
        )
        self.assertEqual([0, 1, 2], [outcome.route_index for outcome in result.outcomes])

    def test_real_policy_advances_to_the_next_route_milestone_after_verified_progress(self) -> None:
        """A verified nonterminal action advances from opening controls to adjusting the slider."""
        stable = _volume_route_observation("volume-milestones", include_slider=True)
        observer = QueuedObserver([stable, stable, stable, stable, stable, stable])
        dispatcher = RecordingDispatcher([TransportResult(success=True), TransportResult(success=True)])
        verifier = ScriptedVerifier([_verified(goal_achieved=False), _verified(goal_achieved=True)])

        result = asyncio.run(
            _controller(Policy(), verifier, observer, dispatcher).run("increase media volume", 2)
        )

        self.assertTrue(result.completed)
        self.assertEqual(
            ["quick-settings", "media-slider"],
            [action.element_id for action in dispatcher.actions],
        )
        self.assertEqual(
            [ActionKind.TAP, ActionKind.SET_SLIDER],
            [action.kind for action in dispatcher.actions],
        )
        self.assertEqual([0, 1], [outcome.milestone_index for outcome in result.outcomes])

    def test_premature_system_key_is_terminally_rejected_not_counted_as_a_gui_failure(self) -> None:
        """A model cannot exhaust GUI routes merely by repeatedly asking for a hardware key."""
        before = _observation("before")
        observer = QueuedObserver([before, before])
        dispatcher = RecordingDispatcher([])
        verifier = ScriptedVerifier([])
        premature_key = StepDecision(
            intent=SystemKeyIntent(key="VOLUME_UP", expected_effect="goal complete"),
            target_evidence="The model attempted a hardware shortcut.",
            confidence=0.8,
        )
        policy = ScriptedPolicy(
            StrategyPlan(goal="goal complete", routes=[["GUI route"]]),
            [premature_key],
            fallback=StepDecision(
                intent=SystemKeyIntent(key="VOLUME_UP", expected_effect="goal complete"),
                target_evidence="This fallback must never be reached.",
                confidence=0.5,
            ),
        )

        result = asyncio.run(_controller(policy, verifier, observer, dispatcher).run("goal complete", 3))

        self.assertFalse(result.completed)
        self.assertEqual(FailureClass.GROUNDING, result.failure_class)
        self.assertEqual([], dispatcher.actions)
        self.assertEqual(0, policy.fallback_calls)

    def test_policy_validation_error_is_terminal_not_a_path_to_hardware_fallback(self) -> None:
        """A real Policy rejection must not let invalid model output exhaust GUI routes."""
        before = _observation("before")
        observer = QueuedObserver([before, before])
        dispatcher = RecordingDispatcher([])
        verifier = ScriptedVerifier([])
        policy = Policy(
            decision_provider=lambda _: {
                "action": {
                    "kind": "SYSTEM_KEY",
                    "key": "VOLUME_UP",
                    "expected_effect": "increase media volume",
                },
                "target_evidence": "The model attempted an unsafe shortcut.",
                "confidence": 0.8,
                "alternate_element_ids": [],
            }
        )

        result = asyncio.run(_controller(policy, verifier, observer, dispatcher).run("increase media volume", 3))

        self.assertFalse(result.completed)
        self.assertEqual(FailureClass.GROUNDING, result.failure_class)
        self.assertEqual([], dispatcher.actions)

    def test_repeat_guard_ignores_changed_expected_effect_prose(self) -> None:
        """Changing only model wording must not permit a third identical physical tap."""
        same = _observation("same")
        observer = QueuedObserver([same, same, same, same, same, same])
        dispatcher = RecordingDispatcher([TransportResult(success=True), TransportResult(success=True)])
        verifier = ScriptedVerifier([_verified(goal_achieved=False), _verified(goal_achieved=False)])
        policy = ScriptedPolicy(
            StrategyPlan(
                goal="goal complete",
                routes=[["first GUI action", "second GUI action", "third GUI action"]],
            ),
            [
                _decision("primary", expected_effect="first wording"),
                _decision("primary", expected_effect="second wording"),
                _decision("primary", expected_effect="third wording"),
            ],
        )

        result = asyncio.run(_controller(policy, verifier, observer, dispatcher).run("goal complete", 5))

        self.assertFalse(result.completed)
        self.assertEqual(FailureClass.STALLED, result.failure_class)
        self.assertEqual(2, len(dispatcher.actions))

    def test_missing_screenshot_never_counts_as_a_stable_observation(self) -> None:
        """Vision-only means no native tree, not no screenshot for safe action verification."""
        uncaptured = Observation(
            observation_id="uncaptured",
            width=100,
            height=200,
            image=None,
            device_state={},
            elements=[],
        )
        observer = QueuedObserver([uncaptured, uncaptured])
        dispatcher = RecordingDispatcher([])
        verifier = ScriptedVerifier([])
        policy = ScriptedPolicy(StrategyPlan(goal="goal complete", routes=[["GUI route"]]), [])

        result = asyncio.run(_controller(policy, verifier, observer, dispatcher).run("goal complete", 3))

        self.assertFalse(result.completed)
        self.assertEqual(FailureClass.PERCEPTION, result.failure_class)
        self.assertEqual([], dispatcher.actions)

    def test_transient_post_action_capture_failure_retries_perception_once(self) -> None:
        """One transient capture error after dispatch must not skip semantic verification."""
        before = _observation("before")
        after = _observation("after", color="green", tree_text="complete")
        observer = QueuedObserver(
            [before, before, RuntimeError("temporary capture failure"), after, after]
        )
        dispatcher = RecordingDispatcher([TransportResult(success=True)])
        verifier = ScriptedVerifier([_verified(goal_achieved=True)])
        policy = ScriptedPolicy(
            StrategyPlan(goal="goal complete", routes=[["GUI route"]]), [_decision("primary")]
        )

        result = asyncio.run(_controller(policy, verifier, observer, dispatcher).run("goal complete", 3))

        self.assertTrue(result.completed)
        self.assertEqual(1, len(dispatcher.actions))
        self.assertEqual(1, len(verifier.calls))

    def test_run_rebinds_goal_aware_verifier_before_completion(self) -> None:
        """A verifier reused from another task cannot complete this run with its old goal."""
        before = _observation("before", tree_text="Wi-Fi disabled")
        after = _observation("after", color="green", tree_text="Wi-Fi enabled")
        observer = QueuedObserver([before, before, after, after])
        dispatcher = RecordingDispatcher([TransportResult(success=True)])
        policy = ScriptedPolicy(
            StrategyPlan(goal="mute media volume", routes=[["GUI route"]]),
            [_decision("primary", expected_effect="Wi-Fi enabled")],
        )

        result = asyncio.run(
            _controller(policy, Verifier(goal="Wi-Fi enabled"), observer, dispatcher).run(
                "mute media volume", 1
            )
        )

        self.assertFalse(result.completed)
        self.assertEqual(FailureClass.EXHAUSTED, result.failure_class)

    def test_repeated_observation_and_action_terminates_as_stalled(self) -> None:
        """The third identical observation/action pair is blocked before another side effect."""
        same = _observation("same")
        observer = QueuedObserver([same, same, same, same, same, same])
        dispatcher = RecordingDispatcher([TransportResult(success=True), TransportResult(success=True)])
        verifier = ScriptedVerifier([_verified(goal_achieved=False), _verified(goal_achieved=False)])
        policy = ScriptedPolicy(
            StrategyPlan(
                goal="goal complete",
                routes=[["first GUI action", "second GUI action", "third GUI action"]],
            ),
            [_decision("primary"), _decision("primary"), _decision("primary")],
        )

        result = asyncio.run(_controller(policy, verifier, observer, dispatcher).run("goal complete", 5))

        self.assertFalse(result.completed)
        self.assertEqual(FailureClass.STALLED, result.failure_class)
        self.assertEqual(2, len(dispatcher.actions))

    def test_step_exhaustion_returns_failed_not_completed(self) -> None:
        """Verified intermediate actions cannot turn a max-step exit into success."""
        before = _observation("before")
        after_first = _observation("after-first", color="yellow", tree_text="progress one")
        after_second = _observation("after-second", color="orange", tree_text="progress two")
        observer = QueuedObserver(
            [before, before, after_first, after_first, after_second, after_second]
        )
        dispatcher = RecordingDispatcher([TransportResult(success=True), TransportResult(success=True)])
        verifier = ScriptedVerifier([_verified(goal_achieved=False), _verified(goal_achieved=False)])
        policy = ScriptedPolicy(
            StrategyPlan(
                goal="goal complete",
                routes=[["first intermediate action", "second intermediate action"]],
            ),
            [_decision("primary", expected_effect="intermediate one"), _decision("secondary", expected_effect="intermediate two")],
        )

        result = asyncio.run(_controller(policy, verifier, observer, dispatcher).run("goal complete", 2))

        self.assertFalse(result.completed)
        self.assertEqual(FailureClass.EXHAUSTED, result.failure_class)
        self.assertEqual(2, len(dispatcher.actions))


if __name__ == "__main__":
    unittest.main()
