"""Behavioral tests for the ADB transport safety boundary."""

from __future__ import annotations

import subprocess
import unittest
from io import BytesIO

from execution.android_device import AndroidDevice
from execution.models import ActionKind, GroundedAction
from PIL import Image


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

    def test_capture_screenshot_decodes_the_actual_png_dimensions(self) -> None:
        """Perception must use the captured pixels rather than a fixed device size."""
        png = BytesIO()
        Image.new("RGB", (321, 654)).save(png, format="PNG")
        calls: list[tuple[str, ...]] = []

        def binary_runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[bytes]:
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, stdout=png.getvalue(), stderr=b"")

        screenshot = AndroidDevice(binary_command_runner=binary_runner).capture_screenshot()

        self.assertIsNotNone(screenshot)
        self.assertEqual((321, 654), screenshot.size)
        self.assertEqual(("adb", "exec-out", "screencap", "-p"), calls[0])

    def test_ui_hierarchy_xml_accepts_a_valid_empty_hierarchy(self) -> None:
        """An empty native tree is valid and must allow vision fallback."""
        calls: list[tuple[str, ...]] = []

        def runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            stdout = "<hierarchy />" if command[-2] == "cat" else "dumped"
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

        hierarchy = AndroidDevice(command_runner=runner).ui_hierarchy_xml()

        self.assertEqual("<hierarchy />", hierarchy)
        self.assertEqual(("adb", "shell", "uiautomator", "dump"), calls[0][:4])
        self.assertTrue(calls[0][-1].startswith("/sdcard/gui_agent_window_"))
        self.assertEqual(calls[0][-1], calls[1][-1])

    def test_ui_hierarchy_xml_uses_unique_remote_paths_per_capture(self) -> None:
        """Concurrent observations must not read a different capture's XML file."""
        dump_paths: list[str] = []

        def runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
            if command[-2] == "cat":
                return subprocess.CompletedProcess(command, 0, stdout="<hierarchy />", stderr="")
            if command[2:4] == ("uiautomator", "dump"):
                dump_paths.append(command[-1])
            return subprocess.CompletedProcess(command, 0, stdout="dumped", stderr="")

        device = AndroidDevice(command_runner=runner)
        self.assertEqual("<hierarchy />", device.ui_hierarchy_xml())
        self.assertEqual("<hierarchy />", device.ui_hierarchy_xml())

        self.assertEqual(2, len(dump_paths))
        self.assertNotEqual(dump_paths[0], dump_paths[1])

    def test_ui_hierarchy_xml_removes_its_generated_remote_file(self) -> None:
        """Continuous perception must not leak one UI dump file per observation."""
        calls: list[tuple[str, ...]] = []

        def runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            stdout = "<hierarchy />" if command[-2] == "cat" else "dumped"
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

        hierarchy = AndroidDevice(command_runner=runner).ui_hierarchy_xml()

        self.assertEqual("<hierarchy />", hierarchy)
        self.assertEqual(
            ("adb", "shell", "rm", "-f", calls[0][-1]),
            calls[-1],
        )

    def test_foreground_app_reads_package_and_activity_from_current_focus(self) -> None:
        """Perception state needs the foreground package/activity beside node metadata."""

        def runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
            self.assertEqual(("adb", "shell", "dumpsys", "window", "windows"), command)
            stdout = (
                "Window #0 Window{deadbeef u0 com.example.old/.OldActivity}\n"
                "mCurrentFocus=Window{a57e4f9 u0 "
                "com.android.settings/com.android.settings.Settings}"
            )
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

        foreground = AndroidDevice(command_runner=runner).foreground_app()

        self.assertEqual(
            {
                "package": "com.android.settings",
                "activity": "com.android.settings.Settings",
            },
            foreground,
        )

    def test_perception_state_collects_hierarchy_and_foreground_app(self) -> None:
        """The device exposes all optional native context in one observation-ready mapping."""

        def runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
            if command[-2] == "cat":
                return subprocess.CompletedProcess(
                    command, 0, stdout="<hierarchy />", stderr=""
                )
            if command[2:] == ("dumpsys", "window", "windows"):
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=(
                        "mCurrentFocus=Window{a57e4f9 u0 "
                        "com.android.settings/.Settings}"
                    ),
                    stderr="",
                )
            return subprocess.CompletedProcess(command, 0, stdout="dumped", stderr="")

        state = AndroidDevice(command_runner=runner).perception_state()

        self.assertEqual("<hierarchy />", state["ui_hierarchy_xml"])
        self.assertEqual(
            {"package": "com.android.settings", "activity": ".Settings"},
            state["foreground_app"],
        )


if __name__ == "__main__":
    unittest.main()
