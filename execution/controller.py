"""Verified, recovery-oriented orchestration for typed Android actions."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .action_resolver import ActionResolutionError, resolve_action
from .models import (
    ActionIntent,
    ActionKind,
    FailureClass,
    GroundedAction,
    Observation,
    StepDecision,
    StrategyPlan,
    TargetedActionIntent,
    TransportResult,
    VerificationResult,
)
from .verifier import observation_fingerprint, observation_settle_fingerprint


ObservationProvider = Callable[[], Awaitable[Observation]]
Dispatcher = Callable[[GroundedAction], TransportResult]
Resolver = Callable[[ActionIntent, Observation], GroundedAction]
Sleep = Callable[[float], Awaitable[None]]


class PerceptionUnavailable(RuntimeError):
    """Raised when a stable observation cannot be captured for safe verification."""


class ControllerOutcome(BaseModel):
    """One typed controller attempt, including non-dispatch recovery decisions."""

    model_config = ConfigDict(extra="forbid")

    route_index: int = Field(ge=0)
    milestone_index: int = Field(default=0, ge=0)
    intent: ActionIntent | None = None
    action: GroundedAction | None = None
    transport: TransportResult | None = None
    verification: VerificationResult | None = None
    failure_class: FailureClass | None = None
    recovery: str | None = None
    before_observation: Observation | None = Field(default=None, exclude=True)
    after_observation: Observation | None = Field(default=None, exclude=True)


class ControllerResult(BaseModel):
    """Terminal state of a closed-loop run; completion requires verified goal evidence."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    completed: bool
    failure_class: FailureClass | None = None
    outcomes: list[ControllerOutcome] = Field(default_factory=list)
    final_observation: Observation | None = None


class ClosedLoopController:
    """Capture, decide, resolve, dispatch, verify, and recover one action at a time."""

    def __init__(
        self,
        *,
        policy: Any,
        verifier: Any,
        observe: ObservationProvider,
        dispatch: Dispatcher,
        resolve: Resolver = resolve_action,
        settle_timeout_s: float = 10.0,
        poll_interval_s: float = 0.2,
        max_settle_polls: int = 20,
        clock: Callable[[], float] = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if settle_timeout_s <= 0:
            raise ValueError("settle_timeout_s must be positive")
        if poll_interval_s < 0:
            raise ValueError("poll_interval_s must not be negative")
        if max_settle_polls < 2:
            raise ValueError("max_settle_polls must be at least two")
        self._policy = policy
        self._verifier = verifier
        self._observe = observe
        self._dispatch = dispatch
        self._resolve = resolve
        self._settle_timeout_s = settle_timeout_s
        self._poll_interval_s = poll_interval_s
        self._max_settle_polls = max_settle_polls
        self._clock = clock
        self._sleep = sleep

    @classmethod
    def from_device(
        cls,
        *,
        policy: Any,
        verifier: Any,
        device: Any,
        perception: Any,
        **kwargs: Any,
    ) -> "ClosedLoopController":
        """Create the production observation boundary from Phase 1/2 adapters."""

        async def observe() -> Observation:
            image = device.capture_screenshot()
            if image is None:
                raise PerceptionUnavailable("ADB screenshot capture failed")
            return await perception.observe(image, device.perception_state())

        return cls(
            policy=policy,
            verifier=verifier,
            observe=observe,
            dispatch=device.execute,
            **kwargs,
        )

    async def run(self, goal: str, max_steps: int) -> ControllerResult:
        """Run until verified goal completion, a safe terminal failure, or step exhaustion."""

        outcomes: list[ControllerOutcome] = []
        if max_steps <= 0:
            return self._failed(FailureClass.EXHAUSTED, outcomes, None)
        try:
            observation = await self._settled_observation()
        except PerceptionUnavailable:
            return self._failed(FailureClass.PERCEPTION, outcomes, None)

        try:
            plan: StrategyPlan = self._policy.plan(goal, observation)
        except Exception:
            return self._failed(FailureClass.GROUNDING, outcomes, observation)
        try:
            verifier = self._verifier_for_goal(goal)
        except Exception:
            return self._failed(FailureClass.GROUNDING, outcomes, observation)

        route_index = 0
        milestone_index = 0
        steps = 0
        pending_decision: StepDecision | None = None
        used_alternate = False
        perception_retry_used = False
        fallback_attempted = False
        repeated_actions: dict[str, int] = {}

        while steps < max_steps:
            using_fallback = route_index >= len(plan.routes)
            if pending_decision is not None:
                decision = pending_decision
                pending_decision = None
            elif using_fallback:
                if fallback_attempted:
                    return self._failed(FailureClass.EXHAUSTED, outcomes, observation)
                fallback_attempted = True
                try:
                    decision = self._policy.system_fallback(goal, observation)
                except Exception:
                    return self._failed(FailureClass.EXHAUSTED, outcomes, observation)
                if decision is None:
                    return self._failed(FailureClass.EXHAUSTED, outcomes, observation)
            else:
                try:
                    decision = self._policy.decide(
                        plan,
                        observation,
                        outcomes,
                        route_index=route_index,
                        milestone_index=milestone_index,
                    )
                except Exception:
                    outcomes.append(
                        ControllerOutcome(
                            route_index=route_index,
                            milestone_index=milestone_index,
                            failure_class=FailureClass.GROUNDING,
                            recovery="policy decision rejected",
                        )
                    )
                    return self._failed(FailureClass.GROUNDING, outcomes, observation)

            if decision.intent.kind is ActionKind.SYSTEM_KEY and not using_fallback:
                outcomes.append(
                    ControllerOutcome(
                        route_index=route_index,
                        milestone_index=milestone_index,
                        intent=decision.intent,
                        failure_class=FailureClass.GROUNDING,
                        recovery="rejected premature system-key fallback",
                    )
                )
                return self._failed(FailureClass.GROUNDING, outcomes, observation)

            try:
                action = self._resolve(decision.intent, observation)
            except ActionResolutionError:
                outcomes.append(
                    ControllerOutcome(
                        route_index=route_index,
                        milestone_index=milestone_index,
                        intent=decision.intent,
                        failure_class=FailureClass.GROUNDING,
                        recovery="grounding failed",
                        before_observation=observation,
                    )
                )
                if not perception_retry_used:
                    perception_retry_used = True
                    try:
                        observation = await self._settled_observation()
                    except PerceptionUnavailable:
                        return self._failed(FailureClass.PERCEPTION, outcomes, observation)
                    continue
                alternate = self._alternate_decision(decision, observation, used_alternate)
                if alternate is not None:
                    pending_decision = alternate
                    used_alternate = True
                    continue
                if using_fallback:
                    return self._failed(FailureClass.EXHAUSTED, outcomes, observation)
                route_index += 1
                milestone_index = 0
                perception_retry_used = False
                used_alternate = False
                continue

            if action.internal:
                before_observation = observation
                try:
                    refreshed_observation = await self._settled_observation()
                except PerceptionUnavailable:
                    return self._failed(FailureClass.PERCEPTION, outcomes, observation)
                outcomes.append(
                    ControllerOutcome(
                        route_index=route_index,
                        milestone_index=milestone_index,
                        intent=decision.intent,
                        action=action,
                        before_observation=before_observation,
                        after_observation=refreshed_observation,
                        verification=VerificationResult(
                            verified=True,
                            reason="inspection is internal and triggered fresh perception",
                            evidence=["dispatched=False"],
                        ),
                        recovery="perception retry",
                    )
                )
                observation = refreshed_observation
                if perception_retry_used:
                    alternate = self._alternate_decision(
                        decision, refreshed_observation, used_alternate
                    )
                    if alternate is not None and not using_fallback:
                        pending_decision = alternate
                        used_alternate = True
                        continue
                    if using_fallback:
                        return self._failed(FailureClass.EXHAUSTED, outcomes, observation)
                    route_index += 1
                    milestone_index = 0
                    perception_retry_used = False
                    used_alternate = False
                    continue
                perception_retry_used = True
                continue

            repeat_key = self._repeat_key(observation, action)
            if repeated_actions.get(repeat_key, 0) >= 2:
                outcomes.append(
                    ControllerOutcome(
                        route_index=route_index,
                        milestone_index=milestone_index,
                        intent=decision.intent,
                        action=action,
                        failure_class=FailureClass.STALLED,
                        recovery="blocked third identical observation/action pair",
                    )
                )
                return self._failed(FailureClass.STALLED, outcomes, observation)
            repeated_actions[repeat_key] = repeated_actions.get(repeat_key, 0) + 1

            before_observation = observation
            transport = self._dispatch_safely(action)
            try:
                after = await self._settled_observation()
            except PerceptionUnavailable:
                if not perception_retry_used:
                    perception_retry_used = True
                    try:
                        after = await self._settled_observation()
                    except PerceptionUnavailable:
                        verification = VerificationResult(
                            verified=False,
                            reason="post-action observation did not settle after one retry",
                            evidence=["post_action_observation=unavailable"],
                            failure_class=FailureClass.PERCEPTION,
                        )
                        outcomes.append(
                            ControllerOutcome(
                                route_index=route_index,
                                milestone_index=milestone_index,
                                intent=decision.intent,
                                action=action,
                                transport=transport,
                                verification=verification,
                                failure_class=FailureClass.PERCEPTION,
                                before_observation=before_observation,
                            )
                        )
                        return self._failed(FailureClass.PERCEPTION, outcomes, observation)
                else:
                    verification = VerificationResult(
                        verified=False,
                        reason="post-action observation did not settle",
                        evidence=["post_action_observation=unavailable"],
                        failure_class=FailureClass.PERCEPTION,
                    )
                    outcomes.append(
                        ControllerOutcome(
                            route_index=route_index,
                            milestone_index=milestone_index,
                            intent=decision.intent,
                            action=action,
                            transport=transport,
                            verification=verification,
                            failure_class=FailureClass.PERCEPTION,
                            before_observation=before_observation,
                        )
                    )
                    return self._failed(FailureClass.PERCEPTION, outcomes, observation)

            verification = self._verify_safely(verifier, observation, action, after)
            failure_class = self._failure_class(transport, verification)
            outcomes.append(
                ControllerOutcome(
                    route_index=route_index,
                    milestone_index=milestone_index,
                    intent=decision.intent,
                    action=action,
                    transport=transport,
                    verification=verification,
                    failure_class=failure_class,
                    before_observation=before_observation,
                    after_observation=after,
                )
            )
            steps += 1
            observation = after

            if failure_class is None:
                if verification.goal_achieved:
                    return ControllerResult(
                        completed=True,
                        outcomes=outcomes,
                        final_observation=observation,
                    )
                perception_retry_used = False
                used_alternate = False
                if not using_fallback:
                    if milestone_index + 1 < len(plan.routes[route_index]):
                        milestone_index += 1
                    else:
                        route_index += 1
                        milestone_index = 0
                continue

            alternate = self._alternate_decision(decision, observation, used_alternate)
            if alternate is not None and not using_fallback:
                pending_decision = alternate
                used_alternate = True
                continue
            if using_fallback:
                return self._failed(FailureClass.EXHAUSTED, outcomes, observation)
            route_index += 1
            milestone_index = 0
            perception_retry_used = False
            used_alternate = False

        return self._failed(FailureClass.EXHAUSTED, outcomes, observation)

    async def _settled_observation(self) -> Observation:
        """Poll until two consecutive screenshot/tree semantic fingerprints agree."""

        started = self._clock()
        try:
            previous = await self._observe()
            self._require_screenshot(previous)
        except Exception as error:
            raise PerceptionUnavailable("initial observation capture failed") from error

        for _ in range(1, self._max_settle_polls):
            if self._clock() - started >= self._settle_timeout_s:
                break
            if self._poll_interval_s:
                await self._sleep(self._poll_interval_s)
            try:
                current = await self._observe()
                self._require_screenshot(current)
            except Exception as error:
                raise PerceptionUnavailable("observation capture failed while settling") from error
            if observation_settle_fingerprint(previous) == observation_settle_fingerprint(current):
                return current
            previous = current
        raise PerceptionUnavailable("observation did not stabilize before the settle timeout")

    @staticmethod
    def _alternate_decision(
        decision: StepDecision,
        observation: Observation,
        alternate_already_used: bool,
    ) -> StepDecision | None:
        source_intent = decision.deferred_intent or decision.intent
        if alternate_already_used or not isinstance(source_intent, TargetedActionIntent):
            return None
        known_elements = {element.element_id: element for element in observation.elements}
        for alternate_id in decision.alternate_element_ids:
            alternate = known_elements.get(alternate_id)
            if (
                alternate is not None
                and alternate.interactive
                and not alternate.requires_inspection
                and alternate_id != source_intent.element_id
            ):
                return decision.model_copy(
                    update={
                        "intent": source_intent.model_copy(
                            update={"element_id": alternate_id}
                        ),
                        "deferred_intent": None,
                        "alternate_element_ids": [],
                    }
                )
        return None

    def _dispatch_safely(self, action: GroundedAction) -> TransportResult:
        try:
            return self._dispatch(action)
        except Exception as error:
            return TransportResult(success=False, error=f"dispatch raised: {error}")

    def _verify_safely(
        self,
        verifier: Any,
        before: Observation,
        action: GroundedAction,
        after: Observation,
    ) -> VerificationResult:
        try:
            return verifier.verify(before, action, after)
        except Exception as error:
            return VerificationResult(
                verified=False,
                reason=f"semantic verification raised: {error}",
                failure_class=FailureClass.WRONG_EFFECT,
            )

    @staticmethod
    def _failure_class(
        transport: TransportResult,
        verification: VerificationResult,
    ) -> FailureClass | None:
        if not transport.success:
            return FailureClass.TRANSPORT
        if verification.verified:
            return None
        return verification.failure_class or FailureClass.WRONG_EFFECT

    @staticmethod
    def _repeat_key(observation: Observation, action: GroundedAction) -> str:
        action_payload = action.model_dump(mode="json")
        action_payload.pop("expected_effect", None)
        return f"{observation_fingerprint(observation)}:{json.dumps(action_payload, sort_keys=True)}"

    @staticmethod
    def _require_screenshot(observation: Observation) -> None:
        if observation.image is None:
            raise PerceptionUnavailable("observation is missing its screenshot")

    def _verifier_for_goal(self, goal: str) -> Any:
        binder = getattr(self._verifier, "for_goal", None)
        return binder(goal) if callable(binder) else self._verifier

    @staticmethod
    def _failed(
        failure_class: FailureClass,
        outcomes: list[ControllerOutcome],
        observation: Observation | None,
    ) -> ControllerResult:
        return ControllerResult(
            completed=False,
            failure_class=failure_class,
            outcomes=outcomes,
            final_observation=observation,
        )
