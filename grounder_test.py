#!/usr/bin/env python3
"""
Manual test for the Grounder pipeline.

Sends an image to OmniParser, validates the annotated output and screen_info
text — mirroring the exact return signature of ground():

    ground(image: Image.Image) -> Tuple[Image.Image, str]

---
How to run
---

1. Prerequisites
   - OmniParser service must be running and reachable.
   - Set PARSE_API_BASE_URL in .env to the service URL, e.g.:
       PARSE_API_BASE_URL=https://your-ngrok-url.ngrok-free.dev
   - If using ngrok or a self-signed certificate, also set:
       PARSE_API_VERIFY_SSL=false
   - Increase the timeout if the service is slow (default 10 s is often too short):
       PARSE_API_TIMEOUT_SEC=60
   - API_KEY must be set (any non-empty value is accepted when not calling the LLM):
       API_KEY=test

2. Place a test image in the test/ folder (PNG, JPG, WEBP, BMP).

3. Run from the project root:

       # Auto-pick the first image in test/
       python grounder_test.py

       # Explicit image path
       python grounder_test.py test/original.png

4. Expected output
   - Validation summary printed to stdout confirming the return types.
   - Screen info (set-of-mark prompt) printed — one line per interactable element.
   - Annotated image saved as test/<name>_grounded.<ext> with coloured bounding
     boxes and ID badges drawn on every interactable UI element.

Note: MOCK_MODE is forced to False inside this script so the live OmniParser
service is always exercised regardless of the value set in .env.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Tuple

from PIL import Image

# Force live mode regardless of .env
os.environ["MOCK_MODE"] = "false"

from grounder import ground  # noqa: E402  (import after env override)

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_TEST_DIR = Path(__file__).parent / "test"


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


def _validate(result: Tuple[Image.Image, str]) -> None:
    """Assert the return type matches ground() -> Tuple[Image.Image, str]."""
    enhanced, screen_info = result

    assert isinstance(enhanced, Image.Image), (
        f"Expected PIL.Image.Image, got {type(enhanced)}"
    )
    assert isinstance(screen_info, str), (
        f"Expected str for screen_info, got {type(screen_info)}"
    )
    assert enhanced.size[0] > 0 and enhanced.size[1] > 0, "Annotated image has zero size"

    print("Validation passed:")
    print(f"  enhanced  : PIL.Image.Image  {enhanced.size[0]}x{enhanced.size[1]} px")
    print(f"  screen_info: str  ({len(screen_info)} chars, "
          f"{len(screen_info.splitlines())} lines)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(image_path: Path) -> None:
    from config import Config
    config = Config()
    print(f"Image     : {image_path.name}  ({Image.open(image_path).width}x{Image.open(image_path).height})")
    print(f"OmniParser: {config.parse_api_base_url or '(not set)'}")
    print(f"Verify SSL: {config.parse_api_verify_ssl}")
    print(f"Mock mode : {config.mock_mode}  (forced false by test)")
    print()

    image = Image.open(image_path).convert("RGB")

    try:
        print("Calling ground()...")
        result = await ground(image)
    except ConnectionError as exc:
        print()
        print("ERROR: Could not reach OmniParser.")
        print(f"  {exc}")
        print()
        print("Check that:")
        print("  1. The OmniParser service is running")
        print("  2. PARSE_API_BASE_URL in .env points to it")
        print("  3. PARSE_API_VERIFY_SSL=false if using ngrok or self-signed TLS")
        sys.exit(1)
    except ValueError as exc:
        print(f"ERROR: Configuration problem — {exc}")
        sys.exit(1)

    enhanced, screen_info = result
    _validate(result)

    print()
    print("=" * 60)
    print("Screen info (set-of-mark prompt):")
    print("=" * 60)
    print(screen_info or "(no interactable elements detected)")
    print()

    out_path = image_path.parent / f"{image_path.stem}_grounded{image_path.suffix}"
    enhanced.save(out_path)
    print(f"Annotated image saved: {out_path}")


def main() -> None:
    image_path = _pick_image(sys.argv[1] if len(sys.argv) > 1 else None)
    asyncio.run(run(image_path))


if __name__ == "__main__":
    main()
