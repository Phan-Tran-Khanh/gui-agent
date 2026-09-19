"""Structured, fail-closed policy decisions for the Android control loop."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .models import (
    ActionIntent,
    ActionKind,
    InspectRegionIntent,
    Observation,
    OpenAppIntent,
    SetSliderIntent,
    StepDecision,
    StrategyPlan,
    SystemKeyIntent,
    TapIntent,
    TargetedActionIntent,
    WaitIntent,
)


PlanProvider = Callable[[dict[str, Any]], StrategyPlan | dict[str, Any]]
DecisionProvider = Callable[[dict[str, Any]], StepDecision | dict[str, Any]]
PackageProvider = Callable[[], set[str] | None]


class PolicyValidationError(ValueError):
    """Raised when untrusted policy output is unsafe or structurally invalid."""


class _DecisionPayload(BaseModel):
    """The only model-facing one-step response shape accepted by ``Policy``."""

    model_config = ConfigDict(extra="forbid")

    action: ActionIntent
    target_evidence: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    alternate_element_ids: list[str] = Field(default_factory=list)


class Policy:
    """Plan variable GUI routes and validate exactly one typed next action."""

    def __init__(
        self,
        *,
        plan_provider: PlanProvider | None = None,
        decision_provider: DecisionProvider | None = None,
        installed_packages: PackageProvider | None = None,
        history_limit: int = 8,
    ) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be at least one")
        self._plan_provider = plan_provider
        self._decision_provider = decision_provider
        self._installed_packages = installed_packages
        self._history_limit = history_limit

    def plan(self, goal: str, observation: Observation) -> StrategyPlan:
        """Return non-empty GUI routes without exposing system-key shortcuts."""

        normalized_goal = _meaningful_goal(goal)
        if self._plan_provider is None:
            plan = _default_plan(normalized_goal)
        else:
            context = self._model_context(normalized_goal, None, observation, [])
            plan = self._parse_plan(self._plan_provider(context))

        if plan.goal.strip() != normalized_goal:
            raise PolicyValidationError("policy plan goal does not match the requested goal")
        _validate_gui_routes(plan)
        return plan

    def decide(
        self,
        plan: StrategyPlan,
        observation: Observation,
        history: Sequence[Any],
        *,
        route_index: int = 0,
        milestone_index: int = 0,
        allow_system_fallback: bool = False,
    ) -> StepDecision:
        """Validate one policy response against the current observation only."""

        _validate_gui_routes(plan)
        active_route, active_milestone = _active_route(
            plan, route_index=route_index, milestone_index=milestone_index
        )
        if self._decision_provider is None:
            decision = _default_decision(
                plan.goal,
                observation,
                active_route,
                milestone_index,
            )
        else:
            context = self._model_context(
                plan.goal,
                plan,
                observation,
                history,
                route_index=route_index,
                milestone_index=milestone_index,
                active_route=active_route,
                active_milestone=active_milestone,
            )
            decision = self._parse_decision(self._decision_provider(context))
        return self._validate_decision(
            decision,
            observation,
            allow_system_fallback=allow_system_fallback,
        )

    def system_fallback(
        self, goal: str, observation: Observation
    ) -> StepDecision | None:
        """Return a typed hardware-key fallback only for volume control goals.

        The controller deliberately calls this only after each visible GUI route
        has failed. Keeping it outside ``plan()`` prevents a model from treating
        a system key as an interchangeable first route.
        """

        normalized_goal = _meaningful_goal(goal)
        operation = _volume_operation(normalized_goal)
        if operation is None:
            return None
        return StepDecision(
            intent=SystemKeyIntent(
                key=_volume_key_for_operation(operation),
                expected_effect=normalized_goal,
            ),
            target_evidence=(
                "All visible GUI volume routes were exhausted by the controller; "
                "use the allowlisted hardware fallback."
            ),
            confidence=0.5,
            alternate_element_ids=[],
        )

    def _parse_plan(self, payload: StrategyPlan | dict[str, Any]) -> StrategyPlan:
        try:
            if isinstance(payload, StrategyPlan):
                return StrategyPlan.model_validate(payload.model_dump(mode="json"))
            return StrategyPlan.model_validate(payload)
        except ValidationError as error:
            raise PolicyValidationError("policy returned an invalid strategy plan") from error

    def _parse_decision(
        self, payload: StepDecision | dict[str, Any]
    ) -> StepDecision:
        try:
            if isinstance(payload, StepDecision):
                typed_payload = payload.model_dump(mode="json")
                intent = typed_payload.pop("intent")
                raw = {**typed_payload, "action": intent}
            else:
                raw = payload
            parsed = _DecisionPayload.model_validate(raw)
        except ValidationError as error:
            raise PolicyValidationError("policy must return exactly one valid typed action") from error
        return StepDecision(
            intent=parsed.action,
            target_evidence=parsed.target_evidence.strip(),
            confidence=parsed.confidence,
            alternate_element_ids=parsed.alternate_element_ids,
        )

    def _validate_decision(
        self,
        decision: StepDecision,
        observation: Observation,
        *,
        allow_system_fallback: bool,
    ) -> StepDecision:
        intent = decision.intent
        known_elements = {element.element_id: element for element in observation.elements}
        alternate_ids = decision.alternate_element_ids

        if not isinstance(intent, TargetedActionIntent) and alternate_ids:
            raise PolicyValidationError("only targeted actions may declare alternate element IDs")
        if len(set(alternate_ids)) != len(alternate_ids):
            raise PolicyValidationError("alternate element IDs must be unique")
        for alternate_id in alternate_ids:
            alternate = known_elements.get(alternate_id)
            if alternate is None:
                raise PolicyValidationError(
                    f"alternate target {alternate_id!r} is absent from the current observation"
                )
            if not alternate.interactive or alternate.requires_inspection:
                raise PolicyValidationError(
                    f"alternate target {alternate_id!r} is not dispatchable in the current observation"
                )
            if isinstance(intent, TargetedActionIntent) and alternate_id == intent.element_id:
                raise PolicyValidationError("the primary target cannot also be its alternate")

        if isinstance(intent, TargetedActionIntent):
            target = known_elements.get(intent.element_id)
            if target is None:
                raise PolicyValidationError(
                    f"policy target {intent.element_id!r} is absent from the current observation"
                )
            if target.requires_inspection and not isinstance(intent, InspectRegionIntent):
                return StepDecision(
                    intent=InspectRegionIntent(
                        element_id=target.element_id,
                        expected_effect=(
                            f"inspect {target.text or target.element_id} before "
                            f"{intent.expected_effect}"
                        ),
                    ),
                    deferred_intent=intent,
                    target_evidence=decision.target_evidence,
                    confidence=decision.confidence,
                    alternate_element_ids=decision.alternate_element_ids,
                )
            if not target.interactive and not isinstance(intent, InspectRegionIntent):
                raise PolicyValidationError(
                    f"policy target {target.element_id!r} is context-only and cannot be dispatched"
                )

        if isinstance(intent, OpenAppIntent):
            packages = self._known_packages(observation)
            if intent.package not in packages:
                raise PolicyValidationError(
                    f"policy package {intent.package!r} is not in the observed package registry"
                )

        if isinstance(intent, SystemKeyIntent) and not allow_system_fallback:
            raise PolicyValidationError(
                "SYSTEM_KEY is unavailable until the controller exhausts GUI routes"
            )

        return decision

    def _known_packages(self, observation: Observation) -> set[str]:
        packages = self._installed_packages() if self._installed_packages is not None else None
        if packages is None:
            raw_packages = observation.device_state.get("installed_packages", [])
            packages = set(raw_packages) if isinstance(raw_packages, (list, set, tuple)) else set()
        return {package for package in packages if isinstance(package, str) and package}

    def _model_context(
        self,
        goal: str,
        plan: StrategyPlan | None,
        observation: Observation,
        history: Sequence[Any],
        *,
        route_index: int | None = None,
        milestone_index: int | None = None,
        active_route: Sequence[str] | None = None,
        active_milestone: str | None = None,
    ) -> dict[str, Any]:
        context = {
            "goal": goal,
            "plan": plan.model_dump(mode="json") if plan is not None else None,
            "active_route_index": route_index,
            "active_route": list(active_route) if active_route is not None else None,
            "active_milestone_index": milestone_index,
            "active_milestone": active_milestone,
            "observation": {
                "observation_id": observation.observation_id,
                "width": observation.width,
                "height": observation.height,
                "device_state": _json_safe(observation.device_state),
                "elements": [
                    {
                        "element_id": element.element_id,
                        "text": element.text,
                        "role": element.role,
                        "source": element.source,
                        "interactive": element.interactive,
                        "requires_inspection": element.requires_inspection,
                    }
                    for element in observation.elements
                ],
            },
            "history": [_json_safe(entry) for entry in history[-self._history_limit :]],
            "response_schema": {
                "action": "one ActionIntent object",
                "target_evidence": "non-empty string",
                "confidence": "number from 0 to 1",
                "alternate_element_ids": "list of current observation IDs",
            },
        }
        # Ensure a provider can never receive an accidental PIL image or other
        # object that is not serializable at the model boundary.
        json.dumps(context)
        return context


def _meaningful_goal(goal: str) -> str:
    normalized = goal.strip()
    if not normalized:
        raise PolicyValidationError("goal must not be blank")
    return normalized


def _validate_gui_routes(plan: StrategyPlan) -> None:
    if not plan.routes or any(not route or any(not milestone.strip() for milestone in route) for route in plan.routes):
        raise PolicyValidationError("policy plan must contain non-empty GUI routes and milestones")
    if any(
        "system" in milestone.casefold()
        for route in plan.routes
        for milestone in route
    ):
        raise PolicyValidationError("system actions must not be included in GUI routes")


def _active_route(
    plan: StrategyPlan,
    *,
    route_index: int,
    milestone_index: int,
) -> tuple[list[str], str]:
    if isinstance(route_index, bool) or not isinstance(route_index, int):
        raise PolicyValidationError("active route index must be an integer")
    if isinstance(milestone_index, bool) or not isinstance(milestone_index, int):
        raise PolicyValidationError("active milestone index must be an integer")
    if not 0 <= route_index < len(plan.routes):
        raise PolicyValidationError("active route index is outside the planned GUI routes")
    route = plan.routes[route_index]
    if not 0 <= milestone_index < len(route):
        raise PolicyValidationError("active milestone index is outside the selected GUI route")
    return route, route[milestone_index]


def _default_plan(goal: str) -> StrategyPlan:
    if _is_volume_goal(goal):
        return StrategyPlan(
            goal=goal,
            routes=[
                ["Open Quick Settings", "Adjust the visible media volume slider"],
                [
                    "Open Settings",
                    "Open Sound and vibration",
                    "Adjust the visible media volume slider",
                ],
            ],
        )
    return StrategyPlan(
        goal=goal,
        routes=[
            ["Identify a visible control related to the goal", "Use the grounded control"],
            ["Navigate to an alternate visible route", "Use its grounded control"],
        ],
    )


def _default_decision(
    goal: str,
    observation: Observation,
    active_route: Sequence[str],
    milestone_index: int,
) -> StepDecision:
    candidate_matches = [
        (remaining_index, milestone, element, _milestone_relevance(milestone, element.text))
        for remaining_index, milestone in enumerate(active_route[milestone_index:])
        for element in observation.elements
        if _milestone_relevance(milestone, element.text) > (0, 0.0)
    ]
    candidates = sorted(
        candidate_matches,
        key=lambda match: (
            -match[0],
            match[3],
            _goal_relevance(goal, match[2].text),
            match[2].interactive and not match[2].requires_inspection,
            not match[2].requires_inspection,
            match[2].element_id,
        ),
        reverse=True,
    )
    if not candidates:
        active_milestone = active_route[milestone_index]
        return StepDecision(
            intent=WaitIntent(
                duration_ms=500,
                expected_effect=f"a visible control for {active_milestone} appears",
            ),
            target_evidence=(
                "No current element provides sufficient evidence for the active GUI milestone."
            ),
            confidence=0.0,
        )

    _, selected_milestone, target, _ = candidates[0]
    evidence = (
        f"Current {target.source} element {target.element_id!r} is labelled {target.text!r} "
        f"and matches GUI milestone {selected_milestone!r}."
    )
    if target.requires_inspection:
        intent: ActionIntent = InspectRegionIntent(
            element_id=target.element_id,
            expected_effect=f"inspect {target.text or target.element_id} before acting on {goal}",
        )
    elif _is_volume_goal(goal) and any(
        role_name in target.role.casefold() for role_name in ("slider", "seekbar")
    ):
        value = _relative_slider_value(goal, target.metadata)
        if value is None:
            intent = InspectRegionIntent(
                element_id=target.element_id,
                expected_effect=(
                    f"inspect the current value of {target.text or target.element_id} "
                    f"before acting on {goal}"
                ),
            )
        else:
            intent = SetSliderIntent(
                element_id=target.element_id,
                value=value,
                expected_effect=goal,
            )
    elif target.interactive:
        intent = TapIntent(element_id=target.element_id, expected_effect=goal)
    else:
        intent = InspectRegionIntent(
            element_id=target.element_id,
            expected_effect=f"inspect {target.text or target.element_id} before acting on {goal}",
        )
    return StepDecision(intent=intent, target_evidence=evidence, confidence=0.5)


def _json_safe(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    try:
        return json.loads(json.dumps(value))
    except (TypeError, ValueError) as error:
        raise PolicyValidationError("policy context contains non-serializable state") from error


def _is_volume_goal(goal: str) -> bool:
    return "volume" in goal.casefold()


def _volume_operation(goal: str) -> str | None:
    """Parse one unambiguous allowlisted relative-volume operation."""

    words = set(re.findall(r"[a-z0-9]+", goal.casefold()))
    if "volume" not in words:
        return None
    has_increase = bool(words & _VOLUME_INCREASE_WORDS)
    has_decrease = bool(words & _VOLUME_DECREASE_WORDS)
    if "mute" in words:
        return "mute" if not (has_increase or has_decrease) else None
    if has_increase == has_decrease:
        return None
    return "increase" if has_increase else "decrease"


def _volume_key_for_operation(operation: str) -> str:
    if operation == "mute":
        return "VOLUME_MUTE"
    return "VOLUME_DOWN" if operation == "decrease" else "VOLUME_UP"


def _relative_slider_value(goal: str, metadata: dict[str, Any]) -> float | None:
    operation = _volume_operation(goal)
    if operation is None:
        return None
    raw_value = metadata.get("normalized_value")
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        return None
    current = float(raw_value)
    if not 0.0 <= current <= 1.0:
        return None
    if operation == "mute":
        return 0.0
    if operation == "decrease":
        return max(0.0, current - 0.10)
    return min(1.0, current + 0.10)


def _goal_relevance(goal: str, label: str) -> int:
    goal_words = set(re.findall(r"[a-z0-9]+", goal.casefold()))
    label_words = set(re.findall(r"[a-z0-9]+", label.casefold()))
    return len(goal_words & label_words)


def _milestone_relevance(milestone: str, label: str) -> tuple[int, float]:
    milestone_words = set(re.findall(r"[a-z0-9]+", milestone.casefold()))
    label_words = set(re.findall(r"[a-z0-9]+", label.casefold()))
    if not milestone_words or not label_words:
        return (0, 0.0)
    matched = len(milestone_words & label_words)
    return (matched, matched / len(label_words))


_VOLUME_INCREASE_WORDS = frozenset({"increase", "raise", "up", "louder"})
_VOLUME_DECREASE_WORDS = frozenset({"decrease", "lower", "down", "reduce", "quieter"})
