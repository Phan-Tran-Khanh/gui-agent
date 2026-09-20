"""Persist visual evidence for every closed-loop action attempt."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .models import (
    ActionIntent,
    GroundedAction,
    Observation,
    TransportResult,
    VerificationResult,
)


def save_action_evidence(
    root: str | Path,
    *,
    task_id: str,
    step_index: int,
    goal: str,
    intent: ActionIntent | None,
    action: GroundedAction | None,
    transport: TransportResult | None,
    verification: VerificationResult | None,
    before: Observation | None,
    after: Observation | None,
    public_prefix: str | None = None,
) -> dict[str, Any]:
    """Save raw/annotated before-after images and a JSON action manifest."""

    directory = Path(root) / task_id / f"step-{step_index:03d}"
    directory.mkdir(parents=True, exist_ok=True)

    files: dict[str, Path] = {}
    for phase, observation in (("before", before), ("after", after)):
        if observation is None or observation.image is None:
            continue
        raw_path = directory / f"{phase}.png"
        annotated_path = directory / f"{phase}-annotated.png"
        observation.image.convert("RGB").save(raw_path, format="PNG")
        _annotate_observation(observation, action).save(annotated_path, format="PNG")
        files[phase] = raw_path
        files[f"{phase}_annotated"] = annotated_path

    manifest = {
        "task_id": task_id,
        "step_index": step_index,
        "goal": goal,
        "intent": _model_payload(intent),
        "action": _model_payload(action),
        "transport": _model_payload(transport),
        "verification": _model_payload(verification),
        "before": _observation_payload(before),
        "after": _observation_payload(after),
        "action_marker": _action_marker(action, before),
        "files": {name: path.name for name, path in files.items()},
    }
    manifest_path = directory / "action.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    files["manifest"] = manifest_path

    relative_files = {
        name: f"{task_id}/step-{step_index:03d}/{path.name}"
        for name, path in files.items()
    }
    public_files = (
        {
            name: f"{public_prefix.rstrip('/')}/{relative_path}"
            for name, relative_path in relative_files.items()
        }
        if public_prefix
        else {}
    )
    return {
        "directory": str(directory),
        "files": {name: str(path) for name, path in files.items()},
        "relative_files": relative_files,
        "urls": public_files,
        "manifest": manifest,
    }


def _annotate_observation(observation: Observation, action: GroundedAction | None) -> Image.Image:
    image = observation.image.convert("RGB").copy()
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for index, element in enumerate(observation.elements):
        box = _pixel_bounds(element.bounds, width, height)
        color = _element_color(element.source, element.interactive, element.requires_inspection)
        draw.rectangle(box, outline=color, width=3)
        label = f"{index} {element.text or element.role}"
        _draw_label(draw, box[0], box[1], label, color, width)

    marker = _action_marker(action, observation)
    target_bounds = marker.get("target_bounds")
    if target_bounds:
        draw.rectangle(tuple(target_bounds), outline="#ff00ff", width=6)
    point = marker.get("point")
    if point:
        _draw_crosshair(draw, tuple(point), width, height, "#ff00ff")
    start = marker.get("start")
    end = marker.get("end")
    if start and end:
        draw.line([tuple(start), tuple(end)], fill="#00ffff", width=6)
        _draw_crosshair(draw, tuple(start), width, height, "#00ffff")
        _draw_crosshair(draw, tuple(end), width, height, "#00ffff")

    action_label = marker.get("label")
    if action_label:
        draw.rectangle((0, 0, min(width, 520), 28), fill="#111111")
        draw.text((6, 6), action_label, fill="white")
    return image


def _draw_label(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, color: str, width: int) -> None:
    text = label[:48]
    text_width = min(width - x, max(40, len(text) * 7 + 8))
    top = max(0, y - 18)
    draw.rectangle((x, top, min(width, x + text_width), y), fill=color)
    draw.text((x + 3, top + 2), text, fill="white")


def _draw_crosshair(
    draw: ImageDraw.ImageDraw,
    point: tuple[int, int],
    width: int,
    height: int,
    color: str,
) -> None:
    x, y = point
    draw.line((max(0, x - 14), y, min(width - 1, x + 14), y), fill=color, width=4)
    draw.line((x, max(0, y - 14), x, min(height - 1, y + 14)), fill=color, width=4)
    draw.ellipse((x - 7, y - 7, x + 7, y + 7), outline=color, width=3)


def _pixel_bounds(bounds: tuple[float, float, float, float], width: int, height: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bounds
    return (
        max(0, min(width - 1, round(x1 * width))),
        max(0, min(height - 1, round(y1 * height))),
        max(0, min(width - 1, round(x2 * width))),
        max(0, min(height - 1, round(y2 * height))),
    )


def _element_color(source: str, interactive: bool, requires_inspection: bool) -> str:
    if requires_inspection:
        return "#ff3b30"
    if interactive:
        return "#00d084"
    if source == "vision":
        return "#ff9f1c"
    if source == "fused":
        return "#00a8ff"
    return "#888888"


def _action_marker(action: GroundedAction | None, observation: Observation | None) -> dict[str, Any]:
    if action is None:
        return {}
    marker: dict[str, Any] = {
        "label": action.kind.value,
        "element_id": action.element_id,
        "point": list(action.point) if action.point is not None else None,
        "start": list(action.start) if action.start is not None else None,
        "end": list(action.end) if action.end is not None else None,
    }
    if observation is not None and action.element_id:
        target = next(
            (element for element in observation.elements if element.element_id == action.element_id),
            None,
        )
        if target is not None:
            marker["target_bounds"] = list(_pixel_bounds(target.bounds, observation.width, observation.height))
    if action.point is not None:
        marker["label"] = f"{action.kind.value} @ ({action.point[0]}, {action.point[1]})"
    elif action.start is not None and action.end is not None:
        marker["label"] = (
            f"{action.kind.value} ({action.start[0]}, {action.start[1]})"
            f" -> ({action.end[0]}, {action.end[1]})"
        )
    return marker


def _observation_payload(observation: Observation | None) -> dict[str, Any] | None:
    if observation is None:
        return None
    return {
        "observation_id": observation.observation_id,
        "dimensions": [observation.width, observation.height],
        "foreground_app": observation.device_state.get("foreground_app"),
        "parser_request_id": observation.device_state.get("parser_request_id"),
        "parser_metadata": observation.device_state.get("parser_metadata", {}),
        "elements": [
            {
                "element_id": element.element_id,
                "bounds": list(element.bounds),
                "pixel_bounds": list(_pixel_bounds(element.bounds, observation.width, observation.height)),
                "text": element.text,
                "role": element.role,
                "source": element.source,
                "interactive": element.interactive,
                "requires_inspection": element.requires_inspection,
                "metadata": _json_safe(element.metadata),
            }
            for element in observation.elements
        ],
    }


def _model_payload(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    serializer = getattr(value, "model_dump", None)
    return serializer(mode="json") if callable(serializer) else None


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)
