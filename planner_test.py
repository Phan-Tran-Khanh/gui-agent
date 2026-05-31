#!/usr/bin/env python3
"""
Manual test for the Planner pipeline.

Sends a user task and a mobile screenshot to the real MLLM and prints the
three high-level sub-goals returned by plan().

---
How to run
---

1. Prerequisites
   - A valid API_KEY in .env (required — MOCK_MODE is forced off).
   - At least one image (PNG, JPG, WEBP, BMP) in the test/ folder.

2. Run from the project root:

       # Default task, auto-pick first image in test/
       python planner_test.py

       # Explicit task text
       python planner_test.py "Change Wi-Fi to Public HCMUS"

       # Explicit task text + explicit image
       python planner_test.py "Open the Camera app" test/original.png

3. MOCK_MODE is forced to False in this test so the real MLLM is always
   called. Set a valid API_KEY in .env before running.

4. Expected output
   - The three sub-goals printed to stdout, each on its own numbered line.
   - Validation confirms exactly three non-empty strings were returned.
"""

import os
import sys
from pathlib import Path
from typing import List

from PIL import Image

# Force live MLLM mode regardless of .env so the actual planning path is tested.
os.environ["MOCK_MODE"] = "false"

from planner import plan  # noqa: E402  (import after env override)

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_TEST_DIR = Path(__file__).parent / "test"
_DEFAULT_TASK = "Change Wi-Fi to Public HCMUS"


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
        print("Add a PNG/JPG/WEBP file there and re-run.")
        sys.exit(1)

    print(f"Using: {images[0].name}")
    return images[0]


def _validate(subgoals: List[str]) -> None:
    """Assert the return type matches plan() -> List[str] with exactly 3 items."""
    assert isinstance(subgoals, list), (
        f"Expected list, got {type(subgoals)}"
    )
    assert len(subgoals) == 3, (
        f"Expected exactly 3 sub-goals, got {len(subgoals)}"
    )
    for i, sg in enumerate(subgoals, 1):
        assert isinstance(sg, str) and sg.strip(), (
            f"Sub-goal {i} is empty or not a string"
        )

    print("Validation passed:")
    print(f"  Type  : list[str]")
    print(f"  Count : {len(subgoals)} sub-goals")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    task = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_TASK
    image_arg = sys.argv[2] if len(sys.argv) > 2 else None
    image_path = _pick_image(image_arg)

    image = Image.open(image_path).convert("RGB")

    print(f"Task  : {task!r}")
    print(f"Image : {image_path.name}  ({image.width}x{image.height})")
    print()

    print("Calling plan()...")
    try:
        subgoals = plan(task=task, image=image)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"ERROR: {type(exc).__name__}: {exc}")
        sys.exit(1)

    _validate(subgoals)

    print()
    print("=" * 60)
    print("Sub-goals:")
    print("=" * 60)
    for i, sg in enumerate(subgoals, 1):
        print(f"  {i}. {sg}")


if __name__ == "__main__":
    main()
