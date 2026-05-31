#!/usr/bin/env python3
"""
Manual test for the Achiever pipeline (planner/achiever.py).

Given a screenshot and a sub-goal, calls achieve() with the real MLLM and
prints the next concrete mobile action, completion status, and redo signal.

---
How to run
---

1. Prerequisites
   - A valid API_KEY in .env (MOCK_MODE is forced off).
   - At least one image (PNG, JPG, WEBP, BMP) in the test/ folder.

2. Run from the project root:

       # Default sub-goal, auto-pick first image in test/
       python achiever_test.py

       # Explicit sub-goal
       python achiever_test.py "Navigate through Settings to enter the Wi-Fi section"

       # Explicit sub-goal + explicit image
       python achiever_test.py "Open the camera app" test/original.png

3. MOCK_MODE is forced to False so the real MLLM is always called.
   Set a valid API_KEY in .env before running.

4. Expected output
   - next_action      — one concrete step written as a mobile user-guide instruction
   - subgoal_achieved — whether the screenshot already shows the sub-goal complete
   - redo_from_idx    — None, or an index signalling which step to redo
"""

import os
import sys
from pathlib import Path

from PIL import Image

# Force live MLLM mode regardless of .env.
os.environ["MOCK_MODE"] = "false"

from planner import achieve  # noqa: E402
from planner.models import AchieverOutput  # noqa: E402

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_TEST_DIR = Path(__file__).parent / "test"
_DEFAULT_SUBGOAL = "Navigate through Settings to enter the Wi-Fi section"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_image(arg: str | None) -> Path:
    if arg:
        path = Path(arg)
        if not path.exists():
            print(f"Error: file not found — {path}")
            sys.exit(1)
        return path

    images = sorted(
        p for p in _TEST_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in _IMAGE_EXTENSIONS
    )
    if not images:
        print(f"No images found in {_TEST_DIR}/")
        sys.exit(1)

    print(f"Using: {images[0].name}")
    return images[0]


def _validate(result: AchieverOutput) -> None:
    """Assert the return type matches achieve() -> AchieverOutput."""
    assert isinstance(result, AchieverOutput), (
        f"Expected AchieverOutput, got {type(result)}"
    )
    assert isinstance(result.next_action, str) and result.next_action.strip(), (
        "next_action must be a non-empty string"
    )
    assert isinstance(result.subgoal_achieved, bool), (
        f"subgoal_achieved must be bool, got {type(result.subgoal_achieved)}"
    )
    assert result.redo_from_idx is None or isinstance(result.redo_from_idx, int), (
        f"redo_from_idx must be int or None, got {type(result.redo_from_idx)}"
    )

    print("Validation passed:")
    print(f"  Type : AchieverOutput")
    print(f"  Fields: next_action=str  subgoal_achieved=bool  redo_from_idx=int|None")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    subgoal   = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_SUBGOAL
    image_arg = sys.argv[2] if len(sys.argv) > 2 else None
    image_path = _pick_image(image_arg)

    image = Image.open(image_path).convert("RGB")

    print(f"Sub-goal : {subgoal!r}")
    print(f"Image    : {image_path.name}  ({image.width}x{image.height})")
    print()

    print("Calling achieve()...")
    try:
        result = achieve(image=image, subgoal=subgoal)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"ERROR: {type(exc).__name__}: {exc}")
        sys.exit(1)

    _validate(result)

    print()
    print("=" * 60)
    print("Result:")
    print("=" * 60)
    print(f"  next_action      : {result.next_action}")
    print(f"  subgoal_achieved : {result.subgoal_achieved}")
    print(f"  redo_from_idx    : {result.redo_from_idx}")


if __name__ == "__main__":
    main()
