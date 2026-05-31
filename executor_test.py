#!/usr/bin/env python3
"""
Manual test for the Executor pipeline.

Loads pre-grounded test assets from test/ and runs execute() in annotation-only
mode (no device_id) to verify the full MLLM → ActionOutput → annotation path.

---
How to run
---

1. Prerequisites
   - test/original_grounded.png  — enhanced image produced by grounder_test.py
   - test/parsed.json            — OmniParser JSON output (used to reconstruct
                                    the element list and screen_info)
   - API_KEY must be set in .env (any non-empty value is accepted in mock mode)

2. Run from the project root:

       # Uses MOCK_MODE from .env — synthetic TAP, no LLM call
       python executor_test.py

       # Override action text
       python executor_test.py "tap the navigation menu"

3. MOCK_MODE is forced to False in this test so the real MLLM is always
   exercised. Set a valid API_KEY in .env before running.

4. Expected output
   - Validation summary confirming return types.
   - Annotated image saved as test/original_executed.png showing the decided action:
       TAP / LONG_PRESS  → coloured ring at element centre
       INPUT             → green ring + value label
       SWIPE             → blue arrow
       System actions    → text badge in bottom-left corner

Note: device_id is intentionally omitted — annotation-only mode draws the
action onto the image without executing any ADB commands.
"""

import json
import os
import sys
from pathlib import Path
from typing import List, Tuple

from PIL import Image

# Force live MLLM mode regardless of .env so the full decision path is tested.
os.environ["MOCK_MODE"] = "false"

from executor import execute  # noqa: E402  (import after env override)
from grounder.models import ParsedElement

_TEST_DIR = Path(__file__).parent / "test"
_GROUNDED_IMAGE = _TEST_DIR / "original_grounded.png"
_PARSED_JSON = _TEST_DIR / "parsed.json"

# Generic action texts that exercise different action types.
# The first entry is used by default; pass a custom text as argv[1].
_DEFAULT_ACTION = "tap the first interactable element"


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------


def _load_elements(parsed_json: Path) -> Tuple[List[ParsedElement], str]:
    """
    Parse test/parsed.json into a list of interactable ParsedElement objects
    and compile the screen_info string that mirrors what ground() produces.
    """
    with open(parsed_json, encoding="utf-8-sig") as f:
        payload = json.load(f)

    raw_items = payload.get("parsed_content_list", [])
    elements: List[ParsedElement] = []
    for idx, item in enumerate(raw_items):
        bbox_raw = item.get("bbox", [0.0, 0.0, 0.0, 0.0])
        elements.append(
            ParsedElement(
                idx=int(item.get("idx", idx)),
                type=str(item.get("type", "text")),
                bbox=(
                    float(bbox_raw[0]),
                    float(bbox_raw[1]),
                    float(bbox_raw[2]),
                    float(bbox_raw[3]),
                ),
                interactivity=bool(item.get("interactivity", False)),
                content=item.get("content") or None,
                source=item.get("source") or None,
            )
        )

    interactable = [e for e in elements if e.interactivity]

    screen_info_lines = []
    for elem in interactable:
        label = "Text" if elem.type == "text" else "Icon"
        content = elem.content or ""
        screen_info_lines.append(f"ID: {elem.idx}, {label}: {content}")
    screen_info = "\n".join(screen_info_lines)

    return interactable, screen_info


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate(result: Tuple[bool, Image.Image]) -> None:
    """Assert the return type matches execute() -> Tuple[bool, Image.Image]."""
    success, annotated = result

    assert isinstance(success, bool), f"Expected bool for success, got {type(success)}"
    assert isinstance(
        annotated, Image.Image
    ), f"Expected PIL.Image.Image for annotated, got {type(annotated)}"
    assert (
        annotated.size[0] > 0 and annotated.size[1] > 0
    ), "Annotated image has zero size"

    print("Validation passed:")
    print(f"  success  : {success}")
    print(f"  annotated: PIL.Image.Image  {annotated.size[0]}x{annotated.size[1]} px")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    action_text = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_ACTION

    # --- Check assets ---
    for path in (_GROUNDED_IMAGE, _PARSED_JSON):
        if not path.exists():
            print(f"Error: required test asset not found — {path}")
            print("Run grounder_test.py first to generate test/original_grounded.png")
            sys.exit(1)

    # --- Load assets ---
    image = Image.open(_GROUNDED_IMAGE).convert("RGB")
    elements, screen_info = _load_elements(_PARSED_JSON)

    print(f"Image     : {_GROUNDED_IMAGE.name}  ({image.width}x{image.height})")
    print(f"Elements  : {len(elements)} interactable")
    print(f"Action    : {action_text!r}")
    print("Device    : (none — annotation-only mode)")
    print()

    # --- Print screen info so the test output is self-explanatory ---
    print("=" * 60)
    print("Screen info passed to executor:")
    print("=" * 60)
    print(screen_info)
    print()

    # --- Execute (annotation-only: no device_id) ---
    print("Calling execute()...")
    result = execute(
        action_text=action_text,
        image=image,
        elements=elements,
        screen_info=screen_info,
        # device_id intentionally omitted → annotation-only, no ADB
    )

    # --- Validate ---
    _validate(result)
    success, annotated = result

    # --- Save output ---
    out_path = _TEST_DIR / "original_executed.png"
    annotated.save(out_path)
    print(f"Annotated image saved: {out_path}")

    if not success:
        print("WARNING: execute() returned False — check logs above")
        sys.exit(1)


if __name__ == "__main__":
    main()
