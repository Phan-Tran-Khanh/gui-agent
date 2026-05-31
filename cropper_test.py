#!/usr/bin/env python3
"""
Manual test for the crop-and-upsample pipeline (vision/cropper.py).

Runs crop_and_upsample_region on images from test/ at several candidate
points, prints the transformation context for each resulting FocusRegion,
and saves the upsampled crops for visual inspection.

---
How to run
---

1. Prerequisites
   - At least one image (PNG, JPG, WEBP, BMP) in the test/ folder.
   - No API key or external service required — cropping is purely local.

2. Run from the project root:

       # Auto-pick first image in test/, use default candidate points
       python cropper_test.py

       # Explicit image path
       python cropper_test.py test/original.png

3. VISION_CROPPING_ENABLED is forced to True so the pipeline is always
   exercised regardless of the value in .env.

4. Expected output
   For each candidate point × crop ratio:
   - FocusRegion context printed (origin, zoom factors, offsets)
   - Upsampled crop saved as test/<name>_crop_<point>_<ratio>.png
"""

import io
import os
import sys
from pathlib import Path
from typing import List, Tuple

from PIL import Image

# Force cropping on so the full pipeline is always exercised.
os.environ["VISION_CROPPING_ENABLED"] = "true"
os.environ["MOCK_MODE"] = "false"

from config import Config  # noqa: E402
from vision.cropper import (  # noqa: E402
    CropContext,
    FocusRegion,
    crop_and_upsample_region,
)

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_TEST_DIR = Path(__file__).parent / "test"

# Candidate points expressed as fractions of (width, height) — tested on every image.
_CANDIDATE_FRACTIONS: List[Tuple[float, float]] = [
    (0.5, 0.5),   # centre
    (0.25, 0.25), # top-left quadrant
    (0.75, 0.75), # bottom-right quadrant
]

# Crop ratios to exercise (subset of DEFAULT_CROP_RATIOS for brevity)
_TEST_CROP_RATIOS = [(0.5, 0.5), (0.3, 0.3)]


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


def _validate_region(region: FocusRegion, label: str) -> None:
    """Assert a FocusRegion has valid content and context."""
    assert isinstance(region, FocusRegion), (
        f"[{label}] Expected FocusRegion, got {type(region)}"
    )
    assert isinstance(region.image_bytes, bytes) and region.image_bytes, (
        f"[{label}] image_bytes must be non-empty bytes"
    )
    assert isinstance(region.context, CropContext), (
        f"[{label}] context must be CropContext, got {type(region.context)}"
    )
    assert isinstance(region.original_image_size, tuple) and len(region.original_image_size) == 2, (
        f"[{label}] original_image_size must be a (w, h) tuple"
    )
    # The crop must sit within the original image bounds
    ctx = region.context
    assert ctx.left >= 0 and ctx.top >= 0, (
        f"[{label}] crop origin ({ctx.left}, {ctx.top}) must be non-negative"
    )
    assert ctx.zoom_x > 0 and ctx.zoom_y > 0, (
        f"[{label}] zoom factors must be positive"
    )


def _print_context(ctx: CropContext, label: str) -> None:
    print(
        f"    {label:<30}  "
        f"origin=({ctx.left:4d},{ctx.top:4d})  "
        f"crop={ctx.original_width:4d}×{ctx.original_height:4d}  "
        f"zoom=({ctx.zoom_x:.3f},{ctx.zoom_y:.3f})  "
        f"offset=({ctx.offset_w:.1f},{ctx.offset_h:.1f})"
    )


def _save_region(region: FocusRegion, out_path: Path) -> None:
    img = Image.open(io.BytesIO(region.image_bytes))
    img.save(out_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    config = Config()
    image_path = _pick_image(sys.argv[1] if len(sys.argv) > 1 else None)

    image = Image.open(image_path).convert("RGB")
    w, h = image.size

    print(f"Image                  : {image_path.name}  ({w}×{h})")
    print(f"VISION_CROPPING_ENABLED: {config.vision_cropping_enabled}  "
          f"(test runs regardless of this flag)")
    print(f"Candidate points       : {len(_CANDIDATE_FRACTIONS)}")
    print(f"Crop ratios per point  : {len(_TEST_CROP_RATIOS)}")
    print()

    total_regions = 0
    total_failures = 0

    for frac_x, frac_y in _CANDIDATE_FRACTIONS:
        px, py = int(frac_x * w), int(frac_y * h)
        print(f"Candidate point ({px:4d}, {py:4d})  [{frac_x:.2f}w, {frac_y:.2f}h]:")

        try:
            regions = crop_and_upsample_region(
                candidate_point=(px, py),
                original_image=image,
                crop_ratios=_TEST_CROP_RATIOS,
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            total_failures += 1
            continue

        assert len(regions) == len(_TEST_CROP_RATIOS), (
            f"Expected {len(_TEST_CROP_RATIOS)} regions, got {len(regions)}"
        )

        for region, (rx, ry) in zip(regions, _TEST_CROP_RATIOS):
            label = f"ratio=({rx},{ry})"
            _validate_region(region, label)
            _print_context(region.context, label)

            out_name = (
                f"{image_path.stem}_crop"
                f"_{int(frac_x*100)}x{int(frac_y*100)}"
                f"_r{int(rx*10)}{int(ry*10)}"
                f"{image_path.suffix}"
            )
            _save_region(region, _TEST_DIR / out_name)
            total_regions += 1

        print()

    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"  Regions produced : {total_regions}")
    print(f"  Failures         : {total_failures}")
    print(f"  Output saved to  : {_TEST_DIR}/")
    if total_failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
