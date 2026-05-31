#!/usr/bin/env python3
"""
Manual test for the vision masking pipeline (vision/masker.py).

Exercises both operating modes of mask_image() on every image found in test/
and saves the results locally so the masking output can be visually inspected.

---
How to run
---

1. Prerequisites
   - Place at least one image (PNG, JPG, WEBP, BMP) in the test/ folder.
   - No API key or external service is required — masking is purely local.

2. Run from the project root:

       # Test all images in test/ with default parameters
       python masker_test.py

       # Test a specific image
       python masker_test.py test/original.png

3. Operating modes tested
   - ROI-preserving mode  — masks everything outside a centred region of
                            interest around the image midpoint (x, y provided).
                            Saved as test/<name>_masked_roi.<ext>

   - Random masking mode  — masks a random rectangular patch anywhere on the
                            image (no x, y provided).
                            Saved as test/<name>_masked_random.<ext>

4. Expected output
   - Both masked images saved alongside the source in test/.
   - Validation confirms both outputs are PIL.Image.Image with correct size.

Note: MOCK_MODE has no effect on masking (it is a local image transform).
VISION_MASKING_ENABLED from .env is read and printed for information only —
this test always runs masking regardless of that flag.
"""

import os
import sys
from pathlib import Path
from typing import List

from PIL import Image

# Force vision masking on so the full mask_image pipeline is always exercised.
os.environ["VISION_MASKING_ENABLED"] = "true"
os.environ["MOCK_MODE"] = "false"

from config import Config  # noqa: E402
from vision.masker import mask_image  # noqa: E402

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_TEST_DIR = Path(__file__).parent / "test"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_images(arg: str | None) -> List[Path]:
    if arg:
        path = Path(arg)
        if not path.exists():
            print(f"Error: file not found — {path}")
            sys.exit(1)
        return [path]

    images = sorted(
        p for p in _TEST_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in _IMAGE_EXTENSIONS
    )
    if not images:
        print(f"No images found in {_TEST_DIR}/")
        print("Add a PNG/JPG/WEBP file there and re-run.")
        sys.exit(1)
    return images


def _validate(result: Image.Image, expected_size: tuple, label: str) -> None:
    assert isinstance(result, Image.Image), (
        f"[{label}] Expected PIL.Image.Image, got {type(result)}"
    )
    assert result.size == expected_size, (
        f"[{label}] Size mismatch: expected {expected_size}, got {result.size}"
    )
    assert result.mode == "RGB", (
        f"[{label}] Expected RGB mode, got {result.mode}"
    )
    print(f"  [{label}] Validation passed — {result.size[0]}x{result.size[1]} RGB")


def _test_image(image_path: Path) -> None:
    print(f"\nImage: {image_path.name}")

    image = Image.open(image_path).convert("RGB")
    w, h = image.size
    print(f"  Size     : {w}x{h}")

    # --- ROI-preserving mode (x, y = image centre) ---
    cx, cy = w / 2, h / 2
    roi_result = mask_image(image, x=cx, y=cy)
    _validate(roi_result, (w, h), "ROI mode")
    roi_out = image_path.parent / f"{image_path.stem}_masked_roi{image_path.suffix}"
    roi_result.save(roi_out)
    print(f"  ROI mask : saved → {roi_out.name}")

    # --- Random masking mode (no x, y) ---
    rand_result = mask_image(image)
    _validate(rand_result, (w, h), "Random mode")
    rand_out = image_path.parent / f"{image_path.stem}_masked_random{image_path.suffix}"
    rand_result.save(rand_out)
    print(f"  Random   : saved → {rand_out.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    config = Config()
    images = _pick_images(sys.argv[1] if len(sys.argv) > 1 else None)

    print(f"VISION_MASKING_ENABLED : {config.vision_masking_enabled}  "
          f"(test runs regardless of this flag)")
    print(f"Images to test         : {len(images)}")

    for image_path in images:
        _test_image(image_path)

    print(f"\nDone — {len(images) * 2} masked image(s) saved to {_TEST_DIR}/")


if __name__ == "__main__":
    main()
