"""Live Android acceptance checks, deliberately excluded without an explicit device serial."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
import unittest
import xml.etree.ElementTree as element_tree
from typing import Callable, Iterable

from PIL import Image

from execution.android_device import AndroidDevice
from execution.models import ActionKind, GroundedAction


DEVICE_SERIAL = os.getenv("ANDROID_E2E_DEVICE", "").strip()


def _bounds_center(raw_bounds: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", raw_bounds)
    if match is None:
        return None
    left, top, right, bottom = (int(value) for value in match.groups())
    if left >= right or top >= bottom:
        return None
    return ((left + right) // 2, (top + bottom) // 2)


def _media_volume_index(output: str) -> int | None:
    """Extract the STREAM_MUSIC index from standard ``dumpsys audio`` output."""

    music = re.search(r"(?:STREAM_MUSIC|streamType=3).*?(?:index|mIndex)=(\d+)", output, re.DOTALL)
    return int(music.group(1)) if music else None


@dataclass(frozen=True)
class _DeviceState:
    image: Image.Image
    hierarchy: str | None
    foreground_package: str | None


def _observable_transition(before: _DeviceState, after: _DeviceState) -> bool:
    """Require a device-observable state change, never just a successful ADB return."""

    return (
        before.foreground_package != after.foreground_package
        or before.hierarchy != after.hierarchy
        or before.image.size != after.image.size
        or before.image.tobytes() != after.image.tobytes()
    )


def _hierarchy_contains_text(hierarchy: str | None, text: str) -> bool:
    if not hierarchy:
        return False
    try:
        nodes = element_tree.fromstring(hierarchy).iter("node")
    except element_tree.ParseError:
        return False
    needle = text.casefold()
    return any(
        needle in node.attrib.get(attribute, "").casefold()
        for node in nodes
        for attribute in ("text", "content-desc", "hint")
    )


def _hierarchy_contains_package(hierarchy: str | None, package: str) -> bool:
    if not hierarchy:
        return False
    try:
        nodes = element_tree.fromstring(hierarchy).iter("node")
    except element_tree.ParseError:
        return False
    return any(node.attrib.get("package") == package for node in nodes)


def _restore_media_volume(
    original_index: int,
    read_index: Callable[[], int | None],
    dispatch: Callable[[str], bool],
) -> int:
    """Return media volume to its exact observed pre-test index or fail loudly."""

    current_index = read_index()
    if current_index is None:
        raise AssertionError("STREAM_MUSIC index is unavailable during restoration")
    key = "VOLUME_UP" if current_index < original_index else "VOLUME_DOWN"
    for _ in range(abs(original_index - current_index)):
        if not dispatch(key):
            raise AssertionError(f"could not dispatch {key} while restoring media volume")
    restored_index = read_index()
    if restored_index != original_index:
        raise AssertionError(
            f"media volume was not restored: expected {original_index}, got {restored_index}"
        )
    return restored_index


class AndroidAcceptanceHelperTests(unittest.TestCase):
    def test_observable_transition_requires_a_changed_screen_or_hierarchy(self) -> None:
        unchanged = _DeviceState(
            image=Image.new("RGB", (2, 2), "white"),
            hierarchy='<hierarchy><node text="Before" /></hierarchy>',
            foreground_package="example.before",
        )
        changed_hierarchy = _DeviceState(
            image=Image.new("RGB", (2, 2), "white"),
            hierarchy='<hierarchy><node text="After" /></hierarchy>',
            foreground_package="example.before",
        )

        self.assertFalse(_observable_transition(unchanged, unchanged))
        self.assertTrue(_observable_transition(unchanged, changed_hierarchy))

    def test_native_hierarchy_oracle_matches_text_and_package(self) -> None:
        hierarchy = (
            '<hierarchy><node package="com.android.systemui" '
            'content-desc="Quick settings" text="gui-agent-e2e" /></hierarchy>'
        )

        self.assertTrue(_hierarchy_contains_text(hierarchy, "gui-agent-e2e"))
        self.assertTrue(_hierarchy_contains_package(hierarchy, "com.android.systemui"))
        self.assertFalse(_hierarchy_contains_text(hierarchy, "missing"))

    def test_media_volume_restore_returns_to_the_original_index(self) -> None:
        current = 3
        dispatched: list[str] = []

        def read_index() -> int | None:
            return current

        def dispatch(key: str) -> bool:
            nonlocal current
            dispatched.append(key)
            current += 1 if key == "VOLUME_UP" else -1
            return True

        self.assertEqual(5, _restore_media_volume(5, read_index, dispatch))
        self.assertEqual(["VOLUME_UP", "VOLUME_UP"], dispatched)


@unittest.skipUnless(DEVICE_SERIAL, "set ANDROID_E2E_DEVICE to enable live Android acceptance")
class AndroidAcceptanceTests(unittest.TestCase):
    """Device mutations only run after the operator passes a specific serial to the runner."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.device = AndroidDevice(serial=DEVICE_SERIAL)
        status = subprocess.run(
            ["adb", "-s", DEVICE_SERIAL, "get-state"],
            capture_output=True,
            check=False,
            text=True,
        )
        if status.returncode != 0 or status.stdout.strip() != "device":
            raise unittest.SkipTest(f"Android device {DEVICE_SERIAL!r} is not available")
        screenshot = cls.device.capture_screenshot()
        if screenshot is None:
            raise unittest.SkipTest("ADB screenshot capture is unavailable")
        cls.width, cls.height = screenshot.size

    def _audio_dump(self) -> str:
        completed = subprocess.run(
            ["adb", "-s", DEVICE_SERIAL, "shell", "dumpsys", "audio"],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        return completed.stdout

    def _device_state(self) -> _DeviceState:
        screenshot = self.device.capture_screenshot()
        self.assertIsNotNone(screenshot, "ADB screenshot capture is unavailable during verification")
        foreground = self.device.foreground_app() or {}
        return _DeviceState(
            image=screenshot,
            hierarchy=self.device.ui_hierarchy_xml(),
            foreground_package=foreground.get("package"),
        )

    def _assert_observable_transition(
        self, before: _DeviceState, after: _DeviceState, expected_effect: str
    ) -> None:
        self.assertTrue(
            _observable_transition(before, after),
            f"no observable device effect after {expected_effect}",
        )

    def _dispatch_system_key(self, key: str) -> bool:
        result = self.device.execute(
            GroundedAction(
                kind=ActionKind.SYSTEM_KEY,
                key=key,
                expected_effect="restore the original media volume after acceptance verification",
            )
        )
        return result.success

    def _find_center(self, class_terms: Iterable[str]) -> tuple[int, int] | None:
        hierarchy = self.device.ui_hierarchy_xml()
        if not hierarchy:
            return None
        try:
            nodes = element_tree.fromstring(hierarchy).iter("node")
        except element_tree.ParseError:
            return None
        terms = tuple(term.casefold() for term in class_terms)
        for node in nodes:
            node_class = node.attrib.get("class", "").casefold()
            if any(term in node_class for term in terms):
                center = _bounds_center(node.attrib.get("bounds", ""))
                if center is not None:
                    return center
        return None

    def test_settings_volume_adjustment_and_hardware_fallback_use_audio_oracle(self) -> None:
        """Settings is opened first; a reversible hardware fallback is measured only by dumpsys audio."""

        packages = self.device.installed_packages()
        if not packages or "com.android.settings" not in packages:
            self.skipTest("the selected device does not expose com.android.settings")
        opened = self.device.execute(
            GroundedAction(
                kind=ActionKind.OPEN_APP,
                package="com.android.settings",
                expected_effect="open Android Settings before volume adjustment",
            )
        )
        self.assertTrue(opened.success, opened.error)
        settings_state = self._device_state()
        self.assertEqual(
            "com.android.settings",
            settings_state.foreground_package,
            "opening Settings must be verified from foreground application state",
        )

        before = _media_volume_index(self._audio_dump())
        if before is None or before <= 0:
            self.skipTest("STREAM_MUSIC index is unavailable or already at its lower bound")
        lowered_attempted = False
        try:
            lowered_attempted = True
            lowered = self.device.execute(
                GroundedAction(
                    kind=ActionKind.SYSTEM_KEY,
                    key="VOLUME_DOWN",
                    expected_effect="temporarily lower media volume through the fallback",
                )
            )
            self.assertTrue(lowered.success, lowered.error)
            after_lower = _media_volume_index(self._audio_dump())
            self.assertIsNotNone(after_lower)
            self.assertLess(after_lower, before)
        finally:
            if lowered_attempted:
                self.assertEqual(
                    before,
                    _restore_media_volume(
                        before,
                        lambda: _media_volume_index(self._audio_dump()),
                        self._dispatch_system_key,
                    ),
                )

    def test_quick_settings_navigation_has_a_system_ui_effect(self) -> None:
        """A top-edge gesture must expose Android System UI, not merely return from ADB."""

        before = self._device_state()
        top_inset = max(1, self.height // 100)
        try:
            result = self.device.execute(
                GroundedAction(
                    kind=ActionKind.EDGE_SWIPE,
                    start=(self.width // 2, top_inset),
                    end=(self.width // 2, max(1, self.height // 2)),
                    expected_effect="open Quick Settings",
                )
            )
            self.assertTrue(result.success, result.error)
            after = self._device_state()
            self._assert_observable_transition(before, after, "opening Quick Settings")
            self.assertTrue(
                _hierarchy_contains_package(after.hierarchy, "com.android.systemui"),
                "Quick Settings must expose a System UI hierarchy",
            )
        finally:
            self.device.execute(
                GroundedAction(
                    kind=ActionKind.BACK,
                    expected_effect="dismiss the system shade after quick-settings verification",
                )
            )

    def test_scroll_has_an_observable_effect_on_a_native_scroll_target(self) -> None:
        """A scroll must change the displayed native surface, not merely dispatch successfully."""

        scroll_center = self._find_center(("scrollview", "recyclerview", "listview"))
        if scroll_center is None:
            self.skipTest("the current screen has no discovered native scroll target")
        start_x, start_y = scroll_center
        end_y = max(1, start_y - min(self.height // 3, start_y - 1))
        if end_y == start_y:
            self.skipTest("the discovered scroll target has no safe upward swipe distance")
        before = self._device_state()
        scroll = self.device.execute(
            GroundedAction(
                kind=ActionKind.SCROLL,
                start=(start_x, start_y),
                end=(start_x, end_y),
                expected_effect="scroll the discovered native surface",
            )
        )
        self.assertTrue(scroll.success, scroll.error)
        self._assert_observable_transition(before, self._device_state(), "scrolling the native surface")

    def test_typing_verifies_the_acceptance_marker_in_native_hierarchy(self) -> None:
        """Text input is accepted only when the target hierarchy exposes the marker afterward."""

        input_center = self._find_center(("edittext",))
        if input_center is None:
            self.skipTest("the current screen has no discovered native text input")
        marker = "gui-agent-e2e"
        before = self._device_state()
        typed = self.device.execute(
            GroundedAction(
                kind=ActionKind.INPUT,
                point=input_center,
                text=marker,
                expected_effect="enter the acceptance marker into the discovered native text field",
            )
        )
        self.assertTrue(typed.success, typed.error)
        after = self._device_state()
        self._assert_observable_transition(before, after, "typing the acceptance marker")
        self.assertTrue(
            _hierarchy_contains_text(after.hierarchy, marker),
            "the native hierarchy must contain the marker after text input",
        )

    def test_long_press_has_an_observable_native_effect(self) -> None:
        """A discovered native target must expose an observable context effect after a long press."""

        long_press_center = self._find_center(("textview", "button"))
        if long_press_center is None:
            self.skipTest("the current screen has no discovered native long-press target")
        before = self._device_state()
        try:
            long_press = self.device.execute(
                GroundedAction(
                    kind=ActionKind.LONG_PRESS,
                    point=long_press_center,
                    duration_ms=500,
                    expected_effect="open a context affordance for the discovered native target",
                )
            )
            self.assertTrue(long_press.success, long_press.error)
            self._assert_observable_transition(
                before, self._device_state(), "opening a native context affordance"
            )
        finally:
            self.device.execute(
                GroundedAction(
                    kind=ActionKind.BACK,
                    expected_effect="dismiss the native context affordance after verification",
                )
            )

    def test_slider_movement_has_an_observable_effect_when_explicitly_enabled(self) -> None:
        """A slider is mutated only with explicit consent and must visibly change its native surface."""

        if os.getenv("ANDROID_E2E_ALLOW_SLIDER_MUTATION", "").casefold() != "true":
            self.skipTest("set ANDROID_E2E_ALLOW_SLIDER_MUTATION=true for slider mutation")
        slider_center = self._find_center(("seekbar",))
        if slider_center is None:
            self.skipTest("no native SeekBar is visible on the selected device")
        before = self._device_state()
        moved = self.device.execute(
            GroundedAction(
                kind=ActionKind.SET_SLIDER,
                point=slider_center,
                expected_effect="move the currently visible native slider",
            )
        )
        self.assertTrue(moved.success, moved.error)
        self._assert_observable_transition(before, self._device_state(), "moving the native slider")


if __name__ == "__main__":
    unittest.main()
