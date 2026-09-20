"""ADB transport adapter for already-grounded Android actions."""

from __future__ import annotations

import io
import re
import subprocess
import time
import xml.etree.ElementTree as element_tree
from collections.abc import Callable
from typing import Any, Sequence
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from .models import ActionKind, GroundedAction, TransportResult


CommandRunner = Callable[[tuple[str, ...]], subprocess.CompletedProcess[str]]
BinaryCommandRunner = Callable[[tuple[str, ...]], subprocess.CompletedProcess[bytes]]
FocusChecker = Callable[[], bool]
SleepFunction = Callable[[float], None]


class AndroidDevice:
    """Dispatch safe, grounded actions and expose read-only package inspection."""

    _SYSTEM_KEY_CODES = {
        "VOLUME_DOWN": "25",
        "VOLUME_UP": "24",
        "VOLUME_MUTE": "164",
    }

    def __init__(
        self,
        *,
        serial: str | None = None,
        adb_path: str = "adb",
        command_runner: CommandRunner | None = None,
        binary_command_runner: BinaryCommandRunner | None = None,
        focus_checker: FocusChecker | None = None,
        focus_poll_attempts: int = 3,
        sleep_fn: SleepFunction = time.sleep,
    ) -> None:
        self._serial = serial
        self._adb_path = adb_path
        self._command_runner = command_runner or self._run_subprocess
        self._binary_command_runner = binary_command_runner or self._run_binary_subprocess
        self._focus_checker = focus_checker
        self._focus_poll_attempts = focus_poll_attempts
        self._sleep = sleep_fn

    def execute(self, action: GroundedAction) -> TransportResult:
        """Dispatch an action only after its type-specific safety checks pass."""

        if action.kind is ActionKind.INSPECT_REGION:
            return TransportResult(success=True)
        if action.kind is ActionKind.TAP:
            return self._tap(action)
        if action.kind is ActionKind.LONG_PRESS:
            return self._long_press(action)
        if action.kind in {ActionKind.SCROLL, ActionKind.EDGE_SWIPE}:
            return self._swipe(action)
        if action.kind is ActionKind.SET_SLIDER:
            return self._tap(action)
        if action.kind is ActionKind.INPUT:
            return self._input(action)
        if action.kind is ActionKind.BACK:
            return self._run("shell", "input", "keyevent", "4")
        if action.kind is ActionKind.HOME:
            return self._run("shell", "input", "keyevent", "3")
        if action.kind is ActionKind.ENTER:
            return self._run("shell", "input", "keyevent", "66")
        if action.kind is ActionKind.WAIT:
            self._sleep((action.duration_ms or 0) / 1_000)
            return TransportResult(success=True)
        if action.kind is ActionKind.OPEN_APP:
            return self._open_app(action)
        if action.kind is ActionKind.SYSTEM_KEY:
            return self._system_key(action)
        return TransportResult(success=False, error=f"unsupported action kind: {action.kind}")

    def installed_packages(self) -> set[str] | None:
        """Return the device package registry, or ``None`` when it cannot be read."""

        result = self._run("shell", "pm", "list", "packages")
        if not result.success:
            return None
        return {
            line.removeprefix("package:").strip()
            for line in result.stdout.splitlines()
            if line.startswith("package:") and line.removeprefix("package:").strip()
        }

    def capture_screenshot(self) -> Image.Image | None:
        """Capture and decode the exact screenshot used for coordinate grounding."""

        command = self._adb_command(("exec-out", "screencap", "-p"))
        try:
            completed = self._binary_command_runner(command)
        except (OSError, subprocess.SubprocessError):
            return None
        if completed.returncode != 0 or not completed.stdout:
            return None
        try:
            with Image.open(io.BytesIO(completed.stdout)) as image:
                image.load()
                return image.copy()
        except (OSError, UnidentifiedImageError):
            return None

    def ui_hierarchy_xml(self) -> str | None:
        """Return a validated UIAutomator hierarchy without mutating device state."""

        remote_path = f"/sdcard/gui_agent_window_{uuid4().hex}.xml"
        try:
            dumped = self._run("shell", "uiautomator", "dump", remote_path)
            if not dumped.success:
                return None
            hierarchy = self._run("shell", "cat", remote_path)
            if not hierarchy.success:
                return None
            try:
                element_tree.fromstring(hierarchy.stdout)
            except element_tree.ParseError:
                return None
            return hierarchy.stdout
        finally:
            self._run("shell", "rm", "-f", remote_path)

    def foreground_app(self) -> dict[str, str] | None:
        """Return the foreground package/activity when Android exposes one."""

        for args in (
            ("shell", "dumpsys", "window", "windows"),
            ("shell", "dumpsys", "activity", "activities"),
        ):
            result = self._run(*args)
            if not result.success:
                continue
            foreground = _parse_foreground_app(result.stdout)
            if foreground is not None:
                return foreground
        return None

    def perception_state(self) -> dict[str, Any]:
        """Collect optional, read-only metadata for one perception observation."""

        state: dict[str, Any] = {}
        hierarchy_xml = self.ui_hierarchy_xml()
        if hierarchy_xml is not None:
            state["ui_hierarchy_xml"] = hierarchy_xml
        foreground = self.foreground_app()
        if foreground is not None:
            state["foreground_app"] = foreground
        return state

    def _tap(self, action: GroundedAction) -> TransportResult:
        if action.point is None:
            return TransportResult(success=False, error="tap action has no target point")
        x, y = action.point
        return self._run("shell", "input", "tap", str(x), str(y))

    def _long_press(self, action: GroundedAction) -> TransportResult:
        if action.point is None:
            return TransportResult(success=False, error="long-press action has no target point")
        x, y = action.point
        return self._run(
            "shell",
            "input",
            "swipe",
            str(x),
            str(y),
            str(x),
            str(y),
            str(action.duration_ms or 500),
        )

    def _swipe(self, action: GroundedAction) -> TransportResult:
        if action.start is None or action.end is None:
            return TransportResult(success=False, error="swipe action has no start/end coordinates")
        start_x, start_y = action.start
        end_x, end_y = action.end
        return self._run(
            "shell",
            "input",
            "swipe",
            str(start_x),
            str(start_y),
            str(end_x),
            str(end_y),
            str(action.duration_ms or 300),
        )

    def _input(self, action: GroundedAction) -> TransportResult:
        if action.point is None or not action.text:
            return TransportResult(success=False, error="input action needs a target point and text")
        tap_result = self._tap(action)
        if not tap_result.success:
            return tap_result
        if not self._wait_for_focus():
            return TransportResult(
                success=False,
                command=tap_result.command,
                stdout=tap_result.stdout,
                stderr=tap_result.stderr,
                error="input focus was not established after tapping the target",
            )
        return self._run("shell", "input", "text", _escape_adb_text(action.text))

    def _open_app(self, action: GroundedAction) -> TransportResult:
        if not action.package:
            return TransportResult(success=False, error="open-app action has no package")
        packages = self.installed_packages()
        if packages is None:
            return TransportResult(success=False, error="could not inspect the installed package registry")
        if action.package not in packages:
            return TransportResult(
                success=False,
                error=f"package {action.package!r} is not installed on this device",
            )
        return self._run("shell", "monkey", "-p", action.package, "1")

    def _system_key(self, action: GroundedAction) -> TransportResult:
        key_code = self._SYSTEM_KEY_CODES.get(action.key or "")
        if key_code is None:
            return TransportResult(
                success=False,
                error=f"system key {action.key!r} is not allowlisted",
            )
        return self._run("shell", "input", "keyevent", key_code)

    def _wait_for_focus(self) -> bool:
        for attempt in range(self._focus_poll_attempts):
            if self._has_text_focus():
                return True
            if attempt < self._focus_poll_attempts - 1:
                self._sleep(0.1)
        return False

    def _has_text_focus(self) -> bool:
        if self._focus_checker is not None:
            return self._focus_checker()
        result = self._run("shell", "dumpsys", "input_method")
        if not result.success:
            return False
        return "mCurFocusedWindow=null" not in result.stdout and "mCurFocusedWindow" in result.stdout

    def _run(self, *args: str) -> TransportResult:
        command = self._adb_command(args)
        try:
            completed = self._command_runner(command)
        except (OSError, subprocess.SubprocessError) as error:
            return TransportResult(success=False, command=command, error=str(error))
        return TransportResult(
            success=completed.returncode == 0,
            command=command,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            error=None if completed.returncode == 0 else (completed.stderr or "ADB command failed"),
        )

    def _adb_command(self, args: Sequence[str]) -> tuple[str, ...]:
        command = [self._adb_path]
        if self._serial:
            command.extend(("-s", self._serial))
        command.extend(args)
        return tuple(command)

    @staticmethod
    def _run_subprocess(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    @staticmethod
    def _run_binary_subprocess(command: tuple[str, ...]) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(command, capture_output=True, check=False)


def _escape_adb_text(value: str) -> str:
    """Encode whitespace for ``adb shell input text`` without shell interpolation."""

    return value.replace(" ", "%s")


_FOREGROUND_COMPONENT_PATTERN = re.compile(
    r"(?P<package>[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)/"
    r"(?P<activity>\.?[A-Za-z0-9_.$]+)"
)


def _parse_foreground_app(output: str) -> dict[str, str] | None:
    """Extract a package/activity component from standard dumpsys output."""

    focus_markers = (
        "mCurrentFocus",
        "mFocusedApp",
        "mResumedActivity",
        "topResumedActivity",
    )
    for line in output.splitlines():
        if not any(marker in line for marker in focus_markers):
            continue
        match = _FOREGROUND_COMPONENT_PATTERN.search(line)
        if match is not None:
            return {
                "package": match.group("package"),
                "activity": match.group("activity"),
            }
    return None
