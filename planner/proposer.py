"""
Proposer: identifies the screen region most likely to resolve a blocked action.

Called when an action needs to redo — the Proposer divides the screenshot into
a numbered grid, asks the MLLM which cells are most relevant to the action,
then returns the cropped region and its centre point for focused re-execution.

Exported function
-----------------
    propose(action, image) -> ProposerOutput

---
Usage
---

    from planner import propose
    from planner.models import ProposerOutput
    from PIL import Image

    image = Image.open("screenshot.png")   # annotated image from grounder

    result = propose(
        action="Tap the Wi-Fi toggle to enable Wi-Fi",
        image=image,
    )

    # result.square_indices  — e.g. [3, 4, 8, 9]
    # result.proposed_image  — cropped PIL Image covering those cells
    # result.center_point    — (x, y) in original image coords, suitable for ADB
"""

import logging
from typing import List, Tuple

import litellm
from PIL import Image, ImageDraw
from config import Config
from mllm import BaseMllm, MllmOutputError
from planner.models import GridSelection, ProposerOutput

_logger = logging.getLogger(__name__)

# Primary and fallback grid configurations (cols, rows).
# 5×8 = 40 cells — fine-grained for large or portrait screens.
# 4×7 = 28 cells — coarser fallback for small or square images.
_GRID_PRIMARY = (5, 8)
_GRID_FALLBACK = (4, 7)
_MIN_CELL_PX = 30  # minimum cell side in pixels before switching to fallback


# ---------------------------------------------------------------------------
# Dedicated MLLM
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a mobile screen region adviser helping an agent recover from a "
    "blocked action by identifying where on the screen it should look next.\n\n"
    "The image you receive is a mobile screenshot overlaid with a numbered grid. "
    "Every cell carries its zero-based index, assigned left-to-right then "
    "top-to-bottom, so cell 0 is the top-left tile.\n\n"
    "Your job is to select a generous, broad region of the grid that gives "
    "the agent the widest workable context to retry the action. "
    "Think of it as drawing a wide net around the general zone of the screen "
    "where the action belongs — covering the surrounding area, nearby landmarks, "
    "adjacent controls, and any contextual elements that might help the agent "
    "orient and attempt the action again with fresh visual information. "
    "Err on the side of inclusion: a broad cluster of cells is far more "
    "useful for recovery than a tight, precise selection."
)


class _ProposerMllm(BaseMllm[GridSelection]):
    """MLLM specialised for grid-cell selection."""

    def __init__(self) -> None:
        super().__init__(system_prompt=_SYSTEM_PROMPT, output_class=GridSelection)


# ---------------------------------------------------------------------------
# Grid helpers
# ---------------------------------------------------------------------------


def _pad_to_grid(image: Image.Image, cols: int, rows: int) -> Image.Image:
    """
    Pad the image with black on the right and bottom edges so that every
    grid cell is at least _MIN_CELL_PX pixels on each side.

    Padding is applied only when the image is smaller than the minimum required
    dimensions; otherwise the original image is returned unchanged.
    """
    min_w = cols * _MIN_CELL_PX
    min_h = rows * _MIN_CELL_PX
    new_w = max(image.width, min_w)
    new_h = max(image.height, min_h)
    if new_w == image.width and new_h == image.height:
        return image
    padded = Image.new("RGB", (new_w, new_h), (0, 0, 0))
    padded.paste(image, (0, 0))
    _logger.debug(
        "Padded image %dx%d → %dx%d to fit %d×%d grid",
        image.width,
        image.height,
        new_w,
        new_h,
        cols,
        rows,
    )
    return padded


def _choose_grid(image: Image.Image) -> Tuple[int, int]:
    """
    Pick the best grid configuration for the image dimensions.

    Tries primary (5×8) then fallback (4×7). When neither fits without
    padding, returns the primary grid — _pad_to_grid will expand the image
    to meet the minimum cell size rather than degrading to fewer cells.
    """
    w, h = image.size
    for cols, rows in (_GRID_PRIMARY, _GRID_FALLBACK):
        if w // cols >= _MIN_CELL_PX and h // rows >= _MIN_CELL_PX:
            return cols, rows
    return _GRID_PRIMARY  # caller will pad the image


def _make_cells(
    image: Image.Image, cols: int, rows: int
) -> List[Tuple[int, int, int, int]]:
    """
    Divide the image into a cols×rows grid and return each cell's bounding box.

    Proportional division handles non-divisible dimensions by clamping the
    last column and last row boundaries to the exact image edges, so the
    rightmost/bottom cells absorb any remainder pixels without gaps or overlap.

    Returns:
        List of (x1, y1, x2, y2) tuples in row-major order.
    """
    w, h = image.size
    cells: List[Tuple[int, int, int, int]] = []
    for row in range(rows):
        for col in range(cols):
            x1 = int(col * w / cols)
            y1 = int(row * h / rows)
            # Clamp last column/row to exact image edge to absorb remainder pixels.
            x2 = w if col == cols - 1 else int((col + 1) * w / cols)
            y2 = h if row == rows - 1 else int((row + 1) * h / rows)
            cells.append((x1, y1, x2, y2))
    return cells


def _draw_grid(
    image: Image.Image, cells: List[Tuple[int, int, int, int]]
) -> Image.Image:
    """
    Overlay the numbered grid onto a copy of the image for MLLM input.

    Each cell gets a red border and a filled badge with its zero-based index
    in the top-left corner so the MLLM can reference cells by number.
    """
    annotated = image.copy().convert("RGB")
    draw = ImageDraw.Draw(annotated)

    for idx, (x1, y1, x2, y2) in enumerate(cells):
        # Cell border
        draw.rectangle([x1, y1, x2 - 1, y2 - 1], outline=(220, 30, 30), width=1)
        # Label badge
        label = str(idx)
        badge_w = 6 * len(label) + 4
        draw.rectangle([x1, y1, x1 + badge_w, y1 + 14], fill=(220, 30, 30))
        draw.text((x1 + 2, y1 + 1), label, fill=(255, 255, 255))

    return annotated


# ---------------------------------------------------------------------------
# Proposed area extraction
# ---------------------------------------------------------------------------


def _extract_proposed(
    image: Image.Image,
    cells: List[Tuple[int, int, int, int]],
    indices: List[int],
) -> Tuple[Image.Image, Tuple[int, int]]:
    """
    Crop the bounding box of all selected cells from the original image.

    Centre point is returned in the original image's coordinate space,
    making it directly usable for ADB actions or visual-change detection.

    Falls back to the full image when no valid indices are provided.
    """
    valid = [cells[i] for i in indices if 0 <= i < len(cells)]
    if not valid:
        cx, cy = image.width // 2, image.height // 2
        return image.copy(), (cx, cy)

    x1 = min(c[0] for c in valid)
    y1 = min(c[1] for c in valid)
    x2 = max(c[2] for c in valid)
    y2 = max(c[3] for c in valid)

    cropped = image.crop((x1, y1, x2, y2))
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    return cropped, (cx, cy)


# ---------------------------------------------------------------------------
# Mock fallback
# ---------------------------------------------------------------------------


def _mock_propose(image: Image.Image) -> ProposerOutput:
    """Return the centre cell of the primary grid as a synthetic result."""
    cols, rows = _GRID_PRIMARY
    cells = _make_cells(image, cols, rows)
    centre_idx = len(cells) // 2
    proposed, center = _extract_proposed(image, cells, [centre_idx])
    return ProposerOutput(
        square_indices=[centre_idx],
        proposed_image=proposed,
        center_point=center,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def propose(action: str, image: Image.Image) -> ProposerOutput:
    """
    Identify the screenshot region most likely to resolve a blocked action.

    Divides the annotated screenshot into a numbered grid (5×8 primary,
    4×7 fallback), asks the MLLM which cells are most relevant to the action,
    then crops that region and computes its centre point.

    Args:
        action: The action string that needs to redo
                (e.g. "Tap the Wi-Fi toggle to enable Wi-Fi").
        image:  Annotated PIL Image from the grounder — bounding boxes and
                ID badges are already drawn, giving the MLLM full visual context.

    Returns:
        ProposerOutput with:
        - square_indices  — grid cells the MLLM selected
        - proposed_image  — cropped PIL Image covering those cells
        - center_point    — (x, y) centre in original image coordinates
    """
    _logger.info("Proposing region for action: %.120s", action)

    if Config().mock_mode:
        result = _mock_propose(image)
        _logger.info(
            "[MOCK] centre cell %s  center=%s",
            result.square_indices,
            result.center_point,
        )
        return result

    cols, rows = _choose_grid(image)
    # Pad before dividing so every cell meets the minimum size requirement.
    # Padded pixels are black — the MLLM naturally ignores empty padding cells.
    # The original (unpadded) image is kept for the final crop so the proposed
    # area never contains synthetic padding content.
    padded = _pad_to_grid(image, cols, rows)
    cells = _make_cells(padded, cols, rows)
    _logger.debug("Grid: %d cols × %d rows = %d cells", cols, rows, len(cells))

    grid_image = _draw_grid(padded, cells)

    user_message = (
        f"Action to resolve:\n{action}\n\n"
        f"The grid has {cols} columns × {rows} rows = {len(cells)} cells total. "
        "Select every cell index that contains content relevant to this action."
    )

    mllm = _ProposerMllm()

    try:
        selection = mllm.complete(user_message=user_message, image=grid_image)
    except MllmOutputError as e:
        _logger.error("Proposer MLLM output invalid: %s", e)
        raise
    except litellm.APIError as e:
        _logger.error("Proposer MLLM API error: %s", e)
        raise

    indices = selection.selected_indices
    _logger.info("Selected cells: %s", indices)

    proposed_image, center = _extract_proposed(image, cells, indices)
    _logger.info("Proposed area centre: %s", center)

    return ProposerOutput(
        square_indices=indices,
        proposed_image=proposed_image,
        center_point=center,
    )
