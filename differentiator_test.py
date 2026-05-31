#!/usr/bin/env python3
"""
Manual test for the YDiff visual change detector (planner/differentiator.py).

Compares every pair of images found in test/ — including a same-image baseline —
and prints whether each pair differs visually.

---
How to run
---

1. Prerequisites
   - At least two images (PNG, JPG, WEBP, BMP) in the test/ folder.
   - No API key or external service is required — detection is purely local.

2. Run from the project root:

       # Test all pairs in test/
       python differentiator_test.py

       # Test a specific pair
       python differentiator_test.py test/original.png test/original_grounded.png

3. VISION_DIFFERENTIATOR_ENABLED is forced to True so the full pipeline is
   always exercised regardless of the value in .env.

4. Expected output
   - Baseline check: same image compared with itself → False (no change).
   - Cross-image pairs: annotated vs original → True (bounding boxes differ).
   - Each result printed with the SSIM-derived verdict.
"""

import os
import sys
import time
from itertools import combinations
from pathlib import Path
from typing import List, Tuple

import numpy as np
from PIL import Image

# Force differentiator on so the full detection pipeline is always exercised.
os.environ["VISION_DIFFERENTIATOR_ENABLED"] = "true"
os.environ["MOCK_MODE"] = "false"

from config import Config  # noqa: E402
from planner.differentiator import detect_visual_change  # noqa: E402

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_TEST_DIR = Path(__file__).parent / "test"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_images(args: List[str]) -> List[Path]:
    if len(args) == 2:
        paths = [Path(a) for a in args]
        for p in paths:
            if not p.exists():
                print(f"Error: file not found — {p}")
                sys.exit(1)
        return paths

    images = sorted(
        p for p in _TEST_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in _IMAGE_EXTENSIONS
    )
    if not images:
        print(f"No images found in {_TEST_DIR}/")
        print("Add at least one PNG/JPG/WEBP file there and re-run.")
        sys.exit(1)
    return images


# ---------------------------------------------------------------------------
# Pixel-by-pixel benchmark
# ---------------------------------------------------------------------------

# Fraction of differing pixels above which the pair is considered changed.
_PIXEL_DIFF_THRESHOLD = 0.001  # 0.1 %


def _pixel_diff(img_a: Path, img_b: Path) -> Tuple[bool, float]:
    """
    Compare two images pixel by pixel.

    Converts both to RGB arrays and computes the fraction of pixels that
    differ by at least 1 in any channel.  Images of different dimensions
    are always considered changed.

    Returns:
        (changed, diff_ratio) — changed is True when diff_ratio > threshold.
    """
    arr_a = np.array(Image.open(img_a).convert("RGB"), dtype=np.int32)
    arr_b = np.array(Image.open(img_b).convert("RGB"), dtype=np.int32)

    if arr_a.shape != arr_b.shape:
        return True, 1.0

    diff_mask = np.any(np.abs(arr_a - arr_b) > 0, axis=-1)
    ratio = float(diff_mask.sum()) / (arr_a.shape[0] * arr_a.shape[1])
    return ratio > _PIXEL_DIFF_THRESHOLD, ratio


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_same_image(image_path: Path) -> None:
    """Comparing an image with itself must always return False (no change)."""
    pil = Image.open(image_path)
    changed = detect_visual_change(pil, pil)
    assert not changed, (
        f"Same-image comparison returned True for {image_path.name} — expected False"
    )
    print(f"  ✓  Same-image baseline ({image_path.name}) → IDENTICAL  [as expected]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _run_pair_timed(
    img_a: Path, img_b: Path
) -> Tuple[bool, float, bool, float, float]:
    """Run both algorithms and return (ydiff, ydiff_ms, pixel, pixel_ms, ratio)."""
    pil_a = Image.open(img_a)
    pil_b = Image.open(img_b)

    t0 = time.perf_counter()
    ydiff = detect_visual_change(pil_a, pil_b)
    ydiff_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    pixel, ratio = _pixel_diff(img_a, img_b)
    pixel_ms = (time.perf_counter() - t0) * 1000

    return ydiff, ydiff_ms, pixel, pixel_ms, ratio


def _print_conclusion(
    results: List[Tuple[bool, float, bool, float, float]],
) -> None:
    """Print a statistical summary and interpretation of the benchmark."""
    n = len(results)
    if n == 0:
        return

    agreements   = sum(1 for y, _, p, _, _ in results if y == p)
    ydiff_ms_avg = sum(r[1] for r in results) / n
    pixel_ms_avg = sum(r[3] for r in results) / n
    ydiff_changed = sum(1 for y, *_ in results if y)
    pixel_changed = sum(1 for _, _, p, *_ in results if p)

    # Cases where YDiff says IDENTICAL but pixel diff disagrees (sensitivity gap)
    ydiff_missed = [(r[4], r[3]) for r in results if not r[0] and r[2]]

    print("=" * 70)
    print("Conclusion")
    print("=" * 70)
    print(f"  Pairs tested       : {n}")
    print(f"  Agreement rate     : {agreements}/{n}  ({agreements/n*100:.0f}%)")
    print()
    print(f"  YDiff   — changed: {ydiff_changed}/{n}   avg time: {ydiff_ms_avg:.1f} ms")
    print(f"  Pixel   — changed: {pixel_changed}/{n}   avg time: {pixel_ms_avg:.1f} ms")
    print(f"  Speed advantage (YDiff vs Pixel): {pixel_ms_avg/ydiff_ms_avg:.2f}×  "
          + ("faster" if ydiff_ms_avg < pixel_ms_avg else "slower"))
    print()

    if ydiff_missed:
        avg_missed_ratio = sum(r for r, _ in ydiff_missed) / len(ydiff_missed)
        print(f"  YDiff missed {len(ydiff_missed)} pair(s) that pixel diff caught "
              f"(avg {avg_missed_ratio*100:.1f}% pixels changed).")
        print("  Interpretation: YDiff examines a small central ROI via SSIM — "
              "changes confined to the edges or spread thinly across the image "
              "fall below its threshold. Pixel diff is more sensitive to global "
              "but shallow changes; YDiff is more sensitive to localised, "
              "perceptually significant changes near the point of interest.")
    else:
        print("  Both algorithms agreed on every pair.")
    print("=" * 70)


def main() -> None:
    config = Config()
    cli_args = sys.argv[1:]
    images = _pick_images(cli_args)

    print(f"VISION_DIFFERENTIATOR_ENABLED : {config.vision_differentiator_enabled}  "
          f"(test runs regardless of this flag)")
    print(f"Images found                  : {len(images)}")
    print()

    # --- Baseline: same image vs itself ---
    print("Baseline (same image → should be IDENTICAL):")
    _validate_same_image(images[0])
    print()

    if len(cli_args) == 2:
        pairs = [(images[0], images[1])]
        print("Pair comparison:")
    else:
        pairs = list(combinations(images, 2))
        print(f"Cross-image pairs ({len(pairs)} total):")

    results = []
    for img_a, img_b in pairs:
        ydiff, ydiff_ms, pixel, pixel_ms, ratio = _run_pair_timed(img_a, img_b)

        arr_bytes = Image.open(img_a).width * Image.open(img_a).height * 3
        mem_kb = arr_bytes / 1024
        ydiff_str = "CHANGED  " if ydiff else "IDENTICAL"
        pixel_str = "CHANGED  " if pixel else "IDENTICAL"
        agree     = "✓ agree" if ydiff == pixel else "△ differ"

        print(
            f"  {agree}  "
            f"YDiff:{ydiff_str} {ydiff_ms:6.1f}ms  "
            f"Pixel:{pixel_str} {pixel_ms:6.1f}ms ({ratio*100:5.2f}% px)  "
            f"mem≈{mem_kb:.0f}KB  "
            f"{img_a.name} ↔ {img_b.name}"
        )
        results.append((ydiff, ydiff_ms, pixel, pixel_ms, ratio))

    print()
    _print_conclusion(results)


if __name__ == "__main__":
    main()
