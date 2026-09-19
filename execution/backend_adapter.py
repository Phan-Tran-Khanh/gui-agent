"""Backend-facing adapters for the verified Android control loop.

This module deliberately has no dependency on the web application.  Both the
backend and the CLI can therefore select the same closed-loop implementation,
while the legacy executor remains available for a gradual rollout.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, TypeVar

from .controller import ClosedLoopController, ControllerOutcome, ControllerResult, PerceptionUnavailable
from .models import FailureClass, Observation, StepDecision


class ExecutionEngine(str, Enum):
    """Supported execution paths for backend and CLI rollout."""

    LEGACY = "legacy"
    CLOSED_LOOP = "closed_loop"
    SHADOW = "shadow"


class EventSink(Protocol):
    """The compatible subset of the existing sequential event runner."""

    async def emit(self, task_id: str, **event: Any) -> None: ...


@dataclass(frozen=True)
class BackendExecutionResult:
    """Terminal controller status mapped to the existing backend semantics."""

    success: bool
    goal_achieved: bool
    total_steps: int
    failure_class: FailureClass | None = None


@dataclass(frozen=True)
class ShadowPrediction:
    """A policy prediction recorded without resolving or dispatching an action."""

    observation_id: str
    route_id: str
    milestone_id: str
    action_intent: dict[str, Any]
    confidence: float


ResultT = TypeVar("ResultT")


async def run_with_engine(
    engine: ExecutionEngine,
    *,
    legacy_execute: Callable[[], Awaitable[ResultT]],
    closed_loop_execute: Callable[[], Awaitable[ResultT]],
    shadow_predict: Callable[[], Awaitable[object]] | None = None,
) -> ResultT:
    """Select exactly one authoritative execution path.

    Shadow mode first records a non-mutating prediction, then runs the legacy
    executor as the only authority allowed to resolve or dispatch actions.
    """

    if engine is ExecutionEngine.CLOSED_LOOP:
        return await closed_loop_execute()
    if engine is ExecutionEngine.SHADOW:
        if shadow_predict is None:
            raise ValueError("shadow engine requires a shadow prediction callback")
        await shadow_predict()
    return await legacy_execute()


def create_android_adapter(
    *,
    device_id: str | None,
    parse_screen: Callable[[Any], Awaitable[Any]],
) -> "ClosedLoopBackendAdapter":
    """Create the production controller from the shared Android boundaries."""

    # Perception imports the configured OmniParser client; deferring all runtime
    # dependencies keeps Config able to import ExecutionEngine during startup.
    from .android_device import AndroidDevice
    from .perception import PerceptionEngine
    from .policy import Policy
    from .verifier import Verifier

    device = AndroidDevice(serial=device_id)
    perception = PerceptionEngine(parse_screen=parse_screen)
    policy = Policy(installed_packages=device.installed_packages)
    # ``for_goal`` binds the task goal before any action is evaluated.
    verifier = Verifier(goal="unbound")
    return ClosedLoopBackendAdapter.from_device(
        policy=policy,
        verifier=verifier,
        device=device,
        perception=perception,
    )


class ClosedLoopBackendAdapter:
    """Translate controller outcomes into the established task event contract."""

    engine_version = "closed-loop-v1"

    def __init__(
        self,
        *,
        controller: ClosedLoopController | Any,
        shadow_observe: Callable[[], Awaitable[Observation]] | None = None,
        policy: Any | None = None,
    ) -> None:
        self._controller = controller
        self._shadow_observe = shadow_observe
        self._policy = policy

    @classmethod
    def from_device(
        cls,
        *,
        policy: Any,
        verifier: Any,
        device: Any,
        perception: Any,
        **controller_kwargs: Any,
    ) -> "ClosedLoopBackendAdapter":
        """Build controller and shadow paths from the Phase 1/2 boundaries."""

        async def observe() -> Observation:
            image = device.capture_screenshot()
            if image is None:
                raise PerceptionUnavailable("ADB screenshot capture failed")
            return await perception.observe(image, device.perception_state())

        controller = ClosedLoopController(
            policy=policy,
            verifier=verifier,
            observe=observe,
            dispatch=device.execute,
            **controller_kwargs,
        )
        return cls(controller=controller, shadow_observe=observe, policy=policy)

    async def execute(
        self,
        *,
        task_id: str,
        goal: str,
        max_steps: int,
        event_sink: EventSink,
    ) -> BackendExecutionResult:
        """Run the controller and emit additive, backwards-compatible events."""

        await event_sink.emit(
            task_id,
            stage="planning",
            event_type="task_started",
            title="Closed-Loop Execution Started",
            description=f"Goal: {goal}",
            metadata={"engineVersion": self.engine_version},
        )
        result: ControllerResult = await self._controller.run(goal, max_steps)
        observation_id = (
            result.final_observation.observation_id
            if result.final_observation is not None
            else None
        )
        for outcome in result.outcomes:
            await self._emit_outcome(
                task_id=task_id,
                outcome=outcome,
                observation_id=observation_id,
                event_sink=event_sink,
            )

        terminal_outcome = result.outcomes[-1] if result.outcomes else None
        terminal_subgoal_id, terminal_subgoal_index = _subgoal(terminal_outcome)
        if result.completed:
            await event_sink.emit(
                task_id,
                stage="completed",
                event_type="task_completed",
                title="Closed-Loop Goal Verified",
                description="The requested goal was independently verified.",
                subgoal_id=terminal_subgoal_id,
                subgoal_index=terminal_subgoal_index,
                metadata={
                    "engineVersion": self.engine_version,
                    "routeId": _route_id(terminal_outcome),
                    "observationId": observation_id,
                },
            )
        else:
            failure = result.failure_class.value if result.failure_class is not None else "unverified"
            await event_sink.emit(
                task_id,
                stage="failed",
                event_type="task_failed",
                title="Closed-Loop Goal Not Verified",
                description=(
                    "Closed-loop execution ended without verified goal completion "
                    f"({failure})."
                ),
                subgoal_id=terminal_subgoal_id,
                subgoal_index=terminal_subgoal_index,
                metadata={
                    "engineVersion": self.engine_version,
                    "routeId": _route_id(terminal_outcome),
                    "observationId": observation_id,
                    "verification": _model_payload(
                        terminal_outcome.verification if terminal_outcome is not None else None
                    ),
                },
            )

        return BackendExecutionResult(
            success=result.completed,
            goal_achieved=result.completed,
            total_steps=sum(1 for outcome in result.outcomes if outcome.action is not None),
            failure_class=None if result.completed else result.failure_class,
        )

    async def predict_shadow(self, goal: str) -> ShadowPrediction:
        """Capture, perceive, and decide once without resolving or dispatching."""

        if self._shadow_observe is None or self._policy is None:
            raise RuntimeError("shadow prediction requires policy and observation dependencies")
        observation = await self._shadow_observe()
        plan = self._policy.plan(goal, observation)
        decision: StepDecision = self._policy.decide(
            plan,
            observation,
            [],
            route_index=0,
            milestone_index=0,
        )
        return ShadowPrediction(
            observation_id=observation.observation_id,
            route_id="route-0",
            milestone_id="route-0/milestone-0",
            action_intent=_model_payload(decision.intent) or {},
            confidence=decision.confidence,
        )

    async def emit_shadow_prediction(
        self,
        *,
        task_id: str,
        goal: str,
        event_sink: EventSink,
    ) -> ShadowPrediction:
        """Record a shadow prediction as a normal, non-dispatching action event."""

        prediction = await self.predict_shadow(goal)
        await event_sink.emit(
            task_id,
            stage="planning",
            event_type="action_decided",
            title="Closed-Loop Shadow Prediction",
            description="Prediction recorded; legacy execution remains authoritative.",
            subgoal_id=prediction.milestone_id,
            subgoal_index=0,
            confidence=prediction.confidence,
            metadata={
                "engineVersion": self.engine_version,
                "routeId": prediction.route_id.removeprefix("route-"),
                "observationId": prediction.observation_id,
                "actionIntent": prediction.action_intent,
                "groundedAction": None,
                "verification": None,
                "confidence": prediction.confidence,
                "shadow": True,
            },
        )
        return prediction

    async def _emit_outcome(
        self,
        *,
        task_id: str,
        outcome: ControllerOutcome,
        observation_id: str | None,
        event_sink: EventSink,
    ) -> None:
        subgoal_id, subgoal_index = _subgoal(outcome)
        metadata = _outcome_metadata(outcome, observation_id, self.engine_version)
        if outcome.intent is not None:
            await event_sink.emit(
                task_id,
                stage="executing_subgoal",
                event_type="action_decided",
                title="Closed-Loop Action Decided",
                description=outcome.intent.expected_effect,
                subgoal_id=subgoal_id,
                subgoal_index=subgoal_index,
                confidence=metadata["confidence"],
                metadata=metadata,
            )
        if outcome.action is not None and not outcome.action.internal:
            await event_sink.emit(
                task_id,
                stage="reflecting",
                event_type="action_executed",
                title="Closed-Loop Action Verified",
                description=(
                    outcome.verification.reason
                    if outcome.verification is not None
                    else "Action dispatched; verification unavailable."
                ),
                subgoal_id=subgoal_id,
                subgoal_index=subgoal_index,
                confidence=metadata["confidence"],
                metadata=metadata,
            )


def _outcome_metadata(
    outcome: ControllerOutcome,
    observation_id: str | None,
    engine_version: str,
) -> dict[str, Any]:
    verification = outcome.verification
    return {
        "engineVersion": engine_version,
        "routeId": str(outcome.route_index),
        "observationId": observation_id,
        "actionIntent": _model_payload(outcome.intent),
        "groundedAction": _model_payload(outcome.action),
        "verification": _model_payload(verification),
        "confidence": verification.confidence if verification is not None else None,
    }


def _model_payload(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    serializer = getattr(value, "model_dump", None)
    if callable(serializer):
        return serializer(mode="json")
    return None


def _subgoal(outcome: ControllerOutcome | None) -> tuple[str | None, int | None]:
    if outcome is None:
        return None, None
    return (
        f"route-{outcome.route_index}/milestone-{outcome.milestone_index}",
        outcome.milestone_index,
    )


def _route_id(outcome: ControllerOutcome | None) -> str | None:
    return str(outcome.route_index) if outcome is not None else None
