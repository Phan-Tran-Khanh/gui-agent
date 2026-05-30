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
import io
import json
import logging
import mimetypes
import time
import uuid
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


def _build_multipart(image_bytes: bytes, filename: str) -> Tuple[bytes, str]:
    boundary = f"----guiagent-{uuid.uuid4().hex}"
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    header_lines = [
        f"--{boundary}",
        f'Content-Disposition: form-data; name="image"; filename="{filename}"',
        f"Content-Type: {mime}",
        "",
    ]
    prefix = "\r\n".join(header_lines).encode("utf-8") + b"\r\n"
    suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return prefix + image_bytes + suffix, f"multipart/form-data; boundary={boundary}"


def _parse_raw_element(raw: Dict[str, Any], fallback_idx: int) -> ParsedElement:
    bbox_raw = raw.get("bbox", [0.0, 0.0, 0.0, 0.0])
    return ParsedElement(
        idx=int(raw.get("idx", fallback_idx)),
        type=str(raw.get("type", "text")),
        bbox=(
            float(bbox_raw[0]),
            float(bbox_raw[1]),
            float(bbox_raw[2]),
            float(bbox_raw[3]),
        ),
        interactivity=bool(raw.get("interactivity", False)),
        content=raw.get("content") or None,
        source=raw.get("source") or None,
    )


def _call_omniparser_sync(
    base_url: str,
    image_bytes: bytes,
    timeout_sec: float,
    retry_count: int,
    retry_backoff_ms: int,
) -> Dict[str, Any]:
    body, content_type = _build_multipart(image_bytes, "screen.png")
    url = f"{base_url.rstrip('/')}/api/parse"
    last_error: Optional[Exception] = None

    for attempt in range(retry_count + 1):
        try:
            req = request.Request(url=url, data=body, method="POST")
            req.add_header("Content-Type", content_type)
            with request.urlopen(req, timeout=timeout_sec) as resp:
                return json.loads(resp.read().decode("utf-8"))
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
    )

    latency_ms = (time.perf_counter() - started) * 1000

    raw_elements: List[Dict[str, Any]] = payload.get("parsed_content_list", [])
    elements = [_parse_raw_element(elem, idx) for idx, elem in enumerate(raw_elements)]
    interactable = [e for e in elements if e.interactivity]

    # Prefer OmniParser's own screen_info; compile locally if absent
    screen_info = (
        str(payload["screen_info"])
        if payload.get("screen_info")
        else _compile_screen_info(interactable)
    )

    return OmniParserResult(
        elements=elements,
        interactable=interactable,
        width=int(payload.get("width", image.width)),
        height=int(payload.get("height", image.height)),
        latency_ms=latency_ms,
        screen_info=screen_info,
    )


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

async def ground(image: Image.Image) -> Tuple[Image.Image, str]:
    """
    Ground a screenshot using OmniParser.

    Calls OmniParser, filters interactable UI elements, annotates the image
    with numbered bounding boxes (Step 3), and returns the enhanced image
    together with a set-of-mark prompt for MLLM injection (Step 2).

    Args:
        image: Current device screenshot as a PIL Image.

    Returns:
        Tuple of:
        - enhanced_image: PIL Image with coloured bboxes and ID badges drawn
                          on every interactable element.
        - prompt: Set-of-mark text string, e.g.:
                  "ID: 0, Text: Settings
                   ID: 1, Icon: home"
    """
    config = Config()

    if config.mock_mode:
        _logger.info("[MOCK] Returning synthetic grounding result")
        result = _mock_result(image)
    else:
        result = await _fetch_omniparser(image, config)

    _logger.info(
        "Grounded: %d total / %d interactable elements (%.1f ms)",
        len(result.elements), len(result.interactable), result.latency_ms,
    )

    # Step 3: annotate
    enhanced = annotate(image, result.interactable)

    return enhanced, result.screen_info
