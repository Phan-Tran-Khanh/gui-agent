"""Deterministically convert validated intents into safe device actions."""

from __future__ import annotations

from math import isfinite

from .models import (
    ActionIntent,
    ActionKind,
    EdgeSwipeIntent,
    GroundedAction,
    InputIntent,
    InspectRegionIntent,
    LongPressIntent,
    Observation,
    OpenAppIntent,
    ScrollIntent,
    ScreenElement,
    SetSliderIntent,
    SystemKeyIntent,
    TargetedActionIntent,
    WaitIntent,
)


class ActionResolutionError(ValueError):
    """Raised when an intent cannot be safely grounded on an observation."""


def resolve_action(intent: ActionIntent, observation: Observation) -> GroundedAction:
    """Resolve one typed intent using only the current observation's elements."""

    if isinstance(intent, TargetedActionIntent):
        element = _find_target(intent.element_id, observation)
        _validate_dispatchable_bounds(element, observation)
        if element.requires_inspection and not isinstance(intent, InspectRegionIntent):
            raise ActionResolutionError(
                f"element {element.element_id!r} requires INSPECT_REGION before dispatch"
            )
        return _resolve_targeted(intent, element, observation)

    if isinstance(intent, ScrollIntent):
        start, end = _scroll_points(intent, observation)
        return GroundedAction(
            kind=intent.kind,
            expected_effect=intent.expected_effect,
            start=start,
            end=end,
        )

    if isinstance(intent, EdgeSwipeIntent):
        start, end = _edge_swipe_points(intent, observation)
        return GroundedAction(
            kind=intent.kind,
            expected_effect=intent.expected_effect,
            start=start,
            end=end,
        )

    if isinstance(intent, WaitIntent):
        return GroundedAction(
            kind=intent.kind,
            expected_effect=intent.expected_effect,
            duration_ms=intent.duration_ms,
        )

    if isinstance(intent, OpenAppIntent):
        return GroundedAction(
            kind=intent.kind,
            expected_effect=intent.expected_effect,
            package=intent.package,
        )

    if isinstance(intent, SystemKeyIntent):
        return GroundedAction(
            kind=intent.kind,
            expected_effect=intent.expected_effect,
            key=intent.key,
        )

    return GroundedAction(kind=intent.kind, expected_effect=intent.expected_effect)


def _resolve_targeted(
    intent: TargetedActionIntent,
    element: ScreenElement,
    observation: Observation,
) -> GroundedAction:
    """Ground a target-bound intent after its screen bounds are proven safe."""

    if isinstance(intent, SetSliderIntent):
        point = _slider_point(element, observation, intent.value)
    else:
        point = _element_center(element, observation)

    if isinstance(intent, InspectRegionIntent):
        return GroundedAction(
            kind=intent.kind,
            expected_effect=intent.expected_effect,
            element_id=element.element_id,
            point=point,
            internal=True,
        )

    if isinstance(intent, InputIntent):
        return GroundedAction(
            kind=intent.kind,
            expected_effect=intent.expected_effect,
            element_id=element.element_id,
            point=point,
            text=intent.text,
        )

    if isinstance(intent, LongPressIntent):
        return GroundedAction(
            kind=intent.kind,
            expected_effect=intent.expected_effect,
            element_id=element.element_id,
            point=point,
            duration_ms=intent.duration_ms,
        )

    return GroundedAction(
        kind=intent.kind,
        expected_effect=intent.expected_effect,
        element_id=element.element_id,
        point=point,
    )


def _find_target(element_id: str, observation: Observation) -> ScreenElement:
    for element in observation.elements:
        if element.element_id == element_id:
            return element
    raise ActionResolutionError(
        f"element {element_id!r} is not present in observation {observation.observation_id!r}"
    )


def _validate_dispatchable_bounds(element: ScreenElement, observation: Observation) -> None:
    x1, y1, x2, y2 = element.bounds
    values = (x1, y1, x2, y2)
    if not all(isfinite(value) for value in values):
        raise ActionResolutionError(f"element {element.element_id!r} has non-finite bounds")
    if not (0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0):
        raise ActionResolutionError(f"element {element.element_id!r} has unsafe normalized bounds")
    if observation.width < 2 or observation.height < 2:
        raise ActionResolutionError("observation dimensions are too small for device dispatch")


def _element_center(element: ScreenElement, observation: Observation) -> tuple[int, int]:
    x1, y1, x2, y2 = element.bounds
    return (
        _clamp(round(((x1 + x2) / 2) * observation.width), observation.width),
        _clamp(round(((y1 + y2) / 2) * observation.height), observation.height),
    )


def _slider_point(
    element: ScreenElement, observation: Observation, value: float
) -> tuple[int, int]:
    x1, y1, x2, y2 = element.bounds
    left = x1 * observation.width
    right = x2 * observation.width
    inset = (right - left) * 0.05
    x = left + inset + ((right - left) - (2 * inset)) * value
    y = ((y1 + y2) / 2) * observation.height
    return (_clamp(round(x), observation.width), _clamp(round(y), observation.height))


def _scroll_points(
    intent: ScrollIntent, observation: Observation
) -> tuple[tuple[int, int], tuple[int, int]]:
    if observation.width < 2 or observation.height < 2:
        raise ActionResolutionError("observation dimensions are too small for a scroll")

    x_center = _clamp(round(observation.width / 2), observation.width)
    y_center = _clamp(round(observation.height / 2), observation.height)
    x_delta = max(1, round(observation.width * intent.extent * 0.30))
    y_delta = max(1, round(observation.height * intent.extent * 0.30))

    if intent.direction == "DOWN":
        return (x_center, _clamp(y_center + y_delta, observation.height)), (
            x_center,
            _clamp(y_center - y_delta, observation.height),
        )
    if intent.direction == "UP":
        return (x_center, _clamp(y_center - y_delta, observation.height)), (
            x_center,
            _clamp(y_center + y_delta, observation.height),
        )
    if intent.direction == "RIGHT":
        return (_clamp(x_center + x_delta, observation.width), y_center), (
            _clamp(x_center - x_delta, observation.width),
            y_center,
        )
    return (_clamp(x_center - x_delta, observation.width), y_center), (
        _clamp(x_center + x_delta, observation.width),
        y_center,
    )


def _edge_swipe_points(
    intent: EdgeSwipeIntent, observation: Observation
) -> tuple[tuple[int, int], tuple[int, int]]:
    if observation.width < 2 or observation.height < 2:
        raise ActionResolutionError("observation dimensions are too small for an edge swipe")

    x_center = _clamp(round(observation.width / 2), observation.width)
    y_center = _clamp(round(observation.height / 2), observation.height)
    x_inset = max(1, round(observation.width * 0.01))
    y_inset = max(1, round(observation.height * 0.01))
    x_distance = max(1, round(observation.width * intent.extent))
    y_distance = max(1, round(observation.height * intent.extent))

    if intent.edge == "TOP":
        start = (x_center, y_inset)
        end = (x_center, _clamp(y_inset + y_distance, observation.height))
    elif intent.edge == "BOTTOM":
        start = (x_center, _clamp(observation.height - 1 - y_inset, observation.height))
        end = (x_center, _clamp(start[1] - y_distance, observation.height))
    elif intent.edge == "LEFT":
        start = (x_inset, y_center)
        end = (_clamp(x_inset + x_distance, observation.width), y_center)
    else:
        start = (_clamp(observation.width - 1 - x_inset, observation.width), y_center)
        end = (_clamp(start[0] - x_distance, observation.width), y_center)
    return start, end


def _clamp(value: int, dimension: int) -> int:
    return max(0, min(dimension - 1, value))
