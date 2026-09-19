"""Typed execution primitives for GUI Agent's closed-loop controller."""

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
