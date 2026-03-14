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

import cv2
import numpy as np
from PIL import Image, ImageDraw

# Cropping constants
DEFAULT_CROP_RATIOS = [(0.5, 0.5), (0.3, 0.3), (0.4, 0.8), (0.8, 0.4)]  # ratio_x, ratio_y

# Information-Sensitive Cropping constants
DEFAULT_K_MIN = 64  # Initial window size
DEFAULT_RHO_MIN = 0.15  # Base density threshold
DEFAULT_ALPHA = 1.5  # Window expansion factor
DEFAULT_N_MAX = 50  # Maximum number of regions to extract


@dataclass
class ISCRegion:
    """
    Region extracted by adaptive region extraction algorithm.
    
    Represents a rectangular region identified as information-dense
    by the edge-based adaptive extraction method.
    
    Attributes:
        x (int): Top-left x-coordinate in original image
        y (int): Top-left y-coordinate in original image
        size (int): Width and height of the square region
        id (int): Unique region identifier
        density (float): Edge density score in [0, 1]
    """
    x: int
    y: int
    size: int
    id: int
    density: float


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


def detect_edge_matrix(
    image: Any,
    threshold_low: Optional[int] = None,
    threshold_high: Optional[int] = None,
    debug: bool = False,
    task_id: Optional[str] = None
) -> np.ndarray:
    """
    Detect edges in image to generate information indication matrix.
    
    This function converts an image to an edge detection matrix where each pixel
    value indicates the presence of meaningful visual information (typically at
    boundaries of UI elements). The resulting matrix is used by the adaptive
    region extraction algorithm to identify information-dense regions.
    
    Edge detection identifies visually significant regions by leveraging the
    observation that meaningful GUI elements typically have distinctive boundaries.
    
    Process:
        1. Convert image to grayscale if needed
        2. Apply edge detection method (Canny, Sobel, etc.)
        3. Normalize edge values to [0, 1] range
        4. Return binary edge matrix where 1 indicates edge presence
    
    Args:
        image (PIL.Image or str or np.ndarray):
            Input screenshot/image to process.
            - PIL.Image: Converted to grayscale
            - str: Loaded as image file
            - np.ndarray: Treated as RGB or grayscale
            
        edge_method (str):
            Edge detection algorithm to use.
            Default: "canny"
            Options: "canny", "sobel", "laplacian", "prewitt"
            
        threshold_low (int, optional):
            Low threshold for edge detection methods.
            Default: Automatically estimated from image
            
        threshold_high (int, optional):
            High threshold for edge detection methods.
            Default: Automatically estimated from image
            
        debug (bool):
            If True, save edge detection visualization.
            Default: False
            
        task_id (str, optional):
            Task identifier for debug output organization.
            Debug files saved to: ./debug/{task_id}/
    
    Returns:
        np.ndarray:
            Binary edge matrix M ∈ {0, 1}^(H×W) where:
            - M[i, j] = 1: Indicates meaningful visual information at (i, j)
            - M[i, j] = 0: No significant edge/information
            
            Shape: (height, width) - same as input image
            Dtype: np.uint8 (values 0 or 1)
    
    Raises:
        ValueError: If image cannot be processed or edge_method is invalid
        ImportError: If required edge detection library is not available
    
    Notes:
        - Edge detection emphasizes boundaries of UI elements
        - Output matrix is normalized to binary values for downstream processing
        - Thresholds are auto-estimated if not provided based on image statistics
        
    Example:
        ```python
        # Detect edges in screenshot
        edge_matrix = detect_edge_matrix(
            image="screenshot.png",
            edge_method="canny",
            debug=True,
            task_id="task_001"
        )
        
        # edge_matrix.shape == (1080, 1920)
        # edge_matrix.dtype == np.uint8
        # Values are all 0 or 1
        ```
    
    References:
        - Information-Sensitive Cropping paper: https://arxiv.org/pdf/2412.10342
        - Iris: Breaking GUI Complexity with Adaptive Focus and Self-Refining
    """
    # Load and convert image to numpy array
    if isinstance(image, str):
        img = Image.open(image)
        img_array = np.array(img)
    elif isinstance(image, np.ndarray):
        img_array = image
    else:
        # PIL.Image
        img_array = np.array(image)

    # STAGE 1: Pre-processing - Convert to grayscale and apply CLAHE
    if len(img_array.shape) == 3:
        # Convert RGB/BGR to grayscale
        if img_array.shape[2] == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        elif img_array.shape[2] == 4:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGBA2GRAY)
        else:
            gray = img_array[:, :, 0]
    else:
        gray = img_array

    # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
    # Parameters from document: clipLimit=2.0, tileGridSize=(8,8)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # STAGE 2: Noise reduction - Gaussian blur
    # Parameter from document: sigma=1.0
    blurred = cv2.GaussianBlur(enhanced, (5, 5), sigmaX=1.0, sigmaY=1.0)

    # STAGE 3-4: Gradient computation and Canny edge detection
    # CV2.Canny handles: gradient computation, non-maximum suppression, hysteresis thresholding
    if threshold_low is None:
        threshold_low = 50  # Default from document
    if threshold_high is None:
        threshold_high = 150  # Default from document

    edges = cv2.Canny(blurred, threshold_low, threshold_high)

    # STAGE 5: Edge density preservation - Morphological dilation
    # Parameter from document: kernel=3x3, iterations=1-2
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated = cv2.dilate(edges, kernel, iterations=2)

    # Ensure output is binary (0 or 1)
    M = (dilated > 0).astype(np.uint8)

    # Debug visualization
    if debug:
        debug_dir = f"./debug/{task_id}" if task_id else "./debug"
        os.makedirs(debug_dir, exist_ok=True)

        # Save intermediate stages for visual inspection
        cv2.imwrite(os.path.join(debug_dir, "01_grayscale.png"), gray)
        cv2.imwrite(os.path.join(debug_dir, "02_clahe_enhanced.png"), enhanced)
        cv2.imwrite(os.path.join(debug_dir, "03_blurred.png"), blurred)
        cv2.imwrite(os.path.join(debug_dir, "04_canny_edges.png"), edges)
        cv2.imwrite(os.path.join(debug_dir, "05_dilated_edges.png"), dilated)
        cv2.imwrite(os.path.join(debug_dir, "06_binary_matrix.png"), M * 255)

    return M


def adaptive_region_extraction(
    edge_matrix: np.ndarray,
    k_min: int = DEFAULT_K_MIN,
    rho_min: float = DEFAULT_RHO_MIN,
    alpha: float = DEFAULT_ALPHA,
    n_max: int = DEFAULT_N_MAX,
    debug: bool = False,
    task_id: Optional[str] = None
) -> List[ISCRegion]:
    """
    Extract information-dense regions using multi-scale sliding windows.
    
    This algorithm identifies rectangular regions with high visual information
    density by scanning an edge detection matrix at multiple scales. It uses
    sliding window approach with scale-adaptive density thresholds to balance
    sensitivity across different window sizes.
    
    The algorithm progressively increases window size, extracting regions that
    meet density threshold criteria, while preventing overlapping selections by
    zeroing out already-selected regions.
    
    Process:
        1. **Initialize**: k = k_min, regions = []
        2. **Multi-Scale Loop**: While k <= max(height, width) and len(regions) < n_max:
           a. Compute sliding step: step = max(k/4, 32)
           b. Compute density threshold: ρ_k = ρ_min / (k/k_min)²
           c. Slide window across image:
              - For each (x,y) in grid with stride step:
                - If window fits in bounds:
                  - Compute edge density in window
                  - If density >= ρ_k: Extract region, zero out to prevent overlap
           d. Expand window: k = ceil(α * k)
        3. **Sort Results**: Sort regions by density (descending)
        4. **Return**: List of extracted regions
    
    Args:
        edge_matrix (np.ndarray):
            Binary edge detection matrix M ∈ {0, 1}^(H×W).
            - M[i, j] = 1: Indicates meaningful visual information
            - M[i, j] = 0: No significant edge
            Expected shape: (height, width)
            Expected dtype: np.uint8 or np.float32
            
        k_min (int):
            Initial sliding window size in pixels.
            Default: 64
            Range: Typically 32-128 depending on image resolution
            
        rho_min (float):
            Base density threshold for smallest window size.
            Default: 0.15
            Range: [0.0, 1.0]
            - 0.15: ~15% of pixels must be edges to qualify
            - Larger values: More selective (fewer regions)
            - Smaller values: More inclusive (more regions)
            
        alpha (float):
            Window size expansion factor per iteration.
            Default: 1.5
            Typical range: [1.2, 2.0]
            - 1.5: window grows by 50% each iteration
            - Smaller: More scales, more computation
            - Larger: Fewer scales, less computation
            
        n_max (int):
            Maximum number of regions to extract.
            Default: 50
            Stops extraction after this many regions regardless of threshold.
            
        debug (bool):
            If True, save visualization of extracted regions.
            Default: False
            
        task_id (str, optional):
            Task identifier for debug output organization.
            Debug files saved to: ./debug/{task_id}/
    
    Returns:
        List[ISCRegion]:
            List of extracted regions sorted by density (descending).
            
            Each ISCRegion contains:
            - x: Top-left x-coordinate
            - y: Top-left y-coordinate
            - size: Window size (width and height of square region)
            - id: Unique region identifier (1-indexed)
            - density: Edge density score in [0.0, 1.0]
            
            Regions are sorted by density highest-first.
            
            Empty list if no regions found above threshold.
    
    Raises:
        ValueError: If edge_matrix is invalid or parameters out of valid range
        TypeError: If edge_matrix is not np.ndarray
    
    Notes:
        **Density Threshold Scaling**:
        The threshold decreases with window size:
        ```
        ρ_k = ρ_min / (k / k_min)²
        ```
        This prevents larger windows from dominating selection while ensuring
        smaller windows remain selective.
        
        **Sliding Step Strategy**:
        ```
        step = max(k / 4, 32)
        ```
        Smaller windows use finer step (k/4) for detailed coverage.
        Larger windows use coarser step for efficiency.
        
        **Overlap Prevention**:
        Selected regions are zeroed in edge_matrix to prevent overlapping
        selections in subsequent iterations.
        
    Example:
        ```python
        from PIL import Image
        
        # Load image and generate edge matrix
        image = Image.open("screenshot.png")
        edge_matrix = detect_edge_matrix(image)
        
        # Extract information-dense regions
        regions = adaptive_region_extraction(
            edge_matrix,
            k_min=64,
            rho_min=0.15,
            alpha=1.5,
            n_max=50,
            debug=True,
            task_id="task_001"
        )
        
        # Access extracted regions
        for i, region in enumerate(regions):
            print(f"Region {i}: pos=({region.x}, {region.y}), "
                  f"size={region.size}, density={region.density:.3f}")
            
            # Region can be used for cropping:
            # cropped = image.crop((region.x, region.y,
            #                       region.x + region.size,
            #                       region.y + region.size))
        ```
    
    References:
        - Information-Sensitive Cropping (ISC) paper: https://arxiv.org/pdf/2412.10342
        - Iris: Breaking GUI Complexity with Adaptive Focus and Self-Refining
        - Algorithm: AdaptiveRegionExtraction (Section in ISC paper)
    """
    # Validate input
    if not isinstance(edge_matrix, np.ndarray):
        raise TypeError(f"edge_matrix must be np.ndarray, got {type(edge_matrix)}")

    if len(edge_matrix.shape) != 2:
        raise ValueError(f"edge_matrix must be 2D, got shape {edge_matrix.shape}")

    # Make a copy to avoid modifying input
    M = edge_matrix.astype(np.float32).copy()
    height, width = M.shape

    # Initialize
    k = k_min
    regions = []

    # Multi-scale loop
    while k <= max(height, width) and len(regions) < n_max:
        # Step 1: Determine sliding step
        step = max(int(k / 4), 32)

        # Step 2: Compute density threshold for this scale
        rho_k = rho_min / ((k / k_min) ** 2)

        # Step 3: Slide window across image
        for y in range(0, height, step):
            for x in range(0, width, step):
                # Check window boundaries
                if x + k > width or y + k > height:
                    continue

                # Compute edge density in window
                window = M[y : y + k, x : x + k]
                density = float(np.sum(window) / (k * k))

                # Check density threshold
                if density >= rho_k and len(regions) < n_max:
                    # Create region
                    region_id = len(regions) + 1
                    region = ISCRegion(
                        x=x,
                        y=y,
                        size=k,
                        id=region_id,
                        density=density
                    )
                    regions.append(region)

                    # Prevent overlapping regions by zeroing out selected area
                    M[y : y + k, x : x + k] = 0

        # Step 4: Expand window size
        k = int(np.ceil(alpha * k))

    # Sort regions by density (descending)
    regions.sort(key=lambda r: r.density, reverse=True)

    # Debug visualization
    if debug:
        debug_dir = f"./debug/{task_id}" if task_id else "./debug"
        os.makedirs(debug_dir, exist_ok=True)

        # Create visualization image showing extracted regions
        debug_img = Image.new("RGB", (width, height), color=(255, 255, 255))
        draw = ImageDraw.Draw(debug_img)

        colors = [
            (255, 0, 0),      # Red
            (0, 255, 0),      # Green
            (0, 0, 255),      # Blue
            (255, 255, 0),    # Yellow
            (255, 0, 255),    # Magenta
            (0, 255, 255),    # Cyan
        ]

        for i, region in enumerate(regions):
            color = colors[i % len(colors)]
            left = region.x
            top = region.y
            right = region.x + region.size
            bottom = region.y + region.size

            # Draw rectangle with region ID
            draw.rectangle(
                [(left, top), (right, bottom)],
                outline=color,
                width=2
            )

            # Draw region ID and density
            label = f"R{region.id} ({region.density:.2f})"
            draw.text((left + 5, top + 5), label, fill=color)

        debug_img.save(os.path.join(debug_dir, "extracted_regions.png"))

    return regions
