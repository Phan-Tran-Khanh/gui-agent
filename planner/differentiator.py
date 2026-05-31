# pylint: disable=no-member,no-name-in-module,invalid-name,catching-non-exception
# cv2 and skimage are C extensions; pylint cannot introspect their members or exceptions.
# invalid-name: Y and X are standard luminance/coordinate notation from the YDiff algorithm.
"""
YDiff Change Detection - Action Effectiveness Verification

Detects if two screenshots are different using YDiff algorithm.
Used to verify if an executed action had visual effect on the UI.

Reference: YDiff.md - YUV Luminance + SSIM + Weighted ROI analysis
Paper: https://arxiv.org/abs/2503.17709

YDiff Algorithm:
    1. Extract luminance (Y) from YUV colorspace
    2. Extract ROI centered at point of interest (POI)
    3. Normalize ROI for scale invariance
    4. Compute SSIM (Structural Similarity) on normalized ROI
    5. Apply weighted Gaussian emphasis near POI center
    6. Return binary: changed = (weighted_ssim < threshold)

Main Entry Point:
    - detect_visual_change(img_prev, img_curr, poi, threshold) → bool (changed or not)

Flexible image input:
    All public functions accept str (file path), np.ndarray (BGR), or PIL.Image.
"""

import logging
import os
from typing import Any, Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as ssim

_logger = logging.getLogger(__name__)

# Type alias for any supported image input
ImageLike = Union[str, np.ndarray, Image.Image]


# ============================================================================
# Image loading helper
# ============================================================================


def _load_as_bgr(img: Any) -> np.ndarray:
    """
    Convert any supported image format to a BGR numpy array.

    Accepts:
        str         — file path; loaded with cv2.imread
        np.ndarray  — assumed already BGR; returned as-is
        PIL.Image   — converted RGB → BGR
    """
    if isinstance(img, str):
        if not os.path.exists(img):
            raise ValueError(f"Image file not found: {img}")
        arr = cv2.imread(img)
        if arr is None:
            raise ValueError(f"cv2 could not read image: {img}")
        return arr
    if isinstance(img, np.ndarray):
        return img
    # Assume PIL.Image
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)


# ============================================================================
# YDiff Helper Functions (From YDiff.md specification)
# ============================================================================


def extract_luminance(img: np.ndarray) -> np.ndarray:
    """
    Extract luminance (Y) channel from BGR image.

    Converts RGB/BGR to YUV and extracts Y (luminance) channel.
    Luminance captures perceptual brightness without color information.

    Args:
        img (np.ndarray): Input image in BGR format

    Returns:
        np.ndarray: Luminance channel as float32

    Example:
        ```python
        Y = extract_luminance(screenshot)
        ```
    """
    if img is None or img.size == 0:
        raise ValueError("Invalid image input")

    yuv = cv2.cvtColor(img, cv2.COLOR_BGR2YUV)
    Y = yuv[:, :, 0].astype(np.float32)
    return Y


def extract_roi(Y: np.ndarray, x: int, y: int, size: int) -> np.ndarray:
    """
    Extract ROI (Region of Interest) centered at point of interest (POI).

    Extracts a square region of specified size centered at (x, y).
    Handles boundary cases gracefully.

    Args:
        Y (np.ndarray): Luminance image
        x (int): X coordinate of POI
        y (int): Y coordinate of POI
        size (int): ROI size (size × size square)

    Returns:
        np.ndarray: ROI region

    Example:
        ```python
        roi = extract_roi(Y, x=540, y=920, size=64)
        ```
    """
    h, w = Y.shape
    half = size // 2

    x1 = max(0, x - half)
    y1 = max(0, y - half)
    x2 = min(w, x + half)
    y2 = min(h, y + half)

    return Y[y1:y2, x1:x2]


def normalize(img: np.ndarray) -> np.ndarray:
    """
    Normalize image by subtracting mean and dividing by standard deviation.

    SSIM is sensitive to scale differences, so normalization improves robustness
    to intensity variations while preserving structural information.

    Args:
        img (np.ndarray): Input image

    Returns:
        np.ndarray: Normalized image (zero mean, unit variance)
    """
    mean = np.mean(img)
    std = np.std(img)
    normalized = (img - mean) / (std + 1e-6)
    return normalized


def compute_ssim(roi1: np.ndarray, roi2: np.ndarray) -> Tuple[float, np.ndarray]:
    """
    Compute Structural Similarity Index (SSIM) between two ROIs.

    SSIM captures perceptual similarity based on:
    - Mean (luminance comparison)
    - Variance (contrast comparison)
    - Covariance (structure comparison)

    SSIM Range: 0 to 1
    - 1.0 = identical
    - Lower values = more different

    Args:
        roi1 (np.ndarray): First ROI
        roi2 (np.ndarray): Second ROI

    Returns:
        Tuple[float, np.ndarray]: (ssim_score ∈ [0,1], ssim_map)

    Example:
        ```python
        score, map = compute_ssim(roi_prev, roi_curr)
        print(f"Similarity: {score:.3f}")
        ```
    """
    # Ensure same shape
    min_h = min(roi1.shape[0], roi2.shape[0])
    min_w = min(roi1.shape[1], roi2.shape[1])
    roi1 = roi1[:min_h, :min_w]
    roi2 = roi2[:min_h, :min_w]

    # data_range is required for float arrays; derive it from the combined value span.
    data_range = (
        float(max(roi1.max(), roi2.max()) - min(roi1.min(), roi2.min())) or 1.0
    )  # guard against zero range on uniform patches
    score, ssim_map = ssim(roi1, roi2, full=True, data_range=data_range)
    return float(score), ssim_map


def weighted_ssim_score(ssim_map: np.ndarray) -> float:
    """
    Compute weighted SSIM focusing on central point of interest.

    Applies Gaussian weighting to emphasize changes near POI center.
    This helps detect subtle but localized UI changes.

    Args:
        ssim_map (np.ndarray): SSIM map from compute_ssim()

    Returns:
        float: Weighted SSIM score (0-1)

    Example:
        ```python
        weighted = weighted_ssim_score(ssim_map)
        ```
    """
    h, w = ssim_map.shape
    cx, cy = w // 2, h // 2

    # Create coordinate grids
    Y, X = np.ogrid[:h, :w]
    dist = (X - cx) ** 2 + (Y - cy) ** 2

    # Gaussian weighting (higher near center)
    sigma = (w / 4) ** 2
    weights = np.exp(-dist / (2 * sigma))

    # Weighted average
    score = np.sum(ssim_map * weights) / np.sum(weights)
    return float(score)


# ============================================================================
# Main YDiff Function - Binary Change Detector
# ============================================================================


def detect_visual_change(
    img_prev: ImageLike,
    img_curr: ImageLike,
    poi: Optional[Tuple[int, int]] = None,
    roi_size: int = 64,
    threshold: float = 0.95,
) -> bool:
    """
    Detect if two screenshots are visually different.

    Accepts str (file path), np.ndarray (BGR), or PIL.Image for both images.

    Uses YDiff algorithm (YUV luminance + SSIM + weighted ROI) to determine
    if an action had visual effect on the UI.

    From YDiff.md specification:
        1. Extract luminance (Y) from YUV
        2. Extract ROI centered at POI
        3. Normalize ROI for scale invariance
        4. Compute SSIM on luminance ROI
        5. Apply weighted emphasis near POI center
        6. Return binary: changed = (weighted_ssim < threshold)

    Args:
        img_prev: Previous screenshot — file path, BGR ndarray, or PIL Image.
        img_curr: Current screenshot  — file path, BGR ndarray, or PIL Image.
        poi (Tuple[int, int], optional): Point of interest (x, y).
                                        If None, uses image center.
        roi_size (int): ROI size in pixels (default: 64).
        threshold (float): SSIM threshold for change detection.
                          - 0.95–0.98: Static UI (default 0.95)
                          - 0.90–0.95: Slight animation
                          - 0.85–0.90: Aggressive detection

    Returns:
        bool: True if images are different (action had effect), False if identical.

    Example:
        ```python
        changed = detect_visual_change(
            "before.png",
            "after.png",
            poi=(540, 920),
            threshold=0.95,
        )
        ```
    """
    try:
        bgr_prev = _load_as_bgr(img_prev)
        bgr_curr = _load_as_bgr(img_curr)

        if bgr_prev is None or bgr_prev.size == 0:
            _logger.error("detect_visual_change: img_prev is empty or unreadable")
            return False
        if bgr_curr is None or bgr_curr.size == 0:
            _logger.error("detect_visual_change: img_curr is empty or unreadable")
            return False

        # Use image centre if POI not specified
        if poi is None:
            h, w = bgr_curr.shape[:2]
            poi = (w // 2, h // 2)

        x, y = poi

        # Step 1: Extract luminance from both images
        y_prev = extract_luminance(bgr_prev)
        y_curr = extract_luminance(bgr_curr)

        # Step 2: Extract ROI around POI
        roi_prev = extract_roi(y_prev, x, y, roi_size)
        roi_curr = extract_roi(y_curr, x, y, roi_size)

        if roi_prev.size == 0 or roi_curr.size == 0:
            _logger.warning("detect_visual_change: ROI is empty for POI (%d, %d)", x, y)
            return False

        # Step 3: Normalize for scale invariance
        roi_prev = normalize(roi_prev)
        roi_curr = normalize(roi_curr)

        # Step 4: Compute SSIM
        _, ssim_map = compute_ssim(roi_prev, roi_curr)

        # Step 5: Apply weighted emphasis near POI
        weighted_score = weighted_ssim_score(ssim_map)

        # Step 6: Decision rule — changed if weighted_ssim < threshold
        changed = weighted_score < threshold
        _logger.debug(
            "detect_visual_change: weighted_ssim=%.4f  threshold=%.2f  changed=%s",
            weighted_score,
            threshold,
            changed,
        )
        return changed

    except (ValueError, cv2.error) as e:
        _logger.error("detect_visual_change failed: %s", e)
        return False


# ============================================================================
# Utility Functions
# ============================================================================


def load_image_from_bytes(img_bytes: bytes) -> Optional[np.ndarray]:
    """
    Load image from PNG/JPG bytes.

    Args:
        img_bytes (bytes): Image data in PNG/JPG format

    Returns:
        Optional[np.ndarray]: Image in BGR format, or None if decoding fails

    Example:
        ```python
        img = load_image_from_bytes(png_bytes)
        if img is not None:
            changed = detect_visual_change(prev_img, img)
        ```
    """
    try:
        nparr = np.frombuffer(img_bytes, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except (ValueError, TypeError) as e:
        _logger.error("load_image_from_bytes failed: %s", e)
        return None


def detect_visual_change_from_bytes(
    img1_bytes: bytes,
    img2_bytes: bytes,
    poi: Optional[Tuple[int, int]] = None,
    threshold: float = 0.95,
) -> bool:
    """
    Detect if two screenshot bytes are visually different.

    Convenience function for comparing PNG/JPG encoded screenshots.

    Args:
        img1_bytes (bytes): First screenshot bytes
        img2_bytes (bytes): Second screenshot bytes
        poi (Tuple, optional): Point of interest for analysis
        threshold (float): SSIM threshold for change detection

    Returns:
        bool: True if images are different, False if identical

    Example:
        ```python
        changed = detect_visual_change_from_bytes(
            screenshot1_bytes,
            screenshot2_bytes,
            poi=(540, 920)
        )
        ```
    """
    img1 = load_image_from_bytes(img1_bytes)
    img2 = load_image_from_bytes(img2_bytes)

    if img1 is None or img2 is None:
        return False

    return detect_visual_change(img1, img2, poi=poi, threshold=threshold)
