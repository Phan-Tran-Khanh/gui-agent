"""Contracts for presenting closed-loop controller outcomes to backend clients."""

from __future__ import annotations

import asyncio
import unittest

from PIL import Image

from execution.backend_adapter import ClosedLoopBackendAdapter
from execution.controller import ControllerOutcome, ControllerResult
from execution.models import (
    ActionKind,
    GroundedAction,
    InspectRegionIntent,
    Observation,
    StepDecision,
    StrategyPlan,
    TapIntent,
    TransportResult,
    VerificationResult,
)


def _observation(observation_id: str = "observation-1") -> Observation:
    return Observation(
        observation_id=observation_id,
        width=20,
        height=40,
        image=Image.new("RGB", (20, 40), "white"),
    )


class _RecordingEvents:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def emit(self, task_id: str, **event: object) -> None:
        self.events.append({"task_id": task_id, **event})


class _Controller:
    def __init__(self, result: ControllerResult) -> None:
        self.result = result
        self.calls: list[tuple[str, int]] = []

    async def run(self, goal: str, max_steps: int) -> ControllerResult:
        self.calls.append((goal, max_steps))
        return self.result


class _ShadowDevice:
    def __init__(self) -> None:
        self.captures = 0
        self.dispatches = 0

    def capture_screenshot(self) -> Image.Image:
        self.captures += 1
        return Image.new("RGB", (20, 40), "white")

    def perception_state(self) -> dict[str, object]:
        return {"source": "shadow-test"}

    def execute(self, _action: GroundedAction) -> TransportResult:
        self.dispatches += 1
        raise AssertionError("shadow rollout must not dispatch an action")


class _ShadowPerception:
    def __init__(self) -> None:
        self.calls = 0

    async def observe(
        self, image: Image.Image, device_state: dict[str, object]
    ) -> Observation:
        self.calls += 1
        return Observation(
            observation_id="shadow-observation",
            width=image.width,
            height=image.height,
            image=image,
            device_state=device_state,
        )


class _ShadowPolicy:
    def __init__(self) -> None:
        self.plan_calls = 0
        self.decide_calls = 0

    def plan(self, goal: str, _observation: Observation) -> StrategyPlan:
        self.plan_calls += 1
        return StrategyPlan(goal=goal, routes=[["visible milestone"]])

    def decide(
        self,
        _plan: StrategyPlan,
        _observation: Observation,
        _history: list[object],
        *,
        route_index: int,
        milestone_index: int,
    ) -> StepDecision:
        self.decide_calls += 1
        self.last_route = route_index
        self.last_milestone = milestone_index
        return StepDecision(
            intent=TapIntent(element_id="visible", expected_effect="complete goal"),
            target_evidence="visible test control",
            confidence=0.8,
        )


class BackendAdapterTests(unittest.TestCase):
    def test_closed_loop_events_keep_legacy_fields_and_add_typed_metadata(self) -> None:
        outcome = ControllerOutcome(
            route_index=2,
            milestone_index=3,
            intent=TapIntent(element_id="settings", expected_effect="open settings"),
            action=GroundedAction(
                kind=ActionKind.TAP,
                element_id="settings",
                point=(10, 15),
                expected_effect="open settings",
            ),
            transport=TransportResult(success=True),
            verification=VerificationResult(
                verified=True,
                goal_achieved=True,
                confidence=0.9,
                reason="settings is open",
            ),
        )
        controller = _Controller(
            ControllerResult(
                completed=True,
                outcomes=[outcome],
                final_observation=_observation("observation-final"),
            )
        )
        events = _RecordingEvents()

        result = asyncio.run(
            ClosedLoopBackendAdapter(controller=controller).execute(
                task_id="task-closed-loop",
                goal="open settings",
                max_steps=4,
                event_sink=events,
            )
        )

        self.assertTrue(result.success)
        self.assertTrue(result.goal_achieved)
        self.assertEqual([("open settings", 4)], controller.calls)
        self.assertEqual(
            ["task_started", "action_decided", "action_executed", "task_completed"],
            [event["event_type"] for event in events.events],
        )
        action_events = [
            event
            for event in events.events
            if event["event_type"] in {"action_decided", "action_executed"}
        ]
        self.assertEqual(["route-2/milestone-3"] * 2, [event["subgoal_id"] for event in action_events])
        for event in action_events:
            metadata = event["metadata"]
            self.assertEqual("closed-loop-v1", metadata["engineVersion"])
            self.assertEqual("2", metadata["routeId"])
            self.assertEqual("observation-final", metadata["observationId"])
            self.assertIn("actionIntent", metadata)
            self.assertIn("groundedAction", metadata)
            self.assertIn("verification", metadata)
            self.assertIn("confidence", metadata)

    def test_unverified_exhaustion_emits_task_failed_with_false_success(self) -> None:
        controller = _Controller(
            ControllerResult(completed=False, failure_class="exhausted")
        )
        events = _RecordingEvents()

        result = asyncio.run(
            ClosedLoopBackendAdapter(controller=controller).execute(
                task_id="task-failed",
                goal="unverified task",
                max_steps=1,
                event_sink=events,
            )
        )

        self.assertFalse(result.success)
        self.assertFalse(result.goal_achieved)
        self.assertEqual("task_failed", events.events[-1]["event_type"])
        self.assertEqual("failed", events.events[-1]["stage"])

    def test_internal_inspection_is_decided_but_never_reported_as_dispatched(self) -> None:
        outcome = ControllerOutcome(
            route_index=0,
            milestone_index=1,
            intent=InspectRegionIntent(
                element_id="ambiguous-control",
                expected_effect="inspect the ambiguous control",
            ),
            action=GroundedAction(
                kind=ActionKind.INSPECT_REGION,
                element_id="ambiguous-control",
                expected_effect="inspect the ambiguous control",
                internal=True,
            ),
        )
        events = _RecordingEvents()

        asyncio.run(
            ClosedLoopBackendAdapter(
                controller=_Controller(
                    ControllerResult(completed=False, failure_class="grounding", outcomes=[outcome])
                )
            ).execute(
                task_id="task-inspection",
                goal="inspect control",
                max_steps=1,
                event_sink=events,
            )
        )

        self.assertIn("action_decided", [event["event_type"] for event in events.events])
        self.assertNotIn("action_executed", [event["event_type"] for event in events.events])

    def test_shadow_prediction_captures_perceives_and_decides_without_resolving_or_dispatching(self) -> None:
        device = _ShadowDevice()
        perception = _ShadowPerception()
        policy = _ShadowPolicy()

        def forbidden_resolver(*_args: object) -> GroundedAction:
            raise AssertionError("shadow rollout must not resolve an action")

        adapter = ClosedLoopBackendAdapter.from_device(
            policy=policy,
            verifier=object(),
            device=device,
            perception=perception,
            resolve=forbidden_resolver,
        )

        prediction = asyncio.run(adapter.predict_shadow("complete goal"))

        self.assertEqual("shadow-observation", prediction.observation_id)
        self.assertEqual("route-0", prediction.route_id)
        self.assertEqual("route-0/milestone-0", prediction.milestone_id)
        self.assertEqual(1, device.captures)
        self.assertEqual(0, device.dispatches)
        self.assertEqual(1, perception.calls)
        self.assertEqual(1, policy.plan_calls)
        self.assertEqual(1, policy.decide_calls)


if __name__ == "__main__":
    unittest.main()
