"""Data models mirroring the OmniParser output schema."""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class ParsedElement:
    """
    A single UI element detected by OmniParser.

    Fields mirror the TypeScript ParsedElement schema:
        idx           — element index (0-based)
        type          — "text" | "icon"
        bbox          — normalized xyxy [x1, y1, x2, y2] in 0-1 range
        interactivity — True if the element can be interacted with
        content       — text label or icon description (may be None)
        source        — detection source ("box_ocr_content_ocr", etc.)
    """

    idx: int
    type: str
    bbox: Tuple[float, float, float, float]
    interactivity: bool
    content: Optional[str] = None
    source: Optional[str] = None


@dataclass
class OmniParserResult:
    """
    Full grounding result produced by the Grounder.

    Fields:
        elements     — all detected elements (text + icon, interactive + static)
        interactable — subset of elements where interactivity is True
        width        — screenshot width in pixels
        height       — screenshot height in pixels
        latency_ms   — round-trip time to OmniParser in milliseconds
        screen_info  — set-of-mark text for MLLM prompt injection
                       e.g. "ID: 0, Text: Settings\\nID: 1, Icon: home"
    """

    elements: List[ParsedElement]
    interactable: List[ParsedElement]
    width: int
    height: int
    latency_ms: float
    screen_info: str = field(default="")
