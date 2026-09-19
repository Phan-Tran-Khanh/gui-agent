"""
Grounder: enhances screenshots using OmniParser for MLLM visual grounding.

Exported function
-----------------
    ground(image: Image.Image) -> tuple[Image.Image, str]

---
Usage
---

    from grounder import ground
    from PIL import Image

    image = Image.open("screenshot.png")
    enhanced_image, prompt = await ground(image)

    # enhanced_image — PIL Image with numbered bounding boxes drawn on
    #                  every interactable UI element.
    # prompt         — Set-of-mark text ready for MLLM injection, e.g.:
    #                  "ID: 0, Text: Settings
    #                   ID: 1, Icon: home
    #                   ID: 2, Text: Wi-Fi"

Pipeline
--------
    Step 1  Connect to OmniParser and retrieve the full element list.
    Step 2  Filter to interactable elements; compile set-of-mark prompt.
    Step 3  Annotate the screenshot with numbered bounding boxes.
    Step 4  Return (annotated image, prompt).

Mock mode
---------
    Set MOCK_MODE=true in .env to skip the OmniParser call and return a
    synthetic result — useful for testing without a running OmniParser service.
"""

import asyncio
import base64
import io
import json
import logging
import math
import ssl
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib import error, request

from PIL import Image

from config import Config
from grounder.annotator import annotate
from grounder.models import OmniParserResult, ParsedElement

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step 1: OmniParser HTTP connection
# ---------------------------------------------------------------------------

def _image_to_png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _build_json_body(image_bytes: bytes) -> Tuple[bytes, str]:
    """Encode image as base64 for OmniParser's JSON parsing endpoint."""
    payload = {"base64_image": base64.b64encode(image_bytes).decode("utf-8")}
    return json.dumps(payload).encode("utf-8"), "application/json"


def _parse_raw_element(raw: Dict[str, Any], fallback_idx: int) -> ParsedElement:
    bbox, bbox_valid, diagnostic = _parse_bbox(raw.get("bbox"))
    raw_idx = raw.get("idx", fallback_idx)
    try:
        idx = int(raw_idx)
    except (TypeError, ValueError):
        idx = fallback_idx
    return ParsedElement(
        idx=idx,
        type=str(raw.get("type", "text")),
        bbox=bbox,
        interactivity=_parse_interactivity(raw.get("interactivity", False)),
        content=_parse_optional_text(raw.get("content")),
        source=_parse_optional_text(raw.get("source")),
        bbox_valid=bbox_valid,
        diagnostic=diagnostic,
    )


def _parse_bbox(raw_bbox: Any) -> Tuple[Tuple[float, float, float, float], bool, Optional[str]]:
    """Coerce parser bounds while keeping malformed detections diagnostic-only."""

    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return (0.0, 0.0, 0.0, 0.0), False, "bbox must contain four coordinates"
    try:
        bbox = tuple(float(value) for value in raw_bbox)
    except (TypeError, ValueError):
        return (0.0, 0.0, 0.0, 0.0), False, "bbox coordinates must be numeric"
    x1, y1, x2, y2 = bbox
    if not all(math.isfinite(value) for value in bbox):
        return bbox, False, "bbox coordinates must be finite"
    if not (0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0):
        return bbox, False, "bbox must be normalized, ordered, and non-zero-area"
    return bbox, True, None


def _parse_interactivity(value: Any) -> bool:
    """Accept only explicit parser booleans as actionable intent."""

    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.strip().casefold() == "true"


def _parse_optional_text(value: Any) -> Optional[str]:
    """Retain parser labels only when they satisfy the wire contract."""

    return value or None if isinstance(value, str) else None


def _call_omniparser_sync(
    base_url: str,
    image_bytes: bytes,
    timeout_sec: float,
    retry_count: int,
    retry_backoff_ms: int,
    verify_ssl: bool = True,
) -> Dict[str, Any]:
    body, content_type = _build_json_body(image_bytes)
    url = f"{base_url.rstrip('/')}/api/parse-json"
    last_error: Optional[Exception] = None
    ssl_context = None if verify_ssl else ssl._create_unverified_context()  # pylint: disable=protected-access

    for attempt in range(retry_count + 1):
        try:
            req = request.Request(url=url, data=body, method="POST")
            req.add_header("Content-Type", content_type)
            with request.urlopen(req, timeout=timeout_sec, context=ssl_context) as resp:
                # utf-8-sig strips the BOM if the server includes one
                return json.loads(resp.read().decode("utf-8-sig"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else str(exc)
            last_error = exc
            _logger.warning(
                "OmniParser HTTP %s (attempt %d/%d): %s",
                exc.code, attempt + 1, retry_count + 1, detail,
            )
        except error.URLError as exc:
            last_error = exc
            _logger.warning(
                "OmniParser connection error (attempt %d/%d): %s",
                attempt + 1, retry_count + 1, exc.reason,
            )
        except json.JSONDecodeError as exc:
            last_error = exc
            _logger.warning(
                "OmniParser invalid JSON (attempt %d/%d): %s",
                attempt + 1, retry_count + 1, exc,
            )

        if attempt < retry_count:
            time.sleep(retry_backoff_ms / 1000.0)

    raise ConnectionError(
        f"OmniParser failed after {retry_count + 1} attempt(s): {last_error}"
    ) from last_error


async def _fetch_omniparser(image: Image.Image, config: Config) -> OmniParserResult:
    """Send image to OmniParser and return a parsed OmniParserResult."""
    if not config.parse_api_base_url:
        raise ValueError(
            "PARSE_API_BASE_URL is not configured. "
            "Set it in .env or enable MOCK_MODE=true."
        )

    image_bytes = _image_to_png_bytes(image)
    started = time.perf_counter()

    payload = await asyncio.to_thread(
        _call_omniparser_sync,
        config.parse_api_base_url,
        image_bytes,
        config.parse_api_timeout_sec,
        config.parse_api_retry_count,
        config.parse_api_retry_backoff_ms,
        config.parse_api_verify_ssl,
    )

    if not isinstance(payload, dict):
        raise ValueError("OmniParser response must be a JSON object")

    latency_ms = _parse_latency_ms(payload, (time.perf_counter() - started) * 1000)

    raw_elements = payload.get("parsed_content_list", [])
    if not isinstance(raw_elements, list):
        raw_elements = []
    elements = [
        _parse_raw_element(elem if isinstance(elem, dict) else {"content": str(elem)}, idx)
        for idx, elem in enumerate(raw_elements)
    ]
    interactable = [e for e in elements if e.interactivity and e.bbox_valid]

    # Always compile from interactable-only elements — OmniParser's own
    # screen_info includes non-interactable elements which pollute the MLLM prompt.
    screen_info = _compile_screen_info(interactable)

    return OmniParserResult(
        elements=elements,
        interactable=interactable,
        width=image.width,
        height=image.height,
        latency_ms=latency_ms,
        screen_info=screen_info,
        request_id=payload.get("request_id"),
        parser_metadata=payload.get("parser") if isinstance(payload.get("parser"), dict) else {},
        raw_response=payload,
    )


def _parse_latency_ms(payload: Dict[str, Any], fallback_ms: float) -> float:
    """Read either known server latency format without trusting invalid values."""

    for field, multiplier in (("latency_ms", 1.0), ("latency", 1000.0)):
        if field not in payload:
            continue
        try:
            latency_ms = float(payload[field]) * multiplier
        except (TypeError, ValueError):
            continue
        if math.isfinite(latency_ms) and latency_ms >= 0.0:
            return latency_ms
    return fallback_ms


# ---------------------------------------------------------------------------
# Step 2: Set-of-mark prompt compilation
# ---------------------------------------------------------------------------

def _compile_screen_info(interactable: List[ParsedElement]) -> str:
    """Build a set-of-mark prompt string from interactable elements."""
    lines: List[str] = []
    for elem in interactable:
        label = "Text" if elem.type == "text" else "Icon"
        content = elem.content or ""
        lines.append(f"ID: {elem.idx}, {label}: {content}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Mock fallback
# ---------------------------------------------------------------------------

def _mock_result(image: Image.Image) -> OmniParserResult:
    elements = [
        ParsedElement(
            idx=0, type="text", bbox=(0.1, 0.2, 0.4, 0.25),
            interactivity=True, content="Settings",
        ),
        ParsedElement(
            idx=1, type="icon", bbox=(0.6, 0.8, 0.75, 0.9),
            interactivity=True, content="home",
        ),
        ParsedElement(
            idx=2, type="text", bbox=(0.1, 0.3, 0.6, 0.35),
            interactivity=True, content="Wi-Fi",
        ),
    ]
    return OmniParserResult(
        elements=elements,
        interactable=elements,
        width=image.width,
        height=image.height,
        latency_ms=0.0,
        screen_info=_compile_screen_info(elements),
    )


# ---------------------------------------------------------------------------
# Step 4: Public API
# ---------------------------------------------------------------------------

async def parse_screen(image: Image.Image, config: Optional[Config] = None) -> OmniParserResult:
    """Return the complete OmniParser result for one screenshot."""

    active_config = config or Config()
    if active_config.mock_mode:
        _logger.info("[MOCK] Returning synthetic grounding result")
        result = _mock_result(image)
    else:
        result = await _fetch_omniparser(image, active_config)

    _logger.info(
        "Parsed: %d total / %d interactable elements (%.1f ms)",
        len(result.elements), len(result.interactable), result.latency_ms,
    )
    return result


async def ground(image: Image.Image) -> Tuple[Image.Image, str, List[ParsedElement]]:
    """
    Ground a screenshot using OmniParser.

    Calls OmniParser, filters interactable UI elements, annotates the image
    with numbered bounding boxes (Step 3), and returns the enhanced image,
    set-of-mark prompt, and the interactable element list.

    Args:
        image: Current device screenshot as a PIL Image.

    Returns:
        Tuple of:
        - enhanced_image:  PIL Image with coloured bboxes and ID badges drawn
                           on every interactable element.
        - screen_info:     Set-of-mark text for MLLM injection, e.g.
                           "ID: 0, Text: Settings\nID: 1, Icon: home"
        - interactable:    List[ParsedElement] — interactable elements needed
                           by the executor to resolve element_id → pixel coords.
    """
    result = await parse_screen(image)

    # Step 3: annotate
    enhanced = annotate(image, result.interactable)

    return enhanced, result.screen_info, result.interactable
