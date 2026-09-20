"""Deterministic replay coverage for closed-loop Android safety regressions."""

from __future__ import annotations

import copy
import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

def _load_acceptance_module(loader: Callable[[str], object] = import_module) -> object | None:
    """Allow an absent planned runner, but never hide an error from one of its dependencies."""

    try:
        return loader("scripts.run_acceptance")
    except ModuleNotFoundError as error:
        if error.name not in {"scripts", "scripts.run_acceptance"}:
            raise
        return None


_acceptance = _load_acceptance_module()


class AcceptanceModuleLoaderTests(unittest.TestCase):
    def test_transitive_module_import_failure_is_not_hidden(self) -> None:
        """A missing runner dependency must fail rather than masquerade as an absent runner."""

        def fail_for_dependency(_: str) -> object:
            raise ModuleNotFoundError("No module named 'missing_dependency'", name="missing_dependency")

        with self.assertRaisesRegex(ModuleNotFoundError, "missing_dependency"):
            _load_acceptance_module(fail_for_dependency)


def _runner_attribute(name: str) -> Any:
    """Return a planned public replay API, failing clearly until it is implemented."""

    if _acceptance is None:
        return None
    return getattr(_acceptance, name, None)


class ReplayRegressionTests(unittest.TestCase):
    """The production regression these tests catch is unsafe replay handling."""

    def _require_runner(self, name: str) -> Any:
        attribute = _runner_attribute(name)
        self.assertIsNotNone(attribute, f"scripts.run_acceptance must define {name}")
        return attribute

    def test_sanitized_manifest_covers_each_known_failure_class(self) -> None:
        """Dropping a known replay class must make the acceptance corpus fail loudly."""

        load_replay_manifest = self._require_runner("load_replay_manifest")
        manifest = load_replay_manifest()
        scenarios = manifest["scenarios"]
        by_id = {scenario["id"]: scenario for scenario in scenarios}

        self.assertEqual(
            {
                "wrong_icon_label",
                "wrong_bbox",
                "missing_native_hierarchy",
                "repeated_unchanged_state",
                "crop_coordinate_restoration",
                "adb_success_wrong_semantic_effect",
            },
            {
                scenario_id
                for scenario_id in by_id
                if by_id[scenario_id]["category"] == "regression"
            },
        )
        self.assertTrue(
            all(
                isinstance(scenario["screenshot_ref"], str)
                and scenario["screenshot_ref"].startswith("output1/")
                for scenario in scenarios
            )
        )
        self.assertTrue(
            all("device_id" not in scenario and "serial" not in scenario for scenario in scenarios)
        )

    def test_every_replay_uses_the_expected_safe_action_or_recovery(self) -> None:
        """A changed policy, resolver, or controller must not silently dispatch an unsafe replay."""

        load_replay_manifest = self._require_runner("load_replay_manifest")
        run_replays = self._require_runner("run_replays")
        scenarios = load_replay_manifest()["scenarios"]
        results = run_replays(scenarios)
        expected = {scenario["id"]: scenario for scenario in scenarios}

        self.assertEqual(sum(scenario.get("repetitions", 1) for scenario in scenarios), len(results))
        for result in results:
            scenario = expected[result.scenario_id]
            self.assertEqual(0, result.unsafe_coordinate_count, result.scenario_id)
            self.assertEqual(0, result.unsupported_dispatch_count, result.scenario_id)
            self.assertEqual(scenario["expected_action_class"], result.action_class)
            self.assertEqual(
                scenario["expected_verification_result"],
                result.verified,
                result.scenario_id,
            )
            self.assertEqual(scenario.get("expected_recovery"), result.recovery)

        by_id = {result.scenario_id: result for result in results}
        self.assertEqual("RECOVERY:grounding", by_id["wrong_bbox"].action_class)
        self.assertEqual("RECOVERY:stalled", by_id["repeated_unchanged_state"].action_class)
        self.assertEqual("wrong-effect", by_id["adb_success_wrong_semantic_effect"].recovery)
        self.assertIn((280, 240), by_id["crop_coordinate_restoration"].coordinates)

    def test_acceptance_report_enforces_replay_safety_and_completion_gates(self) -> None:
        """A passing report must represent zero unsafe dispatches and 90% general completion."""

        load_replay_manifest = self._require_runner("load_replay_manifest")
        run_replays = self._require_runner("run_replays")
        build_acceptance_report = self._require_runner("build_acceptance_report")
        results = run_replays(load_replay_manifest()["scenarios"])
        report = build_acceptance_report(results, {"http": True, "websocket": True})

        self.assertTrue(report["passed"])
        self.assertEqual(len(results), report["scenario_count"])
        self.assertEqual(0, report["unsafe_action_count"])
        self.assertEqual(0, report["unsupported_dispatch_count"])
        self.assertEqual(0.9, report["general_completion_rate"])
        self.assertTrue(report["volume_repetitions_complete"])
        self.assertEqual({"http": True, "websocket": True}, report["compatibility"])

    def test_acceptance_report_rejects_each_failed_promotion_gate(self) -> None:
        """Every mandatory gate must independently turn a passing acceptance report red."""

        load_replay_manifest = self._require_runner("load_replay_manifest")
        run_replays = self._require_runner("run_replays")
        build_acceptance_report = self._require_runner("build_acceptance_report")
        results = run_replays(load_replay_manifest()["scenarios"])
        general_index = next(index for index, result in enumerate(results) if result.category == "general")
        volume_index = next(index for index, result in enumerate(results) if result.category == "volume")
        variants = {
            "unsafe_coordinates": ([replace(results[0], unsafe_coordinate_count=1)], {"http": True, "websocket": True}),
            "unsupported_dispatch": ([replace(results[0], unsupported_dispatch_count=1)], {"http": True, "websocket": True}),
            "volume_repetitions": ([replace(results[volume_index], completed=False)], {"http": True, "websocket": True}),
            "general_completion": ([replace(results[general_index], completed=False)], {"http": True, "websocket": True}),
            "http_compatibility": ([], {"http": False, "websocket": True}),
            "websocket_compatibility": ([], {"http": True, "websocket": False}),
        }

        for gate, (replacements, compatibility) in variants.items():
            candidate = list(results)
            for replacement in replacements:
                candidate[candidate.index(next(result for result in candidate if result.scenario_id == replacement.scenario_id))] = replacement
            report = build_acceptance_report(candidate, compatibility)
            with self.subTest(gate=gate):
                self.assertFalse(report["passed"])
                self.assertIn(gate, report["failed_gates"])

    def test_replay_execution_uses_recorded_outcomes_not_assertion_fields(self) -> None:
        """Changing an expected assertion must not alter what the controller replays."""

        load_replay_manifest = self._require_runner("load_replay_manifest")
        run_replays = self._require_runner("run_replays")
        scenario = copy.deepcopy(
            next(item for item in load_replay_manifest()["scenarios"] if item["id"] == "general_tap_verified")
        )
        scenario["recorded_outcome"] = {
            "verified": True,
            "goal_achieved": True,
            "evidence_id": "test-recorded-success",
            "reason": "the recorded effect is present",
        }
        scenario["expected_verification_result"] = False

        result = run_replays([scenario])[0]

        self.assertTrue(result.verified)
        self.assertTrue(result.completed)

    def test_replay_loads_the_referenced_recorded_screenshot(self) -> None:
        """A replay must use recorded pixels rather than fabricating a blank image."""

        load_replay_manifest = self._require_runner("load_replay_manifest")
        run_replays = self._require_runner("run_replays")
        scenario = next(
            item for item in load_replay_manifest()["scenarios"] if item["id"] == "general_tap_verified"
        )
        with patch.object(_acceptance.Image, "open", wraps=_acceptance.Image.open) as image_open:
            run_replays([scenario])

        self.assertGreaterEqual(image_open.call_count, 2)

    def test_manifest_rejects_nested_sensitive_trace_fields(self) -> None:
        """Sensitive values must be rejected at every manifest depth, not only the scenario root."""

        load_replay_manifest = self._require_runner("load_replay_manifest")
        manifest = copy.deepcopy(load_replay_manifest())
        manifest["scenarios"][0]["parser_elements"][0]["metadata"] = {"request_id": "secret"}
        with tempfile.TemporaryDirectory() as temporary_directory:
            manifest_path = Path(temporary_directory) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_replay_manifest(manifest_path)

    def test_manifest_rejects_a_parser_reference_outside_output1(self) -> None:
        """Unused parser-reference metadata must not become a path-traversal escape hatch."""

        load_replay_manifest = self._require_runner("load_replay_manifest")
        manifest = copy.deepcopy(load_replay_manifest())
        manifest["scenarios"][0]["parser_ref"] = "outside/unapproved-trace.json#elements[0]"
        with tempfile.TemporaryDirectory() as temporary_directory:
            manifest_path = Path(temporary_directory) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_replay_manifest(manifest_path)

    def test_websocket_event_envelope_remains_json_serializable(self) -> None:
        """The event payload replayed over WebSocket must retain its public envelope."""

        from app.backend.models import AgentEvent

        event = AgentEvent(
            eventId="event-replay-contract",
            taskId="task-replay-contract",
            sequence=1,
            timestamp="2026-09-19T00:00:00+00:00",
            stage="acting",
            type="action_executed",
            title="Safe replay action",
            metadata={"failure_class": "wrong-effect"},
        )

        self.assertEqual(
            {
                "eventId",
                "taskId",
                "sequence",
                "timestamp",
                "stage",
                "type",
                "title",
                "description",
                "subgoalId",
                "subgoalIndex",
                "confidence",
                "reasoning",
                "screenshotUrl",
                "screenshotBase64",
                "metadata",
            },
            set(event.to_dict()),
        )

    def test_live_acceptance_is_run_only_for_an_explicit_device(self) -> None:
        """The acceptance CLI must never select or touch a device implicitly."""

        run_live_device_acceptance = self._require_runner("run_live_device_acceptance")
        with patch("scripts.run_acceptance.subprocess.run") as run:
            run.return_value.returncode = 0
            self.assertTrue(run_live_device_acceptance("emulator-replay"))

        command = run.call_args.args[0]
        self.assertEqual(
            [
                _acceptance.sys.executable,
                "-m",
                "unittest",
                "tests.emulator.test_android_acceptance",
                "-v",
            ],
            command,
        )
        self.assertEqual("emulator-replay", run.call_args.kwargs["env"]["ANDROID_E2E_DEVICE"])

    def test_live_acceptance_rejects_an_all_skipped_device_suite(self) -> None:
        """An unavailable device must not be reported as a passing live acceptance run."""

        run_live_device_acceptance = self._require_runner("run_live_device_acceptance")
        with patch("scripts.run_acceptance.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "OK (skipped=5)"
            run.return_value.stderr = ""
            self.assertFalse(run_live_device_acceptance("emulator-replay"))

    def test_acceptance_uses_asgi_http_and_websocket_compatibility_checks(self) -> None:
        """The report must require transport-level checks in addition to legacy API contracts."""

        compatibility_results = self._require_runner("_compatibility_results")
        with patch("scripts.run_acceptance._run_compatibility_suite", return_value=True) as run:
            self.assertEqual({"http": True, "websocket": True}, compatibility_results())

        self.assertEqual(
            [
                unittest.mock.call("tests.test_api_compatibility"),
                unittest.mock.call(
                    "tests.test_replay_regressions.BackendTransportCompatibilityTests."
                    "test_http_health_route_is_available_through_asgi"
                ),
                unittest.mock.call(
                    "tests.test_replay_regressions.BackendTransportCompatibilityTests."
                    "test_websocket_replays_a_task_event_through_asgi"
                ),
            ],
            run.call_args_list,
        )


class BackendTransportCompatibilityTests(unittest.TestCase):
    """Exercise the actual ASGI routes, not only their underlying Python handlers."""

    def test_http_health_route_is_available_through_asgi(self) -> None:
        from fastapi.testclient import TestClient
        from app.backend import backend

        original_client = backend.omniparser_client
        backend.omniparser_client = None
        try:
            with TestClient(backend.app) as client:
                response = client.get("/health")
        finally:
            backend.omniparser_client = original_client

        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ok"}, response.json())

    def test_websocket_replays_a_task_event_through_asgi(self) -> None:
        from fastapi.testclient import TestClient
        from app.backend import backend
        from app.backend.event_emitter import EventEmitter
        from app.backend.models import AgentEvent
        from app.backend.task_manager import TaskManager

        task_manager = TaskManager()
        event = AgentEvent(
            eventId="event-websocket-contract",
            taskId="task-websocket-contract",
            sequence=1,
            timestamp="2026-09-19T00:00:00+00:00",
            stage="acting",
            type="action_executed",
            title="Replay event",
            metadata={"failure_class": "wrong-effect"},
        )

        async def arrange() -> str:
            state = await task_manager.create_task("replay websocket event")
            await task_manager.append_event(state.task_id, event)
            return state.task_id

        task_id = asyncio.run(arrange())
        original_task_manager = backend.task_manager
        original_emitter = backend.emitter
        original_client = backend.omniparser_client
        backend.task_manager = task_manager
        backend.emitter = EventEmitter()
        backend.omniparser_client = None
        try:
            with TestClient(backend.app) as client:
                with client.websocket_connect(f"/ws/task/{task_id}") as websocket:
                    received = websocket.receive_json()
        finally:
            backend.task_manager = original_task_manager
            backend.emitter = original_emitter
            backend.omniparser_client = original_client

        self.assertEqual(event.to_dict(), received)

if __name__ == "__main__":
    unittest.main()
