"""Independent, fail-closed semantic verification for Android actions."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as element_tree
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models import FailureClass, GroundedAction, Observation, VerificationResult


class ObservationComparison(BaseModel):
    """Stable, serializable evidence from both before and after observations."""

    model_config = ConfigDict(extra="forbid")

    screenshot_changed: bool | None = None
    tree_changed: bool | None = None
    foreground_changed: bool | None = None
    semantic_changed: bool = False
    before_fingerprint: str
    after_fingerprint: str
    evidence: list[str] = Field(default_factory=list)


class SemanticVerdict(BaseModel):
    """An independent semantic decision based on a complete observation comparison."""

    model_config = ConfigDict(extra="forbid")

    matched: bool
    goal_achieved: bool = False
    reason: str = ""
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


SemanticJudge = Callable[
    [str, str, GroundedAction, Observation, Observation, ObservationComparison], SemanticVerdict
]


class Verifier:
    """Compare an action's exact before/after state without trusting ADB status."""

    def __init__(
        self,
        *,
        goal: str,
        semantic_judge: SemanticJudge | None = None,
    ) -> None:
        normalized_goal = goal.strip()
        if not normalized_goal:
            raise ValueError("goal must not be blank")
        self._goal = normalized_goal
        self._semantic_judge = semantic_judge or _default_semantic_judge

    def for_goal(self, goal: str) -> "Verifier":
        """Bind the verifier to one controller run without sharing a stale goal."""

        normalized_goal = goal.strip()
        if normalized_goal == self._goal:
            return self
        return Verifier(goal=normalized_goal, semantic_judge=self._semantic_judge)

    def verify(
        self,
        before: Observation,
        grounded_action: GroundedAction,
        after: Observation,
    ) -> VerificationResult:
        """Return semantic evidence for exactly one grounded action.

        Screenshot, hierarchy, foreground app, and semantic element state are
        compared on every call. A visual delta alone is never a success.
        """

        comparison = compare_observations(before, after)
        try:
            verdict = self._semantic_judge(
                self._goal,
                grounded_action.expected_effect,
                grounded_action,
                before,
                after,
                comparison,
            )
        except Exception as error:  # Fail closed at the verifier boundary.
            return VerificationResult(
                verified=False,
                reason=f"semantic verifier failed: {error}",
                evidence=comparison.evidence,
                confidence=0.0,
                failure_class=FailureClass.WRONG_EFFECT,
            )

        evidence = _deduplicate([*comparison.evidence, *verdict.evidence])
        if verdict.matched:
            return VerificationResult(
                verified=True,
                reason=verdict.reason or "expected effect is visible in the post-action state",
                evidence=evidence,
                confidence=verdict.confidence,
                goal_achieved=verdict.goal_achieved,
            )

        failure_class = (
            FailureClass.NO_EFFECT if _has_no_observable_change(comparison) else FailureClass.WRONG_EFFECT
        )
        return VerificationResult(
            verified=False,
            reason=verdict.reason or "post-action state does not show the expected effect",
            evidence=evidence,
            confidence=verdict.confidence,
            failure_class=failure_class,
        )


def compare_observations(before: Observation, after: Observation) -> ObservationComparison:
    """Compute stable deltas without treating request IDs as screen state."""

    before_image = _image_fingerprint(before)
    after_image = _image_fingerprint(after)
    before_tree = _tree_fingerprint(before)
    after_tree = _tree_fingerprint(after)
    before_foreground = _foreground_fingerprint(before)
    after_foreground = _foreground_fingerprint(after)
    before_semantic = _semantic_state_fingerprint(before)
    after_semantic = _semantic_state_fingerprint(after)

    screenshot_changed = _changed(before_image, after_image)
    tree_changed = _changed(before_tree, after_tree)
    foreground_changed = _changed(before_foreground, after_foreground)
    semantic_changed = before_semantic != after_semantic
    evidence = [
        _change_evidence("screenshot", screenshot_changed),
        _change_evidence("tree", tree_changed),
        _change_evidence("foreground", foreground_changed),
        _change_evidence("semantic", semantic_changed),
    ]
    return ObservationComparison(
        screenshot_changed=screenshot_changed,
        tree_changed=tree_changed,
        foreground_changed=foreground_changed,
        semantic_changed=semantic_changed,
        before_fingerprint=observation_fingerprint(before),
        after_fingerprint=observation_fingerprint(after),
        evidence=evidence,
    )


def observation_fingerprint(observation: Observation) -> str:
    """Fingerprint stable screen state while excluding transient request metadata."""

    material = {
        "screenshot": _image_fingerprint(observation),
        "tree": _tree_fingerprint(observation),
        "foreground": _foreground_fingerprint(observation),
        "semantic": _semantic_state_fingerprint(observation),
    }
    return _digest_json(material)


def _default_semantic_judge(
    goal: str,
    expected_effect: str,
    action: GroundedAction,
    before: Observation,
    after: Observation,
    comparison: ObservationComparison,
) -> SemanticVerdict:
    del goal, expected_effect, action, before, after, comparison
    return SemanticVerdict(
        matched=False,
        reason=(
            "an independent semantic judge is required to verify unrestricted "
            "natural-language effects"
        ),
        evidence=["independent_semantic_judge_required=True"],
        confidence=0.0,
    )


def _image_fingerprint(observation: Observation) -> str | None:
    image = observation.image
    if image is None:
        return None
    try:
        rgb = image.convert("RGB")
        digest = hashlib.sha256()
        digest.update(f"{rgb.width}x{rgb.height}".encode("ascii"))
        digest.update(rgb.tobytes())
        return digest.hexdigest()
    except (AttributeError, OSError, ValueError):
        return None


def _tree_fingerprint(observation: Observation) -> str | None:
    xml = observation.device_state.get("ui_hierarchy_xml")
    if not isinstance(xml, str) or not xml.strip():
        return None
    try:
        root = element_tree.fromstring(xml)
        nodes = [
            tuple(node.attrib.get(name, "") for name in _TREE_ATTRIBUTES)
            for node in root.iter("node")
        ]
        return _digest_json(nodes)
    except element_tree.ParseError:
        return _digest_json({"malformed_xml": xml})


def _foreground_fingerprint(observation: Observation) -> str | None:
    foreground = observation.device_state.get("foreground_app")
    if not isinstance(foreground, dict):
        return None
    return _digest_json(foreground)


def _semantic_state_fingerprint(observation: Observation) -> str:
    elements = sorted(
        (
            element.element_id,
            element.text,
            element.role,
            element.source,
            element.interactive,
            element.requires_inspection,
            tuple(
                (key, str(element.metadata[key]))
                for key in _SEMANTIC_METADATA
                if key in element.metadata
            ),
        )
        for element in observation.elements
    )
    return _digest_json(elements)


def _changed(before: str | None, after: str | None) -> bool | None:
    if before is None or after is None:
        return None
    return before != after


def _change_evidence(label: str, changed: bool | None) -> str:
    return f"{label}_changed={'unavailable' if changed is None else changed}"


def _has_no_observable_change(comparison: ObservationComparison) -> bool:
    return (
        comparison.screenshot_changed is False
        and comparison.tree_changed is False
        and comparison.foreground_changed in {False, None}
        and not comparison.semantic_changed
    )


def _digest_json(value: Any) -> str:
    material = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _deduplicate(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


_TREE_ATTRIBUTES = (
    "class",
    "resource-id",
    "text",
    "content-desc",
    "clickable",
    "editable",
    "scrollable",
    "enabled",
    "focused",
    "checked",
    "selected",
    "bounds",
)

_SEMANTIC_METADATA = (
    "checked",
    "selected",
    "enabled",
    "focused",
    "value",
    "state",
)
