#!/usr/bin/env python3
"""
GUI Agent CLI — executes a user task on a mobile device through the full
plan → achieve → ground → execute pipeline.

Usage
-----
    python eval.py "Open Settings and enable Wi-Fi"
    python eval.py "Search for flights to Tokyo" --device-id emulator-5554
    python eval.py "Turn on dark mode" --device-id 144321556E009492 --max-steps 30

Pipeline
--------
    1.  plan()       — decompose the task into 3 high-level sub-goals
    2.  Loop until all sub-goals complete:
        a. capture screenshot from device (or synthetic in mock mode)
        b. optionally mask the screenshot (VISION_MASKING_ENABLED)
        c. achieve() — determine the immediate next action
        d. if subgoal_achieved → advance to next sub-goal
        e. if redo_from_idx set:
             - propose() to locate a broad recovery region
             - if VISION_CROPPING_ENABLED:
                 crop_and_upsample_region() → multi-scale crops
                 run achieve-ground-execute in parallel across scales;
                 first scale that makes progress wins; element coordinates
                 are mapped back to the full original image before dispatch
             - else: use proposer crop directly without zoom
        f. else (normal step):
             - ground() — annotate screenshot, build screen_info + elements
             - execute() — MLLM picks action, ADB dispatches it
             - if VISION_DIFFERENTIATOR_ENABLED: verify action had visual effect
             - append action to executed history

Feature flags (set in .env)
---------------------------
    MOCK_MODE=true               skip device and LLM calls
    VISION_MASKING_ENABLED=true  apply LessIsMore random masking before MLLM
    VISION_DIFFERENTIATOR_ENABLED=true  YDiff change verification after each step
    VISION_CROPPING_ENABLED=true        multi-scale crop for redo recovery
"""

import argparse
import asyncio
import io
import logging
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image

from adb import adb
from config import Config
from executor import execute
from grounder import ground
from grounder.models import ParsedElement
from planner import achieve, plan, propose
from planner.models import AchieverOutput
from vision.cropper import FocusRegion, crop_and_upsample_region
from vision.masker import mask_image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_logger = logging.getLogger("eval")

_SCREENSHOT_LOCAL_PATH = "output/eval_screenshot.png"
_TEST_DIR = Path(__file__).parent / "test"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GUI Agent — execute a task on a mobile device",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("task", help="Natural-language task to accomplish")
    parser.add_argument(
        "--device-id", "-d", default=None,
        help="Android device ID or emulator serial (e.g. emulator-5554). "
             "Omit for annotation-only mode (no ADB dispatch).",
    )
    parser.add_argument(
        "--max-steps", type=int, default=20,
        help="Maximum actions allowed per sub-goal (default 20)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Screenshot capture
# ---------------------------------------------------------------------------

def _capture_screenshot(device_id: Optional[str], config: Config) -> Image.Image:
    """
    Return the current device screenshot as a PIL Image.

    Mock mode  — loads first PNG from test/ or returns a grey canvas.
    Real device — captures via ADB screencap and pull.
    No device  — raises (callers must supply the initial image themselves).
    """
    if config.mock_mode:
        images = sorted(_TEST_DIR.glob("*.png"))
        if images:
            return Image.open(images[0]).convert("RGB")
        return Image.new("RGB", (720, 1280), (180, 180, 180))

    if device_id is None:
        raise RuntimeError(
            "device_id is required for live screenshot capture. "
            "Pass --device-id or set MOCK_MODE=true."
        )

    png_bytes = adb.capture_screenshot(device_id, local_path=_SCREENSHOT_LOCAL_PATH)
    if png_bytes is None:
        raise RuntimeError("Screenshot capture failed — check adb connection and device_id.")

    return Image.open(io.BytesIO(png_bytes)).convert("RGB")


# ---------------------------------------------------------------------------
# Coordinate mapping: zoomed FocusRegion → full original image
# ---------------------------------------------------------------------------

def _transform_elements_to_original(
    elements: List[ParsedElement],
    region: FocusRegion,
) -> List[ParsedElement]:
    """
    Map ParsedElement bboxes from a zoomed FocusRegion back to the full
    original image's normalised coordinate space so the executor can
    dispatch ADB actions to the correct screen coordinates.

    Transformation (per element, per coordinate component):
        1. Normalised bbox in zoomed image → pixel in zoomed image
        2. Subtract centering offset (offset_w / offset_h from CropContext)
        3. Divide by zoom factor → pixel in original crop region
        4. Add crop origin (left / top from CropContext) → full-image pixel
        5. Divide by full image dimensions → normalised 0-1 in original space
    """
    ctx = region.context
    full_w, full_h = region.original_image_size
    zoomed_w = ctx.original_width * ctx.zoom_x
    zoomed_h = ctx.original_height * ctx.zoom_y

    transformed: List[ParsedElement] = []
    for elem in elements:
        bx1, by1, bx2, by2 = elem.bbox

        # Pixels in zoomed image (remove centering offsets)
        px1 = bx1 * zoomed_w - ctx.offset_w
        py1 = by1 * zoomed_h - ctx.offset_h
        px2 = bx2 * zoomed_w - ctx.offset_w
        py2 = by2 * zoomed_h - ctx.offset_h

        # Inverse-zoom → full-image pixels
        ox1 = ctx.left + px1 / ctx.zoom_x
        oy1 = ctx.top  + py1 / ctx.zoom_y
        ox2 = ctx.left + px2 / ctx.zoom_x
        oy2 = ctx.top  + py2 / ctx.zoom_y

        # Re-normalise to full original image
        transformed.append(ParsedElement(
            idx=elem.idx, type=elem.type,
            bbox=(ox1 / full_w, oy1 / full_h, ox2 / full_w, oy2 / full_h),
            interactivity=elem.interactivity,
            content=elem.content,
            source=elem.source,
        ))
    return transformed


# ---------------------------------------------------------------------------
# Parallel redo — one attempt per crop scale
# ---------------------------------------------------------------------------

async def _run_scale_attempt(
    region: FocusRegion,
    subgoal: str,
    executed_actions: List[str],
    device_id: Optional[str],
) -> Optional[str]:
    """
    Run achieve-ground-execute on one zoomed scale for redo recovery.

    Returns the next_action string when this scale can make progress
    (achiever does not signal another redo), or None to let the caller
    try other scales.
    """
    zoomed = Image.open(io.BytesIO(region.image_bytes)).convert("RGB")
    enhanced, screen_info, elements = await ground(zoomed)

    ach: AchieverOutput = achieve(
        image=enhanced,
        subgoal=subgoal,
        executed_actions=executed_actions if executed_actions else None,
    )

    if ach.redo_from_idx is not None:
        _logger.debug("Scale attempt still needs redo — skipping this scale")
        return None

    # Map elements back to full original image before dispatching
    elements_orig = _transform_elements_to_original(elements, region)

    success, _ = execute(
        action_text=ach.next_action,
        image=enhanced,
        elements=elements_orig,
        screen_info=screen_info,
        device_id=device_id,
    )
    return ach.next_action if success else None


async def _run_parallel_redo(
    subgoal: str,
    executed_actions: List[str],
    center_point: Tuple[int, int],
    original_screenshot: Image.Image,
    device_id: Optional[str],
) -> Optional[str]:
    """
    Multi-scale redo: crop around the proposed centre at several zoom levels,
    run achieve-ground-execute concurrently on all scales, and return the
    next_action from the first scale that makes progress.
    """
    regions = crop_and_upsample_region(
        candidate_point=center_point,
        original_image=original_screenshot,
    )
    _logger.info("Parallel redo across %d crop scales", len(regions))

    results = await asyncio.gather(
        *[
            _run_scale_attempt(r, subgoal, executed_actions, device_id)
            for r in regions
        ],
        return_exceptions=True,
    )

    for r in results:
        if isinstance(r, str):
            return r
    return None


# ---------------------------------------------------------------------------
# Sub-goal execution loop
# ---------------------------------------------------------------------------

async def _run_subgoal(
    subgoal: str,
    subgoal_idx: int,
    device_id: Optional[str],
    max_steps: int,
    config: Config,
    initial_screenshot: Image.Image,
) -> Image.Image:
    """
    Drive a single sub-goal to completion and return the last screenshot.
    """
    executed_actions: List[str] = []
    prev_screenshot = initial_screenshot
    current_screenshot = initial_screenshot

    _logger.info("=" * 60)
    _logger.info("Sub-goal %d: %s", subgoal_idx + 1, subgoal)
    _logger.info("=" * 60)

    for step in range(max_steps):
        _logger.info("--- Step %d / %d ---", step + 1, max_steps)

        # Optional masking
        working_image = (
            mask_image(current_screenshot) if config.vision_masking_enabled
            else current_screenshot
        )

        # Achiever
        ach: AchieverOutput = achieve(
            image=working_image,
            subgoal=subgoal,
            executed_actions=executed_actions if executed_actions else None,
        )
        _logger.info("next_action      : %s", ach.next_action)
        _logger.info("subgoal_achieved : %s  redo_from_idx: %s",
                     ach.subgoal_achieved, ach.redo_from_idx)

        if ach.subgoal_achieved:
            _logger.info("Sub-goal %d complete.", subgoal_idx + 1)
            break

        # --- Redo branch ---
        if ach.redo_from_idx is not None:
            failed_action = executed_actions[ach.redo_from_idx]
            executed_actions = executed_actions[:ach.redo_from_idx]
            _logger.info(
                "Rolling back to idx=%d — failed action: %s",
                ach.redo_from_idx, failed_action,
            )

            # Propose a broad recovery region for the action that originally failed,
            # not the achiever's current suggestion which may be a workaround step.
            proposer_result = propose(action=failed_action, image=prev_screenshot)
            _logger.info("Proposer: cells=%s  centre=%s",
                         proposer_result.square_indices, proposer_result.center_point)

            if config.vision_cropping_enabled:
                won = await _run_parallel_redo(
                    subgoal=subgoal,
                    executed_actions=executed_actions,
                    center_point=proposer_result.center_point,
                    original_screenshot=prev_screenshot,
                    device_id=device_id,
                )
                if won:
                    executed_actions.append(won)
            else:
                enhanced, screen_info, elements = await ground(proposer_result.proposed_image)
                success, _ = execute(
                    action_text=ach.next_action,
                    image=enhanced,
                    elements=elements,
                    screen_info=screen_info,
                    device_id=device_id,
                )
                if success:
                    executed_actions.append(ach.next_action)

            prev_screenshot = current_screenshot
            current_screenshot = _capture_screenshot(device_id, config)
            continue

        # --- Normal branch ---
        enhanced, screen_info, elements = await ground(working_image)
        success, _ = execute(
            action_text=ach.next_action,
            image=enhanced,
            elements=elements,
            screen_info=screen_info,
            device_id=device_id,
        )
        _logger.info("execute: success=%s", success)

        prev_screenshot = current_screenshot
        current_screenshot = _capture_screenshot(device_id, config)

        if success:
            executed_actions.append(ach.next_action)

        # Differentiator: if the action produced no visual change it effectively
        # failed — treat it as a redo and propose a recovery region immediately.
        if config.vision_differentiator_enabled:
            from planner.differentiator import detect_visual_change  # noqa: PLC0415
            changed = detect_visual_change(prev_screenshot, current_screenshot)
            if not changed:
                _logger.warning(
                    "Action had no visual effect — triggering redo for: %s",
                    ach.next_action,
                )
                # Roll back the action we just appended
                if executed_actions and executed_actions[-1] == ach.next_action:
                    executed_actions.pop()

                proposer_result = propose(action=ach.next_action, image=prev_screenshot)
                _logger.info("Proposer: cells=%s  centre=%s",
                             proposer_result.square_indices, proposer_result.center_point)

                if config.vision_cropping_enabled:
                    won = await _run_parallel_redo(
                        subgoal=subgoal,
                        executed_actions=executed_actions,
                        center_point=proposer_result.center_point,
                        original_screenshot=prev_screenshot,
                        device_id=device_id,
                    )
                    if won:
                        executed_actions.append(won)
                else:
                    enhanced_r, screen_info_r, elements_r = await ground(
                        proposer_result.proposed_image
                    )
                    success_r, _ = execute(
                        action_text=ach.next_action,
                        image=enhanced_r,
                        elements=elements_r,
                        screen_info=screen_info_r,
                        device_id=device_id,
                    )
                    if success_r:
                        executed_actions.append(ach.next_action)

                prev_screenshot = current_screenshot
                current_screenshot = _capture_screenshot(device_id, config)
                continue

    else:
        _logger.warning("Sub-goal %d hit max_steps=%d", subgoal_idx + 1, max_steps)

    return current_screenshot


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run(task: str, device_id: Optional[str], max_steps: int) -> None:
    config = Config()

    _logger.info("Task      : %s", task)
    _logger.info("Device    : %s", device_id or "(annotation-only, no ADB)")
    _logger.info("Mock      : %s", config.mock_mode)
    _logger.info("Flags     : masking=%s  differentiator=%s  cropping=%s",
                 config.vision_masking_enabled,
                 config.vision_differentiator_enabled,
                 config.vision_cropping_enabled)

    screenshot = _capture_screenshot(device_id, config)

    _logger.info("Planning…")
    subgoals = plan(task=task, image=screenshot)
    for i, sg in enumerate(subgoals, 1):
        _logger.info("  Sub-goal %d: %s", i, sg)

    current_screenshot = screenshot
    for idx, subgoal in enumerate(subgoals):
        current_screenshot = await _run_subgoal(
            subgoal=subgoal,
            subgoal_idx=idx,
            device_id=device_id,
            max_steps=max_steps,
            config=config,
            initial_screenshot=current_screenshot,
        )

    _logger.info("Task complete.")


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(run(task=args.task, device_id=args.device_id, max_steps=args.max_steps))
    except KeyboardInterrupt:
        _logger.info("Interrupted by user")
        sys.exit(130)
    except RuntimeError as exc:
        _logger.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
