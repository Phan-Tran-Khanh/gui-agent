"""
Cropping/Zoom for Vision Module

Crops and zooms into candidate regions proposed by MLLM.
Provides detailed views of specific UI areas.

Reference: https://arxiv.org/abs/2505.00684

TODO - Implementation Instructions:
    1. Define CroppedRegion dataclass:
        - id, original_bbox, zoom_level, cropped_image, context
    2. Implement Cropper class:
        - Constructor takes config
        - Initialize logger
    3. Implement crop_regions(screenshot, regions) -> List[CroppedRegion]:
        - For each region bbox
        - Crop with padding/margin
        - Apply zoom if configured
        - Return list of CroppedRegion
    4. Implement calculate_crop_with_context(bbox, image_size) -> new_bbox:
        - Expand bbox with padding
        - Ensure within image bounds
        - Return expanded bbox
    5. Implement zoom(cropped_image, zoom_level) -> zoomed_image:
        - Apply zoom/interpolation
        - Return zoomed image
    6. Add margin/padding configuration
    7. Add logging
"""

from typing import List, Tuple, Optional


class CroppedRegion:
    """
    TODO - Implementation Instructions:
        1. Define __init__ with id, original_bbox, zoom_level, cropped_image, context
        2. Implement to_dict()
    """
    pass


class Cropper:
    """
    TODO - Implementation Instructions:
        1. Define __init__(self, config):
            - Get crop_margin from config
            - Get zoom_level from config
            - Initialize logger
        2. Implement crop_regions(screenshot: bytes, regions: List[Tuple]) -> List[CroppedRegion]:
            - Load image from bytes
            - For each region bbox:
                - Calculate crop with context (padding)
                - Extract crop
                - Apply zoom if configured
                - Create CroppedRegion
            - Return list of CroppedRegion
        3. Implement calculate_crop_with_context(bbox, image_shape, margin) -> extended_bbox:
            - Expand bbox by margin pixels
            - Clip to image bounds
            - Return extended bbox
        4. Implement crop_image(image, bbox) -> cropped:
            - Extract bbox region from image
            - Return cropped image
        5. Implement zoom_image(image, zoom_level) -> zoomed:
            - Apply zoom/interpolation
            - Return zoomed image
    """
    pass


# Cropping constants
DEFAULT_CROP_MARGIN = 20  # pixels padding around crop region
DEFAULT_ZOOM_LEVEL = 1.0  # 1.0 = no zoom, 2.0 = 2x zoom
