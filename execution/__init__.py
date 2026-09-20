"""Typed execution primitives for GUI Agent's closed-loop controller."""

from typing import TYPE_CHECKING

from .models import (
    ActionIntent,
    ActionKind,
    ActionOutcome,
    GroundedAction,
    Observation,
    ScreenElement,
    StepDecision,
    StrategyPlan,
    TransportResult,
    VerificationResult,
)
from .action_resolver import ActionResolutionError, resolve_action
from .android_device import AndroidDevice

if TYPE_CHECKING:
    from .perception import PerceptionEngine

__all__ = [
    "ActionIntent",
    "ActionResolutionError",
    "ActionKind",
    "ActionOutcome",
    "AndroidDevice",
    "GroundedAction",
    "Observation",
    "PerceptionEngine",
    "ScreenElement",
    "StepDecision",
    "StrategyPlan",
    "TransportResult",
    "VerificationResult",
    "resolve_action",
]


def __getattr__(name: str) -> object:
    """Avoid importing config-dependent perception while config is initializing."""

    if name == "PerceptionEngine":
        from .perception import PerceptionEngine

        return PerceptionEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
