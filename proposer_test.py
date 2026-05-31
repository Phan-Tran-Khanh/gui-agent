#!/usr/bin/env python3
"""
Manual test for the Proposer pipeline (planner/proposer.py).

Given a screenshot and a blocked action, calls propose() with the real MLLM,
prints the selected grid cells and centre point, and saves the annotated
grid image and the cropped proposed area for visual inspection.

---
How to run
---

1. Prerequisites
   - A valid API_KEY in .env (MOCK_MODE is forced off).
   - At least one image (PNG, JPG, WEBP, BMP) in the test/ folder.

2. Run from the project root:

       # Default action, auto-pick first image in test/
       python proposer_test.py

       # Explicit action text
       python proposer_test.py "Tap the Wi-Fi toggle to enable Wi-Fi"

       # Explicit action + explicit image
       python proposer_test.py "Tap the Wi-Fi toggle" test/original.png

3. MOCK_MODE is forced to False so the real MLLM is always called.
   Set a valid API_KEY in .env before running.

4. Expected output
   - square_indices — zero-based grid cell indices the MLLM selected
   - center_point   — (x, y) centre of the proposed region in original coords
   - test/<name>_proposer_grid.png    — screenshot with numbered grid overlay
   - test/<name>_proposer_crop.png    — cropped proposed area
"""

import os
import sys
from pathlib import Path

from PIL import Image

# Force live MLLM mode regardless of .env.
os.environ["MOCK_MODE"] = "false"

import litellm  # noqa: E402

from planner import propose  # noqa: E402
from planner.models import ProposerOutput  # noqa: E402
from planner.proposer import _choose_grid, _draw_grid, _make_cells, _pad_to_grid  # noqa: E402

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_TEST_DIR = Path(__file__).parent / "test"
_DEFAULT_ACTION = "Tap the Search button to open the search field"


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


def _validate(result: ProposerOutput) -> None:
    """Assert the return type matches propose() -> ProposerOutput."""
    assert isinstance(result, ProposerOutput), (
        f"Expected ProposerOutput, got {type(result)}"
    )
    assert isinstance(result.square_indices, list), (
        f"square_indices must be a list, got {type(result.square_indices)}"
    )
    assert all(isinstance(i, int) for i in result.square_indices), (
        "all square_indices must be integers"
    )
    if not result.square_indices:
        print("  WARNING: MLLM returned no relevant cells — action may not match "
              "anything visible in the screenshot (center fallback used).")
    assert isinstance(result.proposed_image, Image.Image), (
        f"proposed_image must be PIL.Image.Image, got {type(result.proposed_image)}"
    )
    assert isinstance(result.center_point, tuple) and len(result.center_point) == 2, (
        "center_point must be a (x, y) tuple"
    )

    print("Validation passed:")
    print(f"  Type         : ProposerOutput")
    print(f"  square_indices : list[int]  ({len(result.square_indices)} cells)")
    print(f"  proposed_image : PIL.Image.Image  "
          f"{result.proposed_image.width}x{result.proposed_image.height} px")
    print(f"  center_point   : Tuple[int, int]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    action    = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_ACTION
    image_arg = sys.argv[2] if len(sys.argv) > 2 else None
    image_path = _pick_image(image_arg)

    image = Image.open(image_path).convert("RGB")

    print(f"Action : {action!r}")
    print(f"Image  : {image_path.name}  ({image.width}x{image.height})")
    print()

    # Save the grid overlay so the user can see what the MLLM received.
    cols, rows = _choose_grid(image)
    padded = _pad_to_grid(image, cols, rows)
    cells = _make_cells(padded, cols, rows)
    grid_img = _draw_grid(padded, cells)
    grid_out = image_path.parent / f"{image_path.stem}_proposer_grid{image_path.suffix}"
    grid_img.save(grid_out)
    print(f"Grid overlay saved : {grid_out.name}  "
          f"({cols}×{rows} = {len(cells)} cells)")
    print()

    print("Calling propose()...")
    try:
        result = propose(action=action, image=image)
    except litellm.ServiceUnavailableError:
        print("ERROR: Gemini API is temporarily unavailable — retry in a moment.")
        sys.exit(1)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"ERROR: {type(exc).__name__}: {exc}")
        sys.exit(1)

    _validate(result)

    print()
    print("=" * 60)
    print("Result:")
    print("=" * 60)
    print(f"  square_indices : {result.square_indices}")
    print(f"  center_point   : {result.center_point}")

    crop_out = image_path.parent / f"{image_path.stem}_proposer_crop{image_path.suffix}"
    result.proposed_image.save(crop_out)
    print(f"  proposed area  : saved → {crop_out.name}")


if __name__ == "__main__":
    main()
