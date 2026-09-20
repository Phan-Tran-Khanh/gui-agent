"""Behavioral tests for fusing OmniParser and UIAutomator perception."""

from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from pydantic import TypeAdapter

from execution.action_resolver import ActionResolutionError, resolve_action
from execution.models import ActionIntent
from execution.perception import PerceptionEngine
from grounder.grounder import _call_omniparser_sync, ground, parse_screen
from grounder.models import OmniParserResult, ParsedElement


FIXTURES = Path(__file__).parent / "fixtures" / "perception"
ACTION_INTENT_ADAPTER = TypeAdapter(ActionIntent)


def _result_from_fixture(name: str) -> OmniParserResult:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    elements = [
        ParsedElement(
            idx=item["idx"],
            type=item["type"],
            bbox=tuple(item["bbox"]),
            interactivity=item["interactivity"],
            content=item.get("content"),
            source=item.get("source"),
        )
        for item in payload["elements"]
    ]
    return OmniParserResult(
        elements=elements,
        interactable=[element for element in elements if element.interactivity],
        width=1000,
        height=2000,
        latency_ms=payload["latency_ms"],
        request_id=payload["request_id"],
    )


class PerceptionEngineTests(unittest.TestCase):
    """These tests catch unsafe source precedence and targetability regressions."""

    @staticmethod
    def _observe(result: OmniParserResult, hierarchy_xml: str | None = None):
        async def parse(_: Image.Image) -> OmniParserResult:
            return result

        engine = PerceptionEngine(parse_screen=parse)
        state = {} if hierarchy_xml is None else {"ui_hierarchy_xml": hierarchy_xml}
        return asyncio.run(engine.observe(Image.new("RGB", (1000, 2000)), state))

    def test_native_label_and_bounds_win_over_conflicting_icon_caption(self) -> None:
        """A visual caption must not override native text, bounds, or resource identity."""
        observation = self._observe(
            _result_from_fixture("native_wins.json"),
            (FIXTURES / "native_wins.xml").read_text(encoding="utf-8"),
        )

        self.assertEqual(1, len(observation.elements))
        element = observation.elements[0]
        self.assertEqual("com.android.settings:id/wifi_toggle", element.element_id)
        self.assertEqual("Wi-Fi", element.text)
        self.assertEqual((0.1, 0.2, 0.4, 0.4), element.bounds)
        self.assertEqual("Switch", element.role)
        self.assertTrue(element.interactive)
        self.assertEqual("com.android.settings", element.metadata["package"])
        self.assertEqual("", element.metadata["content_description"])
        self.assertTrue(element.metadata["clickable"])
        self.assertFalse(element.metadata["editable"])
        self.assertFalse(element.metadata["scrollable"])
        self.assertTrue(element.metadata["enabled"])
        self.assertFalse(element.metadata["focused"])
        self.assertEqual((100, 400, 400, 800), element.metadata["pixel_bounds"])

    def test_device_state_provider_supplies_native_xml_and_foreground_app(self) -> None:
        """A standard observation can fuse read-only device inspection state."""
        result = _result_from_fixture("native_wins.json")

        async def parse(_: Image.Image) -> OmniParserResult:
            return result

        engine = PerceptionEngine(
            parse_screen=parse,
            device_state_provider=lambda: {
                "ui_hierarchy_xml": (FIXTURES / "native_wins.xml").read_text(
                    encoding="utf-8"
                ),
                "foreground_app": {
                    "package": "com.android.settings",
                    "activity": "com.android.settings.Settings",
                },
            },
        )

        observation = asyncio.run(engine.observe(Image.new("RGB", (1000, 2000))))

        self.assertEqual("Wi-Fi", observation.elements[0].text)
        self.assertEqual(
            {
                "package": "com.android.settings",
                "activity": "com.android.settings.Settings",
            },
            observation.device_state["foreground_app"],
        )

    def test_device_state_is_snapshotted_before_parser_request(self) -> None:
        """Native bounds must belong to the screenshot sent to the parser."""
        result = _result_from_fixture("native_wins.json")
        events: list[str] = []

        async def parse(_: Image.Image) -> OmniParserResult:
            events.append("parser")
            return result

        def state_provider() -> dict[str, str]:
            events.append("state")
            return {
                "ui_hierarchy_xml": (FIXTURES / "native_wins.xml").read_text(
                    encoding="utf-8"
                )
            }

        engine = PerceptionEngine(
            parse_screen=parse, device_state_provider=state_provider
        )
        asyncio.run(engine.observe(Image.new("RGB", (1000, 2000))))

        self.assertEqual(["state", "parser"], events)

    def test_noninteractive_heading_is_preserved_as_context(self) -> None:
        """A useful native heading must stay visible to policy without becoming a target."""
        result = OmniParserResult(
            elements=[], interactable=[], width=1000, height=2000, latency_ms=0.0
        )
        hierarchy = (
            '<hierarchy><node text="Network &amp; internet" resource-id="" '
            'class="android.widget.TextView" package="com.android.settings" '
            'clickable="false" editable="false" scrollable="false" enabled="true" '
            'focused="false" content-desc="" bounds="[100,100][900,200]" />'
            "</hierarchy>"
        )

        observation = self._observe(result, hierarchy)

        self.assertEqual(1, len(observation.elements))
        self.assertEqual("Network & internet", observation.elements[0].text)
        self.assertFalse(observation.elements[0].interactive)

    def test_invalid_vision_bbox_is_excluded_from_action_targets(self) -> None:
        """An off-screen detector result must survive only as diagnostic context."""
        result = OmniParserResult(
            elements=[
                ParsedElement(
                    idx=7,
                    type="icon",
                    bbox=(-0.1, 0.2, 0.3, 0.4),
                    interactivity=True,
                    content="unsafe icon",
                )
            ],
            interactable=[],
            width=1000,
            height=2000,
            latency_ms=0.0,
        )

        observation = self._observe(result)

        self.assertEqual([], observation.elements)
        self.assertEqual(
            "unsafe icon", observation.device_state["perception_diagnostics"][0]["label"]
        )

    def test_empty_ui_hierarchy_falls_back_to_vision(self) -> None:
        """A custom-rendered screen must retain a safe vision-only inspection target."""
        result = OmniParserResult(
            elements=[
                ParsedElement(
                    idx=3,
                    type="icon",
                    bbox=(0.3, 0.4, 0.5, 0.6),
                    interactivity=True,
                    content="wireless settings",
                )
            ],
            interactable=[],
            width=1000,
            height=2000,
            latency_ms=0.0,
        )

        observation = self._observe(
            result, (FIXTURES / "empty_hierarchy.xml").read_text(encoding="utf-8")
        )

        self.assertEqual(1, len(observation.elements))
        element = observation.elements[0]
        self.assertEqual("wireless settings", element.text)
        self.assertTrue(element.requires_inspection)
        self.assertFalse(element.interactive)

    def test_explicitly_interactive_vision_text_can_be_grounded_without_native_xml(self) -> None:
        """A verified text control remains usable when UIAutomator is unavailable."""
        result = OmniParserResult(
            elements=[
                ParsedElement(
                    idx=4,
                    type="text",
                    bbox=(0.2, 0.3, 0.6, 0.4),
                    interactivity=True,
                    content="Save",
                    source="box_ocr_content_ocr",
                )
            ],
            interactable=[],
            width=1000,
            height=2000,
            latency_ms=0.0,
        )

        observation = self._observe(
            result, (FIXTURES / "empty_hierarchy.xml").read_text(encoding="utf-8")
        )
        element = observation.elements[0]
        self.assertTrue(element.interactive)
        self.assertFalse(element.requires_inspection)
        tap = ACTION_INTENT_ADAPTER.validate_python(
            {
                "kind": "TAP",
                "element_id": element.element_id,
                "expected_effect": "save the form",
            }
        )

        self.assertEqual((400, 700), resolve_action(tap, observation).point)

    def test_overlapping_sources_receive_one_stable_element_id(self) -> None:
        """Repeated fusion of the same native resource must not create duplicate targets."""
        result = _result_from_fixture("native_wins.json")
        hierarchy = (FIXTURES / "native_wins.xml").read_text(encoding="utf-8")

        first = self._observe(result, hierarchy)
        second = self._observe(result, hierarchy)

        self.assertEqual(1, len(first.elements))
        self.assertEqual(first.elements[0].element_id, second.elements[0].element_id)

    def test_duplicate_native_resource_ids_are_disambiguated_for_dispatch(self) -> None:
        """Repeated list-row IDs must never resolve a later row to the first row."""
        result = OmniParserResult(
            elements=[], interactable=[], width=1000, height=2000, latency_ms=0.0
        )
        hierarchy = (
            '<hierarchy>'
            '<node text="First" resource-id="com.example:id/list_row" '
            'class="android.widget.TextView" clickable="true" editable="false" '
            'scrollable="false" enabled="true" focused="false" bounds="[0,200][1000,400]" />'
            '<node text="Second" resource-id="com.example:id/list_row" '
            'class="android.widget.TextView" clickable="true" editable="false" '
            'scrollable="false" enabled="true" focused="false" bounds="[0,600][1000,800]" />'
            "</hierarchy>"
        )

        observation = self._observe(result, hierarchy)
        first, second = observation.elements
        self.assertNotEqual(first.element_id, second.element_id)
        self.assertEqual(2, len({first.element_id, second.element_id}))

        first_tap = ACTION_INTENT_ADAPTER.validate_python(
            {
                "kind": "TAP",
                "element_id": first.element_id,
                "expected_effect": "open the first row",
            }
        )
        second_tap = ACTION_INTENT_ADAPTER.validate_python(
            {
                "kind": "TAP",
                "element_id": second.element_id,
                "expected_effect": "open the second row",
            }
        )
        self.assertEqual((500, 300), resolve_action(first_tap, observation).point)
        self.assertEqual((500, 700), resolve_action(second_tap, observation).point)

    def test_equal_iou_matching_uses_lowest_parser_index(self) -> None:
        """An equal-overlap tie must not depend on unordered set iteration."""
        result = OmniParserResult(
            elements=[
                ParsedElement(
                    idx=9,
                    type="icon",
                    bbox=(0.1, 0.2, 0.4, 0.4),
                    interactivity=True,
                    content="later parser item",
                ),
                ParsedElement(
                    idx=3,
                    type="icon",
                    bbox=(0.1, 0.2, 0.4, 0.4),
                    interactivity=True,
                    content="earlier parser item",
                ),
            ],
            interactable=[],
            width=1000,
            height=2000,
            latency_ms=0.0,
        )

        observation = self._observe(
            result, (FIXTURES / "native_wins.xml").read_text(encoding="utf-8")
        )
        fused = next(element for element in observation.elements if element.source == "fused")

        self.assertEqual(3, fused.metadata["parser_index"])

    def test_unlabeled_native_control_with_visual_caption_requires_inspection(self) -> None:
        """A vision caption cannot make an otherwise unlabeled native control tappable."""
        result = OmniParserResult(
            elements=[
                ParsedElement(
                    idx=8,
                    type="icon",
                    bbox=(0.1, 0.2, 0.4, 0.4),
                    interactivity=True,
                    content="Delete",
                )
            ],
            interactable=[],
            width=1000,
            height=2000,
            latency_ms=0.0,
        )
        hierarchy = (
            '<hierarchy><node text="" content-desc="" resource-id="" '
            'class="android.widget.ImageButton" clickable="true" editable="false" '
            'scrollable="false" enabled="true" focused="false" '
            'bounds="[100,400][400,800]" /></hierarchy>'
        )

        observation = self._observe(result, hierarchy)
        element = observation.elements[0]
        self.assertTrue(element.interactive)
        self.assertTrue(element.requires_inspection)
        tap = ACTION_INTENT_ADAPTER.validate_python(
            {
                "kind": "TAP",
                "element_id": element.element_id,
                "expected_effect": "delete the item",
            }
        )

        with self.assertRaises(ActionResolutionError):
            resolve_action(tap, observation)

    def test_disputed_target_requires_inspection_before_execution(self) -> None:
        """Conflicting source labels must block direct taps but permit inspection."""
        result = OmniParserResult(
            elements=[
                ParsedElement(
                    idx=9,
                    type="icon",
                    bbox=(0.1, 0.2, 0.4, 0.4),
                    interactivity=True,
                    content="Bluetooth",
                )
            ],
            interactable=[],
            width=1000,
            height=2000,
            latency_ms=0.0,
        )
        observation = self._observe(
            result, (FIXTURES / "native_wins.xml").read_text(encoding="utf-8")
        )
        element = observation.elements[0]

        self.assertTrue(element.requires_inspection)
        tap = ACTION_INTENT_ADAPTER.validate_python(
            {
                "kind": "TAP",
                "element_id": element.element_id,
                "expected_effect": "open the Wi-Fi setting",
            }
        )
        with self.assertRaises(ActionResolutionError):
            resolve_action(tap, observation)

        inspection = ACTION_INTENT_ADAPTER.validate_python(
            {
                "kind": "INSPECT_REGION",
                "element_id": element.element_id,
                "expected_effect": "confirm the target icon",
            }
        )
        self.assertTrue(resolve_action(inspection, observation).internal)


class GrounderCompatibilityTests(unittest.TestCase):
    """These tests catch drift from the established legacy grounding boundary."""

    @staticmethod
    def _live_config() -> SimpleNamespace:
        return SimpleNamespace(
            mock_mode=False,
            parse_api_base_url="http://127.0.0.1:8001",
            parse_api_timeout_sec=1.0,
            parse_api_retry_count=0,
            parse_api_retry_backoff_ms=0,
            parse_api_verify_ssl=True,
        )

    def test_parse_screen_keeps_actual_image_dimensions_and_parser_metadata(self) -> None:
        """Server omission or mismatch of dimensions must not alter dispatch geometry."""
        payload = {
            "request_id": "request-123",
            "parser": {"version": "omniparser-v2-yolov9e"},
            "parsed_content_list": [
                {
                    "type": "text",
                    "bbox": [0.1, 0.2, 0.3, 0.4],
                    "interactivity": False,
                    "content": "Wi-Fi",
                    "source": "box_ocr_content_ocr",
                }
            ],
            "width": 720,
            "height": 1600,
        }
        image = Image.new("RGB", (1080, 2400))
        with patch("grounder.grounder._call_omniparser_sync", return_value=payload):
            result = asyncio.run(parse_screen(image, config=self._live_config()))

        self.assertEqual((1080, 2400), (result.width, result.height))
        self.assertEqual("request-123", result.request_id)
        self.assertEqual("omniparser-v2-yolov9e", result.parser_metadata["version"])
        self.assertEqual(1, len(result.elements))

    def test_parse_screen_safely_degrades_malformed_parser_fields(self) -> None:
        """Malformed parser metadata must not create an interactable legacy target."""
        payload = {
            "latency_ms": 7.5,
            "parsed_content_list": [
                {
                    "idx": "not-an-integer",
                    "type": "icon",
                    "bbox": [0.1, 0.2, 0.3, 0.4],
                    "interactivity": "false",
                    "content": {"untrusted": "object"},
                    "source": ["untrusted", "source"],
                },
                {
                    "idx": 1,
                    "type": "icon",
                    "bbox": [-0.1, 0.2, 0.3, 0.4],
                    "interactivity": True,
                    "content": "unsafe target",
                },
            ],
        }
        image = Image.new("RGB", (1000, 2000))
        with patch("grounder.grounder._call_omniparser_sync", return_value=payload):
            result = asyncio.run(parse_screen(image, config=self._live_config()))

        self.assertEqual(7.5, result.latency_ms)
        self.assertEqual(0, result.elements[0].idx)
        self.assertFalse(result.elements[0].interactivity)
        self.assertIsNone(result.elements[0].content)
        self.assertIsNone(result.elements[0].source)
        self.assertFalse(result.elements[1].bbox_valid)
        self.assertEqual([], result.interactable)

    def test_legacy_ground_keeps_annotated_image_prompt_and_interactable_tuple(self) -> None:
        """Refactoring fetch into parse_screen must not break existing tuple consumers."""
        image = Image.new("RGB", (320, 640))
        mock_config = SimpleNamespace(mock_mode=True)
        with patch("grounder.grounder.Config", return_value=mock_config):
            annotated, screen_info, interactable = asyncio.run(ground(image))

        self.assertEqual((320, 640), annotated.size)
        self.assertIn("ID: 0, Text: Settings", screen_info)
        self.assertEqual(3, len(interactable))

    def test_grounder_uses_the_current_json_parse_endpoint(self) -> None:
        """Calling the obsolete route would make the current local service unusable."""

        class Response:
            status = 200

            def read(self) -> bytes:
                return b'{"parsed_content_list": []}'

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        with patch("grounder.grounder.request.urlopen", return_value=Response()) as urlopen:
            _call_omniparser_sync(
                "http://127.0.0.1:8001", b"png-bytes", 1.0, 0, 0, True
            )

        self.assertEqual(
            "http://127.0.0.1:8001/api/parse-json",
            urlopen.call_args.args[0].full_url,
        )


if __name__ == "__main__":
    unittest.main()
