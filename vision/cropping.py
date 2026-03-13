"""
Cropping/Zoom for Vision Module

Crops and zooms into candidate regions proposed by MLLM.
Provides detailed views of specific UI areas.

Reference: 
    RegionFocus: Visual Test-time Scaling for GUI Agent Grounding
    https://arxiv.org/abs/2505.00684
    https://github.com/tiangeluo/RegionFocus

This module implements the cropping and upsampling pipeline for precise
GUI element localization through iterative region focus refinement.
"""

import io
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw


# Cropping constants
DEFAULT_CROP_RATIOS = [(0.5, 0.5), (0.3, 0.3), (0.4, 0.8), (0.8, 0.4)]  # ratio_x, ratio_y


@dataclass
class CropContext:
    """
    Context information for converting coordinates from zoomed image back to original image space.
    
    Used to track the transformation applied during crop and upsample operations,
    enabling accurate coordinate projection from fine-grained predictions back to
    the original screenshot coordinates.
    
    Attributes:
        left (int): X-coordinate of crop region's top-left corner in original image
        top (int): Y-coordinate of crop region's top-left corner in original image
        original_width (int): Width of the original crop region before upsampling
        original_height (int): Height of the original crop region before upsampling
        zoom_x (float): Zoom factor applied on x-axis 
        zoom_y (float): Zoom factor applied on y-axis
        offset_w (float): Horizontal offset from viewport edge (for centered cropping)
        offset_h (float): Vertical offset from viewport edge (for centered cropping)
    """
    left: int
    top: int
    original_width: int
    original_height: int
    zoom_x: float
    zoom_y: float
    offset_w: float
    offset_h: float


@dataclass
class FocusRegion:
    """
    Result of cropping and upsampling a region of interest.
    
    Contains the zoomed image in bytes format and transformation context
    needed to project coordinates back to original image space.
    
    Attributes:
        image_bytes (bytes): PNG-encoded bytes of the upsampled region
        context (CropContext): Coordinate transformation context for unprojection
        original_image_size (Tuple[int, int]): (width, height) of original screenshot
    """
    image_bytes: bytes
    context: CropContext
    original_image_size: Tuple[int, int]

def propose_candidate_points(
    instruction: str,
    image: Any,
    vlm_client: Any,
    temperatures: Optional[List[float]] = None,
    top_p: float = 0.9,
    system_message: Optional[Dict] = None,
    debug: bool = False,
    task_id: Optional[str] = None
) -> Tuple[List[Tuple[int, int]], List[str]]:
    """
    Propose candidate points in an image using VLM with temperature variation.
    
    This function queries the multimodal VLM multiple times with different temperature
    values to generate diverse candidate points. Higher temperature values encourage
    more exploratory predictions, while lower temperatures produce more confident
    predictions. The first valid point found is returned (early stopping).
    
    The temperature schedule allows the model to explore different interpretations
    of spatial references and UI element positions while maintaining a base level
    of consistency through deterministic (temperature=0) grounding.
    
    Process:
        1. For each temperature value in the schedule:
            a. Encode image to base64 for API transmission
            b. Build prompt asking model to locate coordinates matching instruction
            c. Call VLM endpoint with specified temperature and top_p
            d. Parse response for coordinate extraction
            e. Normalize coordinates to [0, 1] range
            f. If valid point found, add to candidates and break
        2. Return list of candidate points (pixel coordinates) and raw responses
    
    Args:
        instruction (str): 
            Natural language description of the target UI element.
            Example: "Click the save button in the top right corner"
            
        image (PIL.Image or str or np.ndarray):
            Input screenshot/image to analyze.
            - PIL.Image: Will be encoded to PNG bytes
            - str: Treated as file path, loaded as PIL.Image
            - np.ndarray: Converted to PIL.Image
            
        vlm_client (Any):
            OpenAI-compatible API client instance with:
            - _call_endpoint(messages, temperature, top_p) method
            - Returns raw text response from model
            
        temperatures (List[float], optional):
            Temperature schedule for sampling diversity.
            Default: [0.0, 0.3, 0.5, 0.7, 0.9]
            - 0.0: Deterministic, selects highest probability
            - 0.3-0.7: Balanced exploration/exploitation
            - 0.9: High diversity, exploratory predictions
            
        top_p (float):
            Nucleus sampling threshold. Default: 0.9
            - Controls the cumulative probability mass to sample from
            - 0.9 means sample from top 90% of probability distribution
            
        system_message (Dict, optional):
            System prompt configuration dict with structure:
            {
                "role": "system",
                "content": [{"type": "text", "text": "..."}, ...]
            }
            Used to provide model with function calling context.
            
        debug (bool):
            If True, save intermediate visualizations and responses.
            Default: False
            
        task_id (str, optional):
            Task identifier for organizing debug outputs.
            Debug artifacts saved to: ./debug/{task_id}/
    
    Returns:
        Tuple[List[Tuple[int, int]], List[str]]:
            A tuple containing:
            - List of candidate points as (x_pixel, y_pixel) tuples in original image space
              (NOT normalized, actual pixel coordinates)
              Example: [(640, 360), (650, 365)]
            - List of raw VLM responses corresponding to each candidate point
              
            If no valid points found, returns ([], [])
    
    Raises:
        ValueError: If image cannot be loaded or processed
        TypeError: If vlm_client lacks required _call_endpoint method
    
    Notes:
        - Early stopping: Returns after first successful temperature (does not try all)
        - Normalization reversal: Points are denormalized using image dimensions 
          to return pixel coordinates, not [0, 1] normalized values
        - Response parsing expects JSON in format: `<tool_call>\\n{json}\\n</tool_call>`
        - Failed parsing returns None for that candidate point
        
    Example:
        ```python
        points, responses = propose_candidate_points(
            instruction="Click the download button",
            image="screenshot.png",
            vlm_client=qwen_client,
            temperatures=[0.0, 0.3, 0.5],
            system_message=system_msg,
            debug=True,
            task_id="task_001"
        )
        
        # Output: points = [(512, 256), (520, 260)]
        #         responses = [json_str_1, json_str_2]
        
        for point in points:
            x_pixel, y_pixel = point
            # Use pixel coordinates for downstream processing
        ```
    """
    pass


def calculate_crop_region(
    candidate_point: Tuple[int, int],
    image: Any,
    ratio_x: float = 0.5,
    ratio_y: float = 0.5,
    debug: bool = False,
    task_id: Optional[str] = None,
    index: Optional[int] = None
) -> Tuple[int, int, int, int]:
    """
    Calculate the crop region bounding box around a candidate point.
    
    This function determines the rectangular region to extract from the original
    image, centered on the candidate point but bounded by image dimensions.
    
    Process:
        1. Extract image dimensions (treats as viewport size)
        2. Clamp candidate point to valid bounds
        3. Calculate crop dimensions: crop_w = viewport_w * ratio_x
        4. Center crop on candidate point: left = x_center - crop_w/2
        5. Adjust for boundary violations (left, right, top, bottom clamping)
        6. Return final crop box
    
    Args:
        candidate_point (Tuple[int, int]):
            (x_pixel, y_pixel) to center crop around
            
        image (PIL.Image or str or np.ndarray):
            Original image to get dimensions from
            
        ratio_x (float):
            Fraction of image width to crop. Default: 0.5
            
        ratio_y (float):
            Fraction of image height to crop. Default: 0.5
            
        debug (bool):
            If True, save visualization of crop region
            
        task_id (str, optional):
            Task ID for debug directory organization
            
        index (int, optional):
            Index for debug filename
    
    Returns:
        Tuple[int, int, int, int]:
            (left, top, width, height) of crop region in original image space
    
    References:
        - RegionFocus paper: https://arxiv.org/pdf/2505.00684
    """
    # Load image and get dimensions
    if isinstance(image, str):
        pil_img = Image.open(image)
    elif isinstance(image, np.ndarray):
        pil_img = Image.fromarray(image)
    else:
        pil_img = image

    viewport_width, viewport_height = pil_img.size
    x_center, y_center = candidate_point

    # Clamp coordinates to bounds
    x_center = max(0, min(x_center, viewport_width - 1))
    y_center = max(0, min(y_center, viewport_height - 1))

    # Calculate crop dimensions
    crop_w = float(viewport_width * ratio_x)
    crop_h = float(viewport_height * ratio_y)

    # Initial crop region centered on focus point
    left = x_center - crop_w / 2
    top = y_center - crop_h / 2
    right = left + crop_w
    bottom = top + crop_h

    # Adjust horizontally if out of bounds
    if left < 0:
        shift = -left
        left += shift
        right += shift
    if right > viewport_width:
        shift = right - viewport_width
        left -= shift
        right -= shift

    # Adjust vertically if out of bounds
    if top < 0:
        shift = -top
        top += shift
        bottom += shift
    if bottom > viewport_height:
        shift = bottom - viewport_height
        top -= shift
        bottom -= shift

    # Final safety clamp
    left = max(0, left)
    top = max(0, top)
    right = min(viewport_width, right)
    bottom = min(viewport_height, bottom)

    # Debug visualization
    if debug:
        debug_dir = f"./debug/{task_id}" if task_id else "./debug"
        os.makedirs(debug_dir, exist_ok=True)

        debug_img = pil_img.copy()
        draw = ImageDraw.Draw(debug_img)

        # Draw the point of interest
        point_radius = 5
        draw.ellipse(
            (x_center - point_radius, y_center - point_radius, 
             x_center + point_radius, y_center + point_radius),
            fill=(255, 0, 0)
        )

        # Draw the crop rectangle
        draw.rectangle(
            [(left, top), (right, bottom)],
            outline=(0, 255, 0),
            width=2
        )

        crop_debug_filename = f"crop_region_{index}.png" if index is not None else "crop_region.png"
        debug_img.save(os.path.join(debug_dir, crop_debug_filename))

    return int(left), int(top), int(right - left), int(bottom - top)


def crop_and_upsample_region(
    candidate_point: Tuple[int, int],
    original_image: Any,
    crop_ratios: Optional[List[Tuple[float, float]]] = None,
    keep_aspect_ratio: bool = True,
    debug: bool = False,
    task_id: Optional[str] = None,
    index: Optional[int] = None
) -> List[FocusRegion]:
    """
    Crop around a candidate point and upsample at multiple scale ratios.
    
    This function generates multiple zoomed views of the candidate region at
    different crop ratios, enabling fine-grained prediction at various levels
    of zoom. Each zoomed region includes transformation metadata allowing
    coordinate projection back to the original image space.
    
    The multi-ratio approach handles diverse UI element sizes and aspect ratios:
    - Square crops (0.5, 0.5): Balanced crops centered on point
    - Small focused crop (0.3, 0.3): Tight zoom for precise elements
    - Vertical-oriented crop (0.4, 0.8): For tall UI elements
    - Horizontal-oriented crop (0.8, 0.4): For wide UI elements
    
    Process for each crop ratio:
        1. **Calculate Crop Region**: Center crop on point, expand by ratio, clamp to bounds
        2. **Extract Crop**: Extract bounding box from original image
        3. **Calculate Zoom Factors**: Determine upsampling scale preserving aspect ratio
        4. **Resample & Upsample**: Resize with LANCZOS interpolation, convert to PNG bytes
        5. **Create Context**: Package transformation metadata for coordinate un-projection
    
    Args:
        candidate_point (Tuple[int, int]):
            Point (x_pixel, y_pixel) to center crop around.
            Must be in original image pixel coordinates.
            Example: (640, 480)
            
        original_image (PIL.Image or str or np.ndarray):
            Original screenshot to crop from.
            
        crop_ratios (List[Tuple[float, float]], optional):
            Crop size ratios as (ratio_x, ratio_y).
            Default: [(0.5, 0.5), (0.3, 0.3), (0.4, 0.8), (0.8, 0.4)]
            
        keep_aspect_ratio (bool):
            If True, preserve original image aspect ratio during upsampling.
            Default: True
            
        debug (bool):
            If True, save crop and upsample visualizations.
            Default: False
            
        task_id (str, optional):
            Task identifier for debug output organization
            
        index (int, optional):
            Index for debug filenames
    
    Returns:
        List[FocusRegion]:
            List of zoomed region objects, one per crop ratio, each containing:
            - image_bytes: PNG-encoded bytes of upsampled region
            - context: CropContext with transformation metadata
            - original_image_size: (width, height) of original screenshot
    
    Notes:
        **Coordinate Un-projection**:
        Given a point (x_zoom, y_zoom) on zoomed image, convert back to
        original image coordinates using CropContext:
        
        ```python
        zoomed_width = context.original_width * context.zoom_x
        zoomed_height = context.original_height * context.zoom_y
        
        # Clamp point to zoomed area
        x_zoom = max(0, min(x_zoom, zoomed_width))
        y_zoom = max(0, min(y_zoom, zoomed_height))
        
        # Un-project to original coordinates
        x_original = context.left + (x_zoom / context.zoom_x)
        y_original = context.top + (y_zoom / context.zoom_y)
        ```
    
    References:
        - RegionFocus paper: https://arxiv.org/pdf/2505.00684
    """
    if crop_ratios is None:
        crop_ratios = DEFAULT_CROP_RATIOS

    # Load original image
    if isinstance(original_image, str):
        img = Image.open(original_image)
    elif isinstance(original_image, np.ndarray):
        img = Image.fromarray(original_image)
    else:
        img = original_image

    img_width, img_height = img.size
    zoomed_regions = []

    # Process each crop ratio
    for ratio_x, ratio_y in crop_ratios:
        # Step 1: Calculate crop region
        left, top, w, h = calculate_crop_region(
            candidate_point,
            original_image,
            ratio_x=ratio_x,
            ratio_y=ratio_y,
            debug=debug,
            task_id=task_id,
            index=index
        )

        # Step 2: Extract crop
        cropped = img.crop((left, top, left + w, top + h))

        if debug:
            debug_dir = f"./debug/{task_id}" if task_id else "./debug"
            os.makedirs(debug_dir, exist_ok=True)
            crop_filename = f"crop_{index}.png" if index is not None else "crop.png"
            cropped.save(os.path.join(debug_dir, crop_filename))

        # Step 3: Calculate zoom factors
        viewport_width = img_width
        viewport_height = img_height

        if not keep_aspect_ratio:
            # Stretch to viewport dimensions
            upsampled = cropped.resize((viewport_width, viewport_height), Image.Resampling.LANCZOS)
            zoom_x = viewport_width / w
            zoom_y = viewport_height / h
            offset_w = 0.0
            offset_h = 0.0
        else:
            # Preserve aspect ratio
            zoom_x = viewport_width / w
            zoom_y = viewport_height / h
            zoom_factor = min(zoom_x, zoom_y)

            # Apply same zoom factor to both dimensions
            new_w = round(w * zoom_factor)
            new_h = round(h * zoom_factor)
            upsampled = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # Calculate centering offsets
            offset_w = float(viewport_width - new_w) / 2
            offset_h = float(viewport_height - new_h) / 2

            # Use same zoom factor for both when preserving aspect ratio
            zoom_x = zoom_factor
            zoom_y = zoom_factor

        if debug:
            debug_dir = f"./debug/{task_id}" if task_id else "./debug"
            upsampled_filename = f"upsampled_{index}.png" if index is not None else "upsampled.png"
            upsampled.save(os.path.join(debug_dir, upsampled_filename))

        # Step 4: Convert to PNG bytes
        output_buffer = io.BytesIO()
        upsampled.save(output_buffer, format="PNG")
        screenshot_bytes = output_buffer.getvalue()

        # Step 5: Create context for coordinate un-projection
        context = CropContext(
            left=left,
            top=top,
            original_width=w,
            original_height=h,
            zoom_x=zoom_x,
            zoom_y=zoom_y,
            offset_w=offset_w,
            offset_h=offset_h
        )

        # Create FocusRegion
        zoomed_region = FocusRegion(
            image_bytes=screenshot_bytes,
            context=context,
            original_image_size=(img_width, img_height)
        )

        zoomed_regions.append(zoomed_region)

    return zoomed_regions
