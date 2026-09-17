#!/usr/bin/env python3
"""
Test script for OmniParserClient.

This script demonstrates how to:
1. Load a screenshot from disk or capture one
2. Call OmniParserClient to parse the screenshot
3. Annotate the screenshot with parsed elements
4. Save the annotated image locally
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

from web.omniparser_client import OmniParserClient
from utils.box_annotator import draw_parsed_elements


def setup_logger() -> logging.Logger:
    """Configure and return a logger."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("OmniParserTest")


async def test_omniparser_client(
    image_path: str,
    base_url: str = "https://ample-mammoth-generally.ngrok-free.app",
    output_dir: str = "output",
    logger: Optional[logging.Logger] = None,
) -> bool:
    """
    Test OmniParserClient by parsing a screenshot and annotating it.

    Args:
        image_path: Path to the screenshot image file
        base_url: Base URL of the OmniParser server (default: http://localhost:8000)
        output_dir: Directory to save the annotated image (default: output)
        logger: Logger instance (optional)

    Returns:
        True if successful, False otherwise
    """
    if logger is None:
        logger = setup_logger()

    try:
        # ============================================================================
        # STEP 1: Validate input image
        # ============================================================================
        image_file = Path(image_path)
        if not image_file.exists():
            logger.error(f"Image file not found: {image_path}")
            return False

        logger.info(f" Found image: {image_path}")

        # ============================================================================
        # STEP 2: Read image bytes
        # ============================================================================
        with open(image_file, "rb") as f:
            image_bytes = f.read()

        logger.info(f" Read {len(image_bytes)} bytes from image")

        # ============================================================================
        # STEP 3: Initialize OmniParserClient
        # ============================================================================
        client = OmniParserClient(
            base_url=base_url,
            timeout_sec=30.0,
            retry_count=2,
            retry_backoff_ms=500,
        )
        logger.info(f" OmniParserClient initialized (base_url={base_url})")

        # ============================================================================
        # STEP 4: Probe the OmniParser server
        # ============================================================================
        try:
            probe_result = await client.probe()
            logger.info(f" OmniParser server is reachable")
            logger.info(f"  Server info: {probe_result}")
        except Exception as e:
            logger.warning(f"⚠ Could not reach OmniParser server: {e}")
            logger.info("  Make sure the OmniParser server is running at {base_url}")

        # ============================================================================
        # STEP 5: Parse the screenshot
        # ============================================================================
        logger.info("")
        logger.info("Parsing screenshot...")
        parse_result = await client.parse_screen(
            image_bytes=image_bytes,
            filename=image_file.name,
        )

        logger.info(f" Parse completed in {parse_result.latency_ms:.2f}ms")
        logger.info(f"  Request ID: {parse_result.request_id}")
        logger.info(f"  Elements detected: {len(parse_result.parsed_screen)}")

        # ============================================================================
        # STEP 6: Display parsed elements
        # ============================================================================
        if parse_result.parsed_screen:
            logger.info("")
            logger.info("Parsed Elements:")
            for idx, element in enumerate(parse_result.parsed_screen):
                element_type = element.get("type", "unknown")
                content = element.get("content", "")
                bbox = element.get("bbox", [])
                interactivity = element.get("interactivity", False)

                logger.info(f"  [{idx}] Type: {element_type}, Interactive: {interactivity}")
                logger.info(f"      Content: {content[:100] if content else '(empty)'}")
                logger.info(f"      BBox: {bbox}")
        else:
            logger.warning("No elements detected in screenshot")

        # ============================================================================
        # STEP 7: Create output directory
        # ============================================================================
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        logger.info(f" Output directory created: {output_path.absolute()}")

        # ============================================================================
        # STEP 8: Annotate and save the screenshot
        # ============================================================================
        if parse_result.parsed_screen:
            try:
                annotated_filename = image_file.stem + "_annotated.png"
                annotated_path = output_path / annotated_filename

                logger.info("")
                logger.info(f"Annotating screenshot with bounding boxes...")

                draw_parsed_elements(
                    image_path=str(image_file),
                    parsed_content_list=parse_result.parsed_screen,
                    output_path=str(annotated_path),
                    draw_bbox_config={
                        "text_scale": 0.4,
                        "text_padding": 5,
                        "text_thickness": 2,
                        "thickness": 3,
                    },
                )

                logger.info(f" Annotated image saved: {annotated_path.absolute()}")
            except Exception as e:
                logger.error(f"✗ Failed to annotate image: {e}")
                return False
        else:
            logger.warning("Skipping annotation: no elements to draw")

        # ============================================================================
        # STEP 9: Save raw parsed response
        # ============================================================================
        try:
            import json

            response_filename = image_file.stem + "_parsed_response.json"
            response_path = output_path / response_filename

            with open(response_path, "w") as f:
                json.dump(parse_result.raw_response, f, indent=2)

            logger.info(f" Raw response saved: {response_path.absolute()}")
        except Exception as e:
            logger.warning(f"⚠ Failed to save raw response: {e}")

        logger.info("")
        logger.info("=" * 80)
        logger.info(" TEST COMPLETED SUCCESSFULLY")
        logger.info("=" * 80)

        return True

    except Exception as e:
        logger.exception(f"✗ Test failed with error: {e}")
        return False
    finally:
        await client.close()


async def main():
    """Main entry point for the test script."""
    logger = setup_logger()

    # Default test image - use any available image in the workspace
    test_image = "img/screenshot.png"
    base_url = "https://ample-mammoth-generally.ngrok-free.app"
    output_dir = "output"

    logger.info("=" * 80)
    logger.info("OMNIPARSER CLIENT TEST")
    logger.info("=" * 80)
    logger.info("")

    # Check if a specific image was provided via command line
    if len(sys.argv) > 1:
        test_image = sys.argv[1]

    if len(sys.argv) > 2:
        base_url = sys.argv[2]

    if len(sys.argv) > 3:
        output_dir = sys.argv[3]

    logger.info(f"Configuration:")
    logger.info(f"  Image: {test_image}")
    logger.info(f"  OmniParser URL: {base_url}")
    logger.info(f"  Output directory: {output_dir}")
    logger.info("")

    # Run the test
    success = await test_omniparser_client(
        image_path=test_image,
        base_url=base_url,
        output_dir=output_dir,
        logger=logger,
    )

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
