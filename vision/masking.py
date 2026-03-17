"""
Less is More: Context-Aware Masking for Vision Models

Implements the random masking algorithm from "Less is More: Empowering GUI Agent 
with Context-Aware Simplification" (https://arxiv.org/pdf/2507.03730).

The masking strategy introduces structured noise by randomly masking parts of an 
image while optionally preserving a Region of Interest (ROI).

Algorithm:
    Two operating modes based on whether point of interest (x, y) is provided:

    1. **ROI-Preserving Mode** (if x, y provided):
       - Compute ROI: full width, 50% height, centered on y
       - Mask everything OUTSIDE ROI with black (alpha overlay technique)
       - Vision model focuses on interaction-relevant region

    2. **Random Masking Mode** (if x, y NOT provided):
       - Generate random rectangular mask region with size constraints
       - Mask that region with black (direct paste)
       - Model learns robustness to occlusion and missing information

Core Functions:
    - mask_image(): Main entry point (returns PIL.Image)
    - mask_image_bytes(): Wrapper returning PNG bytes
    - random_mask_outside_area(): Internal masking engine
    - compute_roi_region(): ROI calculation helper

Reference: https://arxiv.org/pdf/2507.03730
Source: https://github.com/JiuTian-VL/SimpAgent
"""

import io
import os
import random
from typing import Any, Optional, Tuple, Union

import numpy as np
from PIL import Image, ImageDraw


# Masking Parameters
DEFAULT_MASK_COLOR = (0, 0, 0)  # Black for masking
DEFAULT_WINDOW_MIN = 0.1  # Minimum mask size as fraction
DEFAULT_WINDOW_MAX = 0.5  # Maximum mask size as fraction
DEFAULT_ROI_HEIGHT_RATIO = 0.5  # ROI height = 50% of image height


def compute_roi_region(
    img_width: int,
    img_height: int,
    point_x: float,
    point_y: float
) -> Tuple[int, int, int, int]:
    """
    Compute Region of Interest (ROI) around a point of interest.

    Step 1 from LessIsMore.md:

    The ROI has:
    - Width: Full image width
    - Height: 50% of image height (0.5 × H)
    - Vertical center: Aligned with point_y

    Args:
        img_width (int): Image width in pixels
        img_height (int): Image height in pixels
        point_x (float): X-coordinate of interest (pixel space, unused)
        point_y (float): Y-coordinate of interest (pixel space)

    Returns:
        Tuple[int, int, int, int]: ROI bounds as (left, top, right, bottom)

    Pseudocode (from LessIsMore.md Step 1):
        roi_width = W
        roi_height = 0.5 × H
        ideal_top = y - roi_height / 2
        ideal_bottom = y + roi_height / 2

        if ideal_top < 0:
            top = 0
            bottom = roi_height
        else if ideal_bottom > H:
            bottom = H
            top = H - roi_height
        else:
            top = ideal_top
            bottom = ideal_bottom

        left = 0
        right = W
        return (left, top, right, bottom)
    """
    # ROI dimensions
    roi_width = img_width
    roi_height = DEFAULT_ROI_HEIGHT_RATIO * img_height  # 0.5 × H

    # Compute vertical position centered on point_y
    ideal_top = point_y - roi_height / 2
    ideal_bottom = point_y + roi_height / 2

    # Clamp to image bounds
    if ideal_top < 0:
        top = 0
        bottom = int(roi_height)
    elif ideal_bottom > img_height:
        bottom = img_height
        top = int(img_height - roi_height)
    else:
        top = int(ideal_top)
        bottom = int(ideal_bottom)

    # ROI spans full width
    left = 0
    right = img_width

    return left, top, right, bottom


def random_mask_outside_area(
    image: Image.Image,
    area: Optional[Tuple[int, int, int, int]] = None,
    window_min: float = DEFAULT_WINDOW_MIN,
    window_max: float = DEFAULT_WINDOW_MAX
) -> Image.Image:
    """
    Apply masking based on area presence.

    Implements Step 2 & 3 from LessIsMore.md:
    - ALWAYS generates random mask region (Step 2)
    - Then applies mask based on whether area (ROI) exists (Step 3)

    Two cases:

    Case A - No ROI (area is None):
        Directly mask the random region with black

    Case B - ROI exists (area is not None):
        Mask everything OUTSIDE the ROI using alpha overlay

    Args:
        image (PIL.Image): RGB image to mask
        area (Tuple or None): ROI bounds as (left, top, right, bottom)
                            None means random masking mode
        window_min (float): Minimum mask size as fraction
        window_max (float): Maximum mask size as fraction

    Returns:
        PIL.Image: Masked image (RGB mode)

    Step 2 (from LessIsMore.md):
        mask_width ~ Uniform(window_min × W, window_max × W)
        mask_height ~ Uniform(window_min × H, window_max × H)
        mask_left ~ Uniform(0, W - mask_width)
        mask_top ~ Uniform(0, H - mask_height)
        mask_right = mask_left + mask_width
        mask_bottom = mask_top + mask_height

    Step 3A - No ROI (Case A):
        black_patch = black image with size (mask_width, mask_height)
        paste black_patch onto image at (mask_left, mask_top)

    Step 3B - With ROI (Case B):
        mask_image = grayscale(0) everywhere
        draw rectangle(roi) with value 255
        overlay = RGBA black
        set overlay.alpha = mask_image
        paste overlay onto image with alpha mask
    """
    width, height = image.size

    # Step 2: Generate random mask region (ALWAYS, regardless of area)
    mask_width = int(random.uniform(window_min * width, window_max * width))
    mask_height = int(random.uniform(window_min * height, window_max * height))

    # Clamp mask dimensions to image bounds
    mask_width = min(mask_width, width)
    mask_height = min(mask_height, height)

    # Sample top-left position
    max_left = max(0, width - mask_width)
    max_top = max(0, height - mask_height)

    mask_left = int(random.uniform(0, max_left)) if max_left > 0 else 0
    mask_top = int(random.uniform(0, max_top)) if max_top > 0 else 0

    mask_right = mask_left + mask_width
    mask_bottom = mask_top + mask_height

    # Step 3: Apply mask based on area
    if area is not None:
        # Case B: ROI preservation (mask everything OUTSIDE area)
        left, top, right, bottom = area

        # Create grayscale mask: 0 (black) everywhere, 255 (white) in ROI
        mask_layer = Image.new('L', (width, height), 0)
        mask_draw = ImageDraw.Draw(mask_layer)
        mask_draw.rectangle([left, top, right, bottom], fill=255)

        # Create black RGBA overlay
        overlay = Image.new('RGBA', (width, height), DEFAULT_MASK_COLOR + (255,))

        # Apply grayscale mask as alpha channel
        overlay.putalpha(mask_layer)

        # Convert image to RGBA if needed and paste overlay
        result = image.convert('RGBA') # image.paste(image.convert('RGBA'), (0, 0))
        result.paste(overlay, (0, 0), overlay)

        return result.convert('RGB')

    else:
        # Case A: Random masking (mask the random region)
        # Create black patch at random location
        patch = Image.new('RGB', (mask_width, mask_height), DEFAULT_MASK_COLOR)

        # Paste patch onto image
        masked_image = image.copy()
        masked_image.paste(patch, (mask_left, mask_top))

        return masked_image


def mask_image(
    screenshot: Union[str, Any],
    x: float = -1,
    y: float = -1,
    window_min: float = DEFAULT_WINDOW_MIN,
    window_max: float = DEFAULT_WINDOW_MAX,
    debug: bool = False,
    task_id: Optional[str] = None
) -> Image.Image:
    """
    Apply masking algorithm from LessIsMore paper.

    Main entry point implementing the complete masking pipeline.

    Orchestrates the algorithm:
    1. Load image
    2. If point (x, y) provided: Compute ROI region
    3. Call masking engine with area (or None for random mode)
    4. Return masked image

    Args:
        screenshot (str or PIL.Image or np.ndarray):
            Input image to mask
            - str: File path to image file
            - PIL.Image: Image object (any mode, converted to RGB)
            - np.ndarray: NumPy array (converted to PIL.Image)

        x (float): X-coordinate of point of interest
                  -1 or negative = no point provided (random masking mode)
                  Pixel coordinates in original image space
          
        y (float): Y-coordinate of point of interest
                  -1 or negative = no point provided (random masking mode)
                  Pixel coordinates in original image space
          
        window_min (float): Minimum mask region size as fraction [0.0, 1.0]
                          Default: 0.1 (10% of dimension)
                          Only used in Case A (no ROI)
                  
        window_max (float): Maximum mask region size as fraction [0.0, 1.0]
                          Default: 0.5 (50% of dimension)
                          Only used in Case A (no ROI)

        debug (bool): If True, save visualization
                     Saves to ./debug/{task_id}/masked_{mode}.png
                     Default: False
             
        task_id (str, optional): Task identifier for debug output organization

    Returns:
        PIL.Image: Masked image (RGB mode)

    Raises:
        ValueError: If screenshot file path not found

    Algorithm (Orchestration):
        1. Load image from path/PIL/array
        2. If x >= 0 and y >= 0:
            area = compute_roi_region(width, height, x, y)
        else:
            area = None
        3. masked_image = random_mask_outside_area(image, area, window_min, window_max)
        4. return masked_image

    Example - ROI-Preserving Mode (point of interest provided):
        ```python
        masked_img = mask_image(
            screenshot="screenshot.png",
            x=960,
            y=540,
            window_min=0.1,
            window_max=0.5,
            debug=True,
            task_id="interaction_001"
        )
        # Result: ROI region around (960, 540) visible, rest black
        ```

    Example - Random Masking Mode (no point of interest):
        ```python
        masked_img = mask_image(
            screenshot="screenshot.png",
            x=-1,
            y=-1,
            window_min=0.1,
            window_max=0.5,
            debug=False
        )
        # Result: Random rectangular region masked with black
        ```
    """
    # Load image
    if isinstance(screenshot, str):
        if not os.path.exists(screenshot):
            raise ValueError(f"Screenshot file not found: {screenshot}")
        img = Image.open(screenshot).convert("RGB")
    elif isinstance(screenshot, np.ndarray):
        img = Image.fromarray(screenshot).convert("RGB")
    else:
        # Assume PIL.Image
        img = screenshot.convert("RGB")

    img_width, img_height = img.size

    # Determine operating mode
    has_point = (x >= 0 and y >= 0)

    # Step 1: Compute ROI if point provided, otherwise area is None
    if has_point:
        area = compute_roi_region(img_width, img_height, x, y)
        mode = "roi"
    else:
        area = None
        mode = "random"

    # Step 2-3: Apply masking
    masked_img = random_mask_outside_area(img, area, window_min, window_max)

    # Debug visualization
    if debug:
        debug_dir = f"./debug/{task_id}" if task_id else "./debug"
        os.makedirs(debug_dir, exist_ok=True)

        debug_filename = f"masked_{mode}.png"
        debug_path = os.path.join(debug_dir, debug_filename)
        masked_img.save(debug_path)

    return masked_img


def mask_image_bytes(
    screenshot: Union[str, Any],
    x: float = -1,
    y: float = -1,
    window_min: float = DEFAULT_WINDOW_MIN,
    window_max: float = DEFAULT_WINDOW_MAX,
    debug: bool = False,
    task_id: Optional[str] = None
) -> bytes:
    """
    Apply masking algorithm and return PNG-encoded bytes.

    Convenience wrapper around mask_image() that returns PNG bytes
    instead of PIL.Image object. Useful for API responses or serialization.

    Args:
        Same as mask_image()

    Returns:
        bytes: PNG-encoded masked image data

    Example:
        ```python
        png_bytes = mask_image_bytes(
            screenshot="screenshot.png",
            x=960,
            y=540,
            debug=False
        )
        # Store or transmit png_bytes
        ```
    """
    masked_img = mask_image(screenshot, x, y, window_min, window_max, debug, task_id)

    output_buffer = io.BytesIO()
    masked_img.save(output_buffer, format="PNG")
    return output_buffer.getvalue()
