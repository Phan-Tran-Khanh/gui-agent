"""Fuse OmniParser vision and UIAutomator metadata into safe observations."""

from __future__ import annotations

import hashlib
import math
import re
import uuid
import xml.etree.ElementTree as element_tree
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from PIL import Image

from grounder.grounder import parse_screen as default_parse_screen
from grounder.models import OmniParserResult, ParsedElement

from .models import Observation, ScreenElement


ParseScreen = Callable[[Image.Image], Awaitable[OmniParserResult]]
DeviceStateProvider = Callable[[], dict[str, Any]]
NormalizedBounds = tuple[float, float, float, float]
PixelBounds = tuple[int, int, int, int]


@dataclass(frozen=True)
class NativeElement:
    """Normalized, device-native UI metadata from one UIAutomator node."""

    bounds: NormalizedBounds
    text: str
    role: str
    resource_id: str
    interactive: bool
    metadata: dict[str, Any]


class PerceptionEngine:
    """Produce canonical observations without treating visual hints as clicks."""

    def __init__(
        self,
        parse_screen: ParseScreen = default_parse_screen,
        device_state_provider: DeviceStateProvider | None = None,
    ) -> None:
        self._parse_screen = parse_screen
        self._device_state_provider = device_state_provider

    async def observe(
        self, image: Image.Image, device_state: dict[str, Any] | None = None
    ) -> Observation:
        """Fuse one parser response with optional UIAutomator XML for this image."""

        provider_state = (
            self._device_state_provider() if self._device_state_provider is not None else {}
        )
        state = dict(provider_state)
        state.update(device_state or {})
        result = await self._parse_screen(image)
        hierarchy_xml = state.get("ui_hierarchy_xml")
        native_elements, native_diagnostics = parse_ui_hierarchy(
            hierarchy_xml, image.width, image.height
        )
        elements, vision_diagnostics = fuse_elements(result.elements, native_elements)
        diagnostics = native_diagnostics + vision_diagnostics
        state.update(
            {
                "parser_request_id": result.request_id,
                "parser_latency_ms": result.latency_ms,
                "parser_metadata": dict(result.parser_metadata),
                "perception_diagnostics": diagnostics,
            }
        )
        return Observation(
            observation_id=result.request_id or uuid.uuid4().hex,
            width=image.width,
            height=image.height,
            image=image,
            device_state=state,
            elements=elements,
        )


def parse_ui_hierarchy(
    hierarchy_xml: str | None, width: int, height: int
) -> tuple[list[NativeElement], list[dict[str, str]]]:
    """Normalize valid UIAutomator nodes against the exact screenshot pixels."""

    if not hierarchy_xml:
        return [], []
    try:
        root = element_tree.fromstring(hierarchy_xml)
    except element_tree.ParseError:
        return [], [{"source": "uiautomator", "reason": "invalid XML", "label": ""}]

    elements: list[NativeElement] = []
    diagnostics: list[dict[str, str]] = []
    for node in root.iter("node"):
        attributes = dict(node.attrib)
        label = _native_label(attributes)
        pixel_bounds = _parse_pixel_bounds(attributes.get("bounds", ""))
        bounds = _normalize_native_bounds(pixel_bounds, width, height)
        if bounds is None:
            diagnostics.append(
                {
                    "source": "uiautomator",
                    "reason": "invalid or out-of-screen bounds",
                    "label": label,
                }
            )
            continue
        class_name = attributes.get("class", "")
        role = class_name.rsplit(".", maxsplit=1)[-1] or "unknown"
        enabled = _as_bool(attributes.get("enabled", "true"))
        interactive = enabled and any(
            _as_bool(attributes.get(name, "false"))
            for name in ("clickable", "editable", "scrollable")
        )
        elements.append(
            NativeElement(
                bounds=bounds,
                text=label,
                role=role,
                resource_id=attributes.get("resource-id", ""),
                interactive=interactive,
                metadata={
                    "resource_id": attributes.get("resource-id", ""),
                    "class": class_name,
                    "package": attributes.get("package", ""),
                    "content_description": attributes.get("content-desc", ""),
                    "clickable": _as_bool(attributes.get("clickable", "false")),
                    "editable": _as_bool(attributes.get("editable", "false")),
                    "scrollable": _as_bool(attributes.get("scrollable", "false")),
                    "enabled": enabled,
                    "focused": _as_bool(attributes.get("focused", "false")),
                    "pixel_bounds": pixel_bounds,
                },
            )
        )
    return elements, diagnostics


def fuse_elements(
    vision_elements: list[ParsedElement], native_elements: list[NativeElement]
) -> tuple[list[ScreenElement], list[dict[str, str]]]:
    """Fuse source records, preferring native semantics and safe geometry."""

    diagnostics: list[dict[str, str]] = []
    valid_vision: list[ParsedElement] = []
    for vision in vision_elements:
        if not getattr(vision, "bbox_valid", True) or not _valid_bounds(vision.bbox):
            diagnostics.append(
                {
                    "source": "vision",
                    "reason": getattr(vision, "diagnostic", None) or "invalid bounds",
                    "label": vision.content or "",
                }
            )
            continue
        valid_vision.append(vision)

    elements: list[ScreenElement] = []
    unmatched_vision = set(range(len(valid_vision)))
    resource_id_counts = Counter(
        native.resource_id for native in native_elements if native.resource_id
    )
    resource_id_occurrences: dict[str, int] = {}
    for native in native_elements:
        native_element_id = _native_element_id(
            native, resource_id_counts, resource_id_occurrences
        )
        match_index = _best_overlap(native.bounds, valid_vision, unmatched_vision)
        if match_index is None:
            elements.append(_native_screen_element(native, native_element_id))
            continue

        vision = valid_vision[match_index]
        unmatched_vision.remove(match_index)
        vision_label = vision.content or ""
        disputed = _labels_conflict(native.text, vision_label)
        native_label_missing = not native.text.strip()
        elements.append(
            ScreenElement(
                element_id=native_element_id,
                bounds=native.bounds,
                text=native.text or vision_label,
                role=native.role,
                source="fused",
                interactive=native.interactive,
                requires_inspection=disputed or (native_label_missing and bool(vision_label)),
                metadata={
                    **native.metadata,
                    "parser_index": vision.idx,
                    "vision_type": vision.type,
                    "vision_content": vision_label,
                    "vision_source": vision.source or "",
                    "disputed": disputed,
                    "native_label_missing": native_label_missing,
                },
            )
        )

    for index in sorted(unmatched_vision):
        vision = valid_vision[index]
        role = vision.type.lower() or "unknown"
        is_icon = role == "icon"
        elements.append(
            ScreenElement(
                element_id=_stable_id("vision", role, vision.bbox, vision.content or ""),
                bounds=vision.bbox,
                text=vision.content or "",
                role=role,
                source="vision",
                interactive=vision.interactivity and not is_icon,
                requires_inspection=is_icon,
                metadata={
                    "parser_index": vision.idx,
                    "parser_interactivity": vision.interactivity,
                    "vision_source": vision.source or "",
                    "vision_is_icon": is_icon,
                },
            )
        )
    return elements, diagnostics


def _native_screen_element(native: NativeElement, element_id: str) -> ScreenElement:
    return ScreenElement(
        element_id=element_id,
        bounds=native.bounds,
        text=native.text,
        role=native.role,
        source="uiautomator",
        interactive=native.interactive,
        metadata=native.metadata,
    )


def _best_overlap(
    native_bounds: NormalizedBounds,
    vision_elements: list[ParsedElement],
    unmatched_vision: set[int],
) -> int | None:
    candidates = [
        (index, _iou(native_bounds, vision_elements[index].bbox))
        for index in unmatched_vision
    ]
    if not candidates:
        return None
    index, overlap = max(
        candidates,
        key=lambda candidate: (
            candidate[1],
            -vision_elements[candidate[0]].idx,
            -candidate[0],
        ),
    )
    return index if overlap >= 0.50 else None


def _iou(first: NormalizedBounds, second: NormalizedBounds) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = (first[2] - first[0]) * (first[3] - first[1])
    second_area = (second[2] - second[0]) * (second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


def _parse_pixel_bounds(value: str) -> PixelBounds | None:
    match = re.fullmatch(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", value)
    if match is None:
        return None
    return tuple(int(group) for group in match.groups())


def _normalize_native_bounds(
    pixel_bounds: PixelBounds | None, width: int, height: int
) -> NormalizedBounds | None:
    if pixel_bounds is None or width <= 0 or height <= 0:
        return None
    x1, y1, x2, y2 = pixel_bounds
    bounds = (x1 / width, y1 / height, x2 / width, y2 / height)
    return bounds if _valid_bounds(bounds) else None


def _valid_bounds(bounds: tuple[float, float, float, float]) -> bool:
    x1, y1, x2, y2 = bounds
    return all(math.isfinite(value) for value in bounds) and (
        0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0
    )


def _native_label(attributes: dict[str, str]) -> str:
    return (
        attributes.get("text", "").strip()
        or attributes.get("content-desc", "").strip()
        or attributes.get("resource-id", "").rsplit("/", maxsplit=1)[-1]
    )


def _labels_conflict(native_label: str, vision_label: str) -> bool:
    return bool(native_label.strip() and vision_label.strip()) and (
        native_label.strip().casefold() != vision_label.strip().casefold()
    )


def _stable_id(
    source: str,
    role: str,
    bounds: NormalizedBounds,
    text: str,
    resource_id: str = "",
) -> str:
    if resource_id:
        return resource_id
    material = "|".join(
        (source, role, *(f"{value:.6f}" for value in bounds), text.strip().casefold())
    )
    return f"{source}:{hashlib.sha256(material.encode('utf-8')).hexdigest()[:16]}"


def _native_element_id(
    native: NativeElement,
    resource_id_counts: Counter[str],
    resource_id_occurrences: dict[str, int],
) -> str:
    """Use a resource ID directly only when it identifies one native node."""

    if not native.resource_id:
        return _stable_id("uiautomator", native.role, native.bounds, native.text)
    if resource_id_counts[native.resource_id] == 1:
        return native.resource_id

    occurrence = resource_id_occurrences.get(native.resource_id, 0)
    resource_id_occurrences[native.resource_id] = occurrence + 1
    hashed = _stable_id("uiautomator", native.role, native.bounds, native.text)
    return f"{native.resource_id}#{occurrence}:{hashed.rsplit(':', maxsplit=1)[-1]}"


def _as_bool(value: str) -> bool:
    return value.strip().casefold() == "true"
