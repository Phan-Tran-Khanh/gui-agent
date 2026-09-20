"""Run deterministic Android replay gates and optional live-device acceptance checks."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image
from pydantic import TypeAdapter

from execution.action_resolver import ActionResolutionError, resolve_action
from execution.controller import ClosedLoopController
from execution.models import (
    ActionIntent,
    ActionKind,
    FailureClass,
    GroundedAction,
    Observation,
    ScreenElement,
    StepDecision,
    StrategyPlan,
    TransportResult,
)
from execution.policy import Policy
from execution.verifier import SemanticVerdict, Verifier

MANIFEST_PATH = PROJECT_ROOT / "tests" / "fixtures" / "replays" / "manifest.json"
_ACTION_INTENT = TypeAdapter(ActionIntent)


@dataclass(frozen=True)
class ReplayResult:
    """One deterministic replay outcome suitable for machine-readable reporting."""

    scenario_id: str
    iteration: int
    category: str
    action_class: str
    verified: bool
    completed: bool
    recovery: str | None
    unsafe_coordinate_count: int
    unsupported_dispatch_count: int
    coordinates: tuple[tuple[int, int], ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["coordinates"] = [list(point) for point in self.coordinates]
        return payload


class _QueuedObserver:
    def __init__(self, observations: Sequence[Observation]) -> None:
        self._observations = deque(observations)

    async def __call__(self) -> Observation:
        if not self._observations:
            raise AssertionError("replay requested an observation not present in its fixture")
        return self._observations.popleft()


class _ReplayPolicy:
    """Small deterministic policy adapter used only to exercise the public controller."""

    def __init__(self, case: dict[str, Any], intent: ActionIntent, route_count: int = 1) -> None:
        self._case = case
        self._intent = intent
        self._route_count = route_count

    def plan(self, goal: str, observation: Observation) -> StrategyPlan:
        del observation
        return StrategyPlan(
            goal=goal,
            routes=[["recorded GUI action"] for _ in range(self._route_count)],
        )

    def decide(
        self,
        plan: StrategyPlan,
        observation: Observation,
        history: Sequence[object],
        *,
        route_index: int = 0,
        milestone_index: int = 0,
    ) -> StepDecision:
        del plan, observation, history, route_index, milestone_index
        return StepDecision(
            intent=self._intent,
            target_evidence="The replay fixture supplied the current target evidence.",
            confidence=1.0,
        )

    def system_fallback(self, goal: str, observation: Observation) -> None:
        del goal, observation
        return None


class _RecordingDispatcher:
    """Transport simulation that counts invalid replay dispatches without using ADB."""

    def __init__(self, case: dict[str, Any], width: int, height: int) -> None:
        self._case = case
        self._width = width
        self._height = height
        self.actions: list[GroundedAction] = []
        self.coordinates: list[tuple[int, int]] = []
        self.unsafe_coordinate_count = 0
        self.unsupported_dispatch_count = 0

    def __call__(self, action: GroundedAction) -> TransportResult:
        self.actions.append(action)
        self._record_coordinates(action)
        if action.kind not in ActionKind:
            self.unsupported_dispatch_count += 1
        if action.kind is ActionKind.OPEN_APP:
            packages = set(self._case.get("installed_packages", []))
            if action.package not in packages:
                self.unsupported_dispatch_count += 1
        return TransportResult(success=bool(self._case.get("transport_success", True)))

    def _record_coordinates(self, action: GroundedAction) -> None:
        points = [point for point in (action.point, action.start, action.end) if point is not None]
        for point in points:
            self.coordinates.append(point)
            x, y = point
            if not (0 <= x < self._width and 0 <= y < self._height):
                self.unsafe_coordinate_count += 1


def load_replay_manifest(path: Path | None = None) -> dict[str, Any]:
    """Load and minimally validate the sanitized, hardware-free replay corpus."""

    with (path or MANIFEST_PATH).open(encoding="utf-8") as fixture_file:
        manifest = json.load(fixture_file)
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported replay manifest schema")
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("replay manifest requires at least one scenario")
    recorded_outcomes = manifest.get("recorded_outcomes")
    if not isinstance(recorded_outcomes, dict):
        raise ValueError("replay manifest requires recorded outcomes keyed by scenario ID")
    required = {
        "id",
        "category",
        "screenshot_ref",
        "parser_elements",
        "action",
        "expected_action_class",
        "expected_verification_result",
    }
    scenario_ids: set[str] = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict) or not required <= scenario.keys():
            raise ValueError("replay manifest contains an incomplete scenario")
        scenario_id = scenario["id"]
        if not isinstance(scenario_id, str) or not scenario_id or scenario_id in scenario_ids:
            raise ValueError("replay manifest scenario IDs must be unique non-empty strings")
        scenario_ids.add(scenario_id)
        _reference_path(scenario["screenshot_ref"])
        _reference_path(scenario.get("after_screenshot_ref", scenario["screenshot_ref"]))
        parser_ref = scenario.get("parser_ref")
        if parser_ref is not None:
            _reference_path(parser_ref, allowed_suffixes=(".json",))
        outcome = recorded_outcomes.get(scenario_id)
        if not isinstance(outcome, dict) or not {
            "verified",
            "goal_achieved",
            "evidence_id",
            "reason",
        } <= outcome.keys():
            raise ValueError(f"scenario {scenario_id!r} has no complete recorded outcome")
        if not isinstance(outcome["verified"], bool) or not isinstance(outcome["goal_achieved"], bool):
            raise ValueError(f"scenario {scenario_id!r} has an invalid recorded outcome")
        scenario["recorded_outcome"] = outcome
    if set(recorded_outcomes) != scenario_ids:
        raise ValueError("recorded outcomes must match replay scenario IDs exactly")
    _assert_sanitized(manifest)
    return manifest


def run_replays(scenarios: Sequence[dict[str, Any]]) -> list[ReplayResult]:
    """Replay every fixture through the controller or its policy/resolver safety boundary."""

    results: list[ReplayResult] = []
    for case in scenarios:
        repetitions = case.get("repetitions", 1)
        if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
            raise ValueError(f"scenario {case['id']!r} has invalid repetitions")
        for iteration in range(1, repetitions + 1):
            results.append(_run_one_replay(case, iteration))
    return results


def build_acceptance_report(
    results: Sequence[ReplayResult], compatibility: dict[str, bool]
) -> dict[str, Any]:
    """Apply the non-negotiable replay and public-contract promotion gates."""

    general = [result for result in results if result.category == "general"]
    volume = [result for result in results if result.category == "volume"]
    unsafe_action_count = sum(result.unsafe_coordinate_count for result in results)
    unsupported_dispatch_count = sum(result.unsupported_dispatch_count for result in results)
    general_completion_rate = (
        sum(result.completed for result in general) / len(general) if general else 0.0
    )
    volume_repetitions_complete = bool(volume) and all(result.completed for result in volume)
    gates = {
        "unsafe_coordinates": unsafe_action_count == 0,
        "unsupported_dispatch": unsupported_dispatch_count == 0,
        "volume_repetitions": volume_repetitions_complete,
        "general_completion": general_completion_rate >= 0.90,
        "http_compatibility": compatibility.get("http", False),
        "websocket_compatibility": compatibility.get("websocket", False),
    }
    return {
        "passed": all(gates.values()),
        "scenario_count": len(results),
        "general_completion_rate": general_completion_rate,
        "unsafe_action_count": unsafe_action_count,
        "unsupported_dispatch_count": unsupported_dispatch_count,
        "volume_repetitions_complete": volume_repetitions_complete,
        "compatibility": compatibility,
        "failed_gates": [name for name, passed in gates.items() if not passed],
        "results": [result.to_dict() for result in results],
    }


def _run_one_replay(case: dict[str, Any], iteration: int) -> ReplayResult:
    mode = case.get("mode", "controller")
    if mode == "inspection":
        return _run_inspection_replay(case, iteration)
    if mode == "grounding_failure":
        return _run_grounding_failure_replay(case, iteration)
    if mode in {"controller", "repeated_state"}:
        return _run_controller_replay(case, iteration)
    raise ValueError(f"scenario {case['id']!r} has unsupported replay mode {mode!r}")


def _run_inspection_replay(case: dict[str, Any], iteration: int) -> ReplayResult:
    observation = _observation(case, after=False)
    policy = Policy(decision_provider=lambda _: _decision_payload(case["action"]))
    decision = policy.decide(policy.plan(case["goal"], observation), observation, [])
    action = resolve_action(decision.intent, observation)
    return _result(
        case,
        iteration,
        action_class=action.kind.value,
        verified=False,
        completed=False,
        recovery="inspection",
        coordinates=(),
    )


def _run_grounding_failure_replay(case: dict[str, Any], iteration: int) -> ReplayResult:
    observation = _observation(case, after=False)
    intent = _intent(case["action"])
    try:
        resolve_action(intent, observation)
    except ActionResolutionError:
        return _result(
            case,
            iteration,
            action_class="RECOVERY:grounding",
            verified=False,
            completed=False,
            recovery=FailureClass.GROUNDING.value,
            coordinates=(),
        )
    raise AssertionError(f"scenario {case['id']!r} should reject unsafe grounding")


def _run_controller_replay(case: dict[str, Any], iteration: int) -> ReplayResult:
    before = _observation(case, after=False)
    repeated = case["mode"] == "repeated_state"
    after = before if repeated else _observation(case, after=True)
    observer = _QueuedObserver([before, before, after, after, after, after] if repeated else [before, before, after, after])
    dispatcher = _RecordingDispatcher(case, before.width, before.height)
    intent = _intent(case["action"])
    policy = _ReplayPolicy(case, intent, route_count=3 if repeated else 1)

    recorded_outcome = case["recorded_outcome"]

    def semantic_judge(
        goal: str,
        expected_effect: str,
        action: GroundedAction,
        observed_before: Observation,
        observed_after: Observation,
        comparison: object,
    ) -> SemanticVerdict:
        del goal, expected_effect, action, observed_before, comparison
        if observed_after.device_state.get("recorded_replay_outcome") != recorded_outcome[
            "evidence_id"
        ]:
            return SemanticVerdict(
                matched=False,
                reason="recorded post-action evidence is unavailable",
                evidence=["recorded_replay_outcome=missing"],
                confidence=0.0,
            )
        return SemanticVerdict(
            matched=recorded_outcome["verified"],
            goal_achieved=recorded_outcome["goal_achieved"],
            reason=recorded_outcome["reason"],
            evidence=[f"recorded_evidence={recorded_outcome['evidence_id']}"],
            confidence=1.0 if recorded_outcome["verified"] else 0.0,
        )

    controller = ClosedLoopController(
        policy=policy,
        verifier=Verifier(goal=case["goal"], semantic_judge=semantic_judge),
        observe=observer,
        dispatch=dispatcher,
        poll_interval_s=0.0,
        max_settle_polls=2,
    )
    result = asyncio.run(controller.run(case["goal"], 3 if repeated else 1))
    last_outcome = result.outcomes[-1] if result.outcomes else None
    recovery = _outcome_failure(last_outcome) or (
        result.failure_class.value if result.failure_class else None
    )
    verified = bool(last_outcome and last_outcome.verification and last_outcome.verification.verified)
    if repeated:
        action_class = f"RECOVERY:{recovery}"
    elif dispatcher.actions:
        action_class = dispatcher.actions[-1].kind.value
    else:
        action_class = f"RECOVERY:{recovery or FailureClass.GROUNDING.value}"
    return _result(
        case,
        iteration,
        action_class=action_class,
        verified=verified,
        completed=result.completed,
        recovery=recovery,
        coordinates=tuple(dispatcher.coordinates),
        unsafe_coordinate_count=dispatcher.unsafe_coordinate_count,
        unsupported_dispatch_count=dispatcher.unsupported_dispatch_count,
    )


def _result(
    case: dict[str, Any],
    iteration: int,
    *,
    action_class: str,
    verified: bool,
    completed: bool,
    recovery: str | None,
    coordinates: tuple[tuple[int, int], ...],
    unsafe_coordinate_count: int = 0,
    unsupported_dispatch_count: int = 0,
) -> ReplayResult:
    return ReplayResult(
        scenario_id=case["id"],
        iteration=iteration,
        category=case["category"],
        action_class=action_class,
        verified=verified,
        completed=completed,
        recovery=recovery,
        unsafe_coordinate_count=unsafe_coordinate_count,
        unsupported_dispatch_count=unsupported_dispatch_count,
        coordinates=coordinates,
    )


def _intent(raw_action: dict[str, Any]) -> ActionIntent:
    return _ACTION_INTENT.validate_python(raw_action)


def _decision_payload(action: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": action,
        "target_evidence": "The fixture records a disputed visual target.",
        "confidence": 0.9,
        "alternate_element_ids": [],
    }


def _observation(case: dict[str, Any], *, after: bool) -> Observation:
    elements = [ScreenElement.model_validate(element) for element in case["parser_elements"]]
    device_state: dict[str, Any] = {}
    hierarchy = case.get("native_hierarchy_snapshot")
    if isinstance(hierarchy, str) and hierarchy:
        device_state["ui_hierarchy_xml"] = hierarchy
    packages = case.get("installed_packages")
    if isinstance(packages, list):
        device_state["installed_packages"] = packages
    if after:
        device_state["recorded_replay_outcome"] = case["recorded_outcome"]["evidence_id"]
    screenshot_ref = case.get("after_screenshot_ref", case["screenshot_ref"]) if after else case[
        "screenshot_ref"
    ]
    image = _load_recorded_image(screenshot_ref)
    return Observation(
        observation_id=f"{case['id']}-{'after' if after else 'before'}",
        width=image.width,
        height=image.height,
        image=image,
        device_state=device_state,
        elements=elements,
    )


def _outcome_failure(outcome: object | None) -> str | None:
    failure_class = getattr(outcome, "failure_class", None)
    return failure_class.value if failure_class is not None else None


def _reference_path(reference: object, *, allowed_suffixes: tuple[str, ...] = (".png",)) -> Path:
    """Resolve an allowlisted ``output1`` artifact without allowing path escape or data copies."""

    if not isinstance(reference, str):
        raise ValueError("replay screenshot references must be strings")
    relative, _, _ = reference.partition("#")
    if not relative.startswith("output1/"):
        raise ValueError("replay fixtures must retain an output1 screenshot reference")
    path = (PROJECT_ROOT / relative).resolve()
    output_root = (PROJECT_ROOT / "output1").resolve()
    if (
        output_root not in path.parents
        or path.suffix.casefold() not in allowed_suffixes
        or not path.is_file()
    ):
        raise ValueError("replay artifact references must resolve to allowlisted output1 files")
    return path


def _load_recorded_image(reference: object) -> Any:
    with Image.open(_reference_path(reference)) as image:
        return image.convert("RGB").copy()


def _assert_sanitized(value: object, path: str = "$") -> None:
    """Reject identifiers and credential-like keys anywhere in a fixture tree."""

    sensitive_keys = {
        "deviceid",
        "serial",
        "requestid",
        "apikey",
        "token",
        "password",
        "authorization",
        "credential",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"replay manifest key at {path} must be a string")
            normalized_key = "".join(character for character in key.casefold() if character.isalnum())
            if any(sensitive in normalized_key for sensitive in sensitive_keys):
                raise ValueError(f"replay manifest contains sensitive field {path}.{key}")
            _assert_sanitized(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_sanitized(child, f"{path}[{index}]")


def _run_compatibility_suite(target: str) -> bool:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", target, "-v"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stdout)
        sys.stderr.write(completed.stderr)
    return completed.returncode == 0


def _compatibility_results() -> dict[str, bool]:
    return {
        "http": (
            _run_compatibility_suite("tests.test_api_compatibility")
            and _run_compatibility_suite(
                "tests.test_replay_regressions.BackendTransportCompatibilityTests."
                "test_http_health_route_is_available_through_asgi"
            )
        ),
        "websocket": _run_compatibility_suite(
            "tests.test_replay_regressions.BackendTransportCompatibilityTests."
            "test_websocket_replays_a_task_event_through_asgi"
        ),
    }


def run_live_device_acceptance(device: str) -> bool:
    """Run live checks only for the serial explicitly supplied by the operator."""

    if not device.strip():
        raise ValueError("a non-empty Android device serial is required")
    environment = {**os.environ, "ANDROID_E2E_DEVICE": device}
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "tests.emulator.test_android_acceptance", "-v"],
        cwd=PROJECT_ROOT,
        check=False,
        env=environment,
        capture_output=True,
        text=True,
    )
    output = f"{getattr(completed, 'stdout', '')}\n{getattr(completed, 'stderr', '')}"
    return completed.returncode == 0 and "skipped" not in output.casefold()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-only", action="store_true", help="run deterministic replay gates only")
    parser.add_argument("--device", help="explicit Android serial for opt-in live acceptance")
    args = parser.parse_args(argv)
    if args.replay_only and args.device:
        parser.error("--replay-only and --device cannot be used together")

    results = run_replays(load_replay_manifest()["scenarios"])
    report = build_acceptance_report(results, _compatibility_results())
    device_passed = True
    if args.device:
        device_passed = run_live_device_acceptance(args.device)
        report["device_acceptance_passed"] = device_passed
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] and device_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
