"""Behavioral tests for the ADB transport safety boundary."""

from __future__ import annotations

import subprocess
import unittest

from execution.android_device import AndroidDevice
from execution.models import ActionKind, GroundedAction


class RecordingRunner:
    """Small ADB boundary fake that records actual command requests."""

    def __init__(self, package_output: str = "") -> None:
        self.calls: list[tuple[str, ...]] = []
        self.package_output = package_output

    def __call__(self, command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        stdout = self.package_output if command[-3:] == ("pm", "list", "packages") else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")


class AndroidDeviceTests(unittest.TestCase):
    """The production changes these tests catch are unsafe ADB dispatches."""

    def test_open_app_rejects_package_not_in_registry(self) -> None:
        """An unregistered package must never be launched from model output."""
        runner = RecordingRunner(package_output="package:com.android.settings\n")
        device = AndroidDevice(command_runner=runner)

        result = device.execute(
            GroundedAction(
                kind=ActionKind.OPEN_APP,
                package="com.example.invented",
                expected_effect="open the invented app",
            )
        )

        self.assertFalse(result.success)
        self.assertIn("not installed", result.error)
        self.assertFalse(any("monkey" in command for command in runner.calls))

    def test_system_key_rejects_non_allowlisted_key(self) -> None:
        """Forged grounded actions must not bypass the system-key allowlist."""
        runner = RecordingRunner()
        device = AndroidDevice(command_runner=runner)

        result = device.execute(
            GroundedAction(
                kind=ActionKind.SYSTEM_KEY,
                key="POWER",
                expected_effect="turn off display",
            )
        )

        self.assertFalse(result.success)
        self.assertIn("not allowlisted", result.error)
        self.assertEqual([], runner.calls)

    def test_input_requires_focus_before_text_dispatch(self) -> None:
        """Text must not be sent when tapping did not establish input focus."""
        runner = RecordingRunner()
        device = AndroidDevice(
            command_runner=runner,
            focus_checker=lambda: False,
            sleep_fn=lambda _: None,
        )

        result = device.execute(
            GroundedAction(
                kind=ActionKind.INPUT,
                point=(250, 400),
                text="secret value",
                expected_effect="enter the secret value",
            )
        )

        self.assertFalse(result.success)
        self.assertIn("focus", result.error)
        self.assertTrue(any(command[2:5] == ("input", "tap", "250") for command in runner.calls))
        self.assertFalse(any(command[2:4] == ("input", "text") for command in runner.calls))

    def test_inspect_region_is_non_dispatching(self) -> None:
        """An inspection request must stay inside the controller and never invoke ADB."""
        runner = RecordingRunner()
        device = AndroidDevice(command_runner=runner)

        result = device.execute(
            GroundedAction(
                kind=ActionKind.INSPECT_REGION,
                element_id="vision-icon",
                point=(250, 400),
                internal=True,
                expected_effect="gather target evidence",
            )
        )

        self.assertTrue(result.success)
        self.assertEqual([], runner.calls)

    def test_internal_flag_cannot_suppress_a_real_tap(self) -> None:
        """Only INSPECT_REGION, not a mutable flag, may bypass device dispatch."""
        runner = RecordingRunner()
        device = AndroidDevice(command_runner=runner)

        result = device.execute(
            GroundedAction(
                kind=ActionKind.TAP,
                point=(250, 400),
                internal=True,
                expected_effect="open the selected setting",
            )
        )

        self.assertTrue(result.success)
        self.assertTrue(any(command[2:4] == ("input", "tap") for command in runner.calls))


if __name__ == "__main__":
    unittest.main()
