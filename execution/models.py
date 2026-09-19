"""Typed, serializable contracts for safe Android control-loop actions."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ActionKind(str, Enum):
    """The only actions a policy may ask the Android device to perform."""

    TAP = "TAP"
    LONG_PRESS = "LONG_PRESS"
    INPUT = "INPUT"
    SCROLL = "SCROLL"
    EDGE_SWIPE = "EDGE_SWIPE"
    SET_SLIDER = "SET_SLIDER"
    BACK = "BACK"
    HOME = "HOME"
    ENTER = "ENTER"
    WAIT = "WAIT"
    OPEN_APP = "OPEN_APP"
    SYSTEM_KEY = "SYSTEM_KEY"
    INSPECT_REGION = "INSPECT_REGION"


class FailureClass(str, Enum):
    """Classifies why a verified closed-loop attempt cannot continue safely."""

    PERCEPTION = "perception"
    GROUNDING = "grounding"
    TRANSPORT = "transport"
    NO_EFFECT = "no-effect"
    WRONG_EFFECT = "wrong-effect"
    STALLED = "stalled"
    EXHAUSTED = "exhausted"


class ScreenElement(BaseModel):
    """An observation-scoped UI target with normalized bounds."""

    model_config = ConfigDict(extra="forbid")

    element_id: str = Field(min_length=1)
    bounds: tuple[float, float, float, float]
    text: str = ""
    role: str = "unknown"
    source: str = "unknown"
    interactive: bool = False
    requires_inspection: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class Observation(BaseModel):
    """One screenshot and its fused semantic targets.

    The image is intentionally excluded from serialization. Callers retain it
    in memory for grounding and verification, while events carry only stable
    identifiers, actual dimensions, device state, and parsed elements.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    observation_id: str = Field(min_length=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    image: Any | None = Field(default=None, exclude=True, repr=False)
    device_state: dict[str, Any] = Field(default_factory=dict)
    elements: list[ScreenElement] = Field(default_factory=list)


class ActionIntentBase(BaseModel):
    """Fields shared by every policy action before it is grounded."""

    model_config = ConfigDict(extra="forbid")

    kind: ActionKind
    expected_effect: str = Field(min_length=1)

    @field_validator("expected_effect")
    @classmethod
    def expected_effect_must_be_meaningful(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("expected_effect must not be blank")
        return normalized


class TargetedActionIntent(ActionIntentBase):
    """An action that must resolve an element in the current observation."""

    element_id: str = Field(min_length=1)


class TapIntent(TargetedActionIntent):
    kind: Literal[ActionKind.TAP] = ActionKind.TAP


class LongPressIntent(TargetedActionIntent):
    kind: Literal[ActionKind.LONG_PRESS] = ActionKind.LONG_PRESS
    duration_ms: int = Field(default=500, ge=1, le=10_000)


class InputIntent(TargetedActionIntent):
    kind: Literal[ActionKind.INPUT] = ActionKind.INPUT
    text: str = Field(min_length=1)


class ScrollIntent(ActionIntentBase):
    kind: Literal[ActionKind.SCROLL] = ActionKind.SCROLL
    direction: Literal["UP", "DOWN", "LEFT", "RIGHT"]
    extent: float = Field(default=0.60, gt=0.0, le=1.0)


class EdgeSwipeIntent(ActionIntentBase):
    kind: Literal[ActionKind.EDGE_SWIPE] = ActionKind.EDGE_SWIPE
    edge: Literal["TOP", "BOTTOM", "LEFT", "RIGHT"]
    extent: float = Field(default=0.50, gt=0.0, le=1.0)


class SetSliderIntent(TargetedActionIntent):
    kind: Literal[ActionKind.SET_SLIDER] = ActionKind.SET_SLIDER
    value: float = Field(ge=0.0, le=1.0)


class BackIntent(ActionIntentBase):
    kind: Literal[ActionKind.BACK] = ActionKind.BACK


class HomeIntent(ActionIntentBase):
    kind: Literal[ActionKind.HOME] = ActionKind.HOME


class EnterIntent(ActionIntentBase):
    kind: Literal[ActionKind.ENTER] = ActionKind.ENTER


class WaitIntent(ActionIntentBase):
    kind: Literal[ActionKind.WAIT] = ActionKind.WAIT
    duration_ms: int = Field(default=500, ge=0, le=30_000)


class OpenAppIntent(ActionIntentBase):
    kind: Literal[ActionKind.OPEN_APP] = ActionKind.OPEN_APP
    package: str = Field(min_length=1)


class SystemKeyIntent(ActionIntentBase):
    kind: Literal[ActionKind.SYSTEM_KEY] = ActionKind.SYSTEM_KEY
    key: Literal["VOLUME_DOWN", "VOLUME_UP", "VOLUME_MUTE"]


class InspectRegionIntent(TargetedActionIntent):
    kind: Literal[ActionKind.INSPECT_REGION] = ActionKind.INSPECT_REGION


ActionIntent = Annotated[
    Union[
        TapIntent,
        LongPressIntent,
        InputIntent,
        ScrollIntent,
        EdgeSwipeIntent,
        SetSliderIntent,
        BackIntent,
        HomeIntent,
        EnterIntent,
        WaitIntent,
        OpenAppIntent,
        SystemKeyIntent,
        InspectRegionIntent,
    ],
    Field(discriminator="kind"),
]


class GroundedAction(BaseModel):
    """A validated intent with concrete device coordinates or ADB arguments."""

    model_config = ConfigDict(extra="forbid")

    kind: ActionKind
    expected_effect: str = Field(min_length=1)
    element_id: str | None = None
    point: tuple[int, int] | None = None
    start: tuple[int, int] | None = None
    end: tuple[int, int] | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    text: str | None = None
    package: str | None = None
    key: str | None = None
    internal: bool = False


class TransportResult(BaseModel):
    """The transport-level result of an ADB operation, before verification."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    command: tuple[str, ...] = ()
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


class VerificationResult(BaseModel):
    """Semantic evidence that an action did or did not cause its expected effect."""

    model_config = ConfigDict(extra="forbid")

    verified: bool
    reason: str = ""
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    failure_class: FailureClass | None = None
    goal_achieved: bool = False


class ActionOutcome(BaseModel):
    """One action's grounded request, transport result, and later verification."""

    model_config = ConfigDict(extra="forbid")

    action: GroundedAction
    transport: TransportResult
    verification: VerificationResult | None = None


class StrategyPlan(BaseModel):
    """A policy's candidate GUI routes and milestones for one goal."""

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1)
    routes: list[list[str]] = Field(default_factory=list)


class StepDecision(BaseModel):
    """Exactly one typed policy decision with evidence for later recovery."""

    model_config = ConfigDict(extra="forbid")

    intent: ActionIntent
    deferred_intent: ActionIntent | None = Field(default=None, exclude=True)
    target_evidence: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    alternate_element_ids: list[str] = Field(default_factory=list)
