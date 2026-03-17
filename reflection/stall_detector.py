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
"""

from typing import Optional, Tuple

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

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

    score, ssim_map = ssim(roi1, roi2, full=True)
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
    dist = (X - cx)**2 + (Y - cy)**2

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
    img_prev: np.ndarray,
    img_curr: np.ndarray,
    poi: Optional[Tuple[int, int]] = None,
    roi_size: int = 64,
    threshold: float = 0.95
) -> bool:
    """
    Detect if two screenshots are visually different.

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
        img_prev (np.ndarray): Previous screenshot (BGR format, numpy array)
        img_curr (np.ndarray): Current screenshot (BGR format, numpy array)
        poi (Tuple[int, int], optional): Point of interest (x, y)
                                        If None, uses image center
        roi_size (int): ROI size in pixels (default: 64)
        threshold (float): SSIM threshold for change detection
                          - 0.95–0.98: Static UI (default 0.95)
                          - 0.90–0.95: Slight animation
                          - 0.85–0.90: Aggressive detection

    Returns:
        bool: True if images are different (action had effect), False if identical

    Example:
        ```python
        # Check if action changed the UI
        changed = detect_visual_change(
            screenshot_before,
            screenshot_after,
            poi=(540, 920),  # Touch coordinate from action
            threshold=0.95
        )

        if changed:
            print("✅ Action succeeded - UI changed")
        else:
            print("❌ Action failed - no visual change")
        ```
    """
    try:
        # Validate inputs
        if img_prev is None or img_prev.size == 0:
            return False

        if img_curr is None or img_curr.size == 0:
            return False

        # Use image center if POI not specified
        if poi is None:
            h, w = img_curr.shape[:2]
            poi = (w // 2, h // 2)

        x, y = poi

        # Step 1: Extract luminance from both images
        Y_prev = extract_luminance(img_prev)
        Y_curr = extract_luminance(img_curr)

        # Step 2: Extract ROI around POI
        roi_prev = extract_roi(Y_prev, x, y, roi_size)
        roi_curr = extract_roi(Y_curr, x, y, roi_size)

        # Validate ROI size
        if roi_prev.size == 0 or roi_curr.size == 0:
            return False

        # Step 3: Normalize for scale invariance
        roi_prev = normalize(roi_prev)
        roi_curr = normalize(roi_curr)

        # Step 4: Compute SSIM
        ssim_raw, ssim_map = compute_ssim(roi_prev, roi_curr)

        # Step 5: Apply weighted emphasis near POI
        weighted_score = weighted_ssim_score(ssim_map)

        # Step 6: Decision rule: changed if weighted_ssim < threshold
        changed = weighted_score < threshold

        return changed

    except Exception as e:
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
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        return None


def detect_visual_change_from_bytes(
    img1_bytes: bytes,
    img2_bytes: bytes,
    poi: Optional[Tuple[int, int]] = None,
    threshold: float = 0.95
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
