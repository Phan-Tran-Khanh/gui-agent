"""
Visual Highlighting for Vision Module

Detects GUI elements using YOLOv8 and Set-of-Mask prompting.
Generates highlighting visualization for MLLM context.

Reference: https://arxiv.org/abs/2412.10342

TODO - Implementation Instructions:
    1. Define HighlightedElement dataclass:
        - id, element_type, bounding_box, center, text, confidence
    2. Implement VisualHighlighter class:
        - Load YOLOv8 model in constructor
        - Cache model loading
    3. Implement detect_elements(screenshot) -> List[HighlightedElement]:
        - Run YOLOv8 inference on screenshot
        - Filter by confidence threshold
        - Extract element info (bbox, type, text)
        - Return list of highlighted elements
    4. Implement generate_highlighted_image(screenshot, elements) -> bytes:
        - Draw bounding boxes on screenshot
        - Add labels/text
        - Return highlighted image bytes
    5. Add model caching to avoid reloading
    6. Add configurable confidence threshold
    7. Add logging
"""

import logging
from typing import List, Optional, Tuple
from dataclasses import dataclass
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont


@dataclass
class ClickAnnotation:
    """Represents a click annotation on a screenshot"""
    x: int
    y: int
    action_type: str = "click"
    label: str = ""
    radius: int = 30
    color: Tuple[int, int, int] = (255, 0, 0)  # Red by default


class ClickAnnotator:
    """
    Utility to annotate screenshots with visual markers showing where clicks happened.
    
    This helps visualize exactly where on your phone screen the coordinates correspond to.
    """

    def __init__(self, logger: logging.Logger = None):
        """
        Initialize the ClickAnnotator.
        
        Args:
            logger: Optional logger instance
        """
        self._logger = logger or logging.getLogger(self.__class__.__name__)

    def annotate_screenshot(
        self,
        screenshot_bytes: bytes,
        annotations: List[ClickAnnotation]
    ) -> bytes:
        """
        Annotate a screenshot with click markers.
        
        Args:
            screenshot_bytes: Screenshot image as bytes
            annotations: List of ClickAnnotation objects
            
        Returns:
            Annotated screenshot as bytes
        """
        try:
            # Load image from bytes
            image = Image.open(BytesIO(screenshot_bytes))
            draw = ImageDraw.Draw(image)
            
            # Try to load a default font, fallback to default if not available
            try:
                font = ImageFont.truetype("arial.ttf", 20)
            except:
                font = ImageFont.load_default()
            
            # Draw each annotation
            for i, annotation in enumerate(annotations):
                self._draw_click_marker(
                    draw,
                    annotation.x,
                    annotation.y,
                    annotation.radius,
                    annotation.color,
                    annotation.label or f"#{i+1} ({annotation.x},{annotation.y})",
                    font
                )
            
            # Convert back to bytes
            output = BytesIO()
            image.save(output, format="PNG")
            return output.getvalue()
        
        except Exception as e:
            self._logger.error(f"Failed to annotate screenshot: {e}")
            return screenshot_bytes

    def _draw_click_marker(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        radius: int = 30,
        color: Tuple[int, int, int] = (255, 0, 0),
        label: str = "",
        font = None
    ):
        """
        Draw a click marker on the image.
        
        Args:
            draw: ImageDraw object
            x: X coordinate of the click
            y: Y coordinate of the click
            radius: Radius of the marker circle
            color: RGB color tuple
            label: Optional label text
            font: Font for label text
        """
        # Draw outer circle (marker)
        draw.ellipse(
            [x - radius, y - radius, x + radius, y + radius],
            outline=color,
            width=3
        )
        
        # Draw center dot
        draw.ellipse(
            [x - 5, y - 5, x + 5, y + 5],
            fill=color
        )
        
        # Draw crosshair
        crosshair_size = 15
        draw.line(
            [(x - crosshair_size, y), (x + crosshair_size, y)],
            fill=color,
            width=2
        )
        draw.line(
            [(x, y - crosshair_size), (x, y + crosshair_size)],
            fill=color,
            width=2
        )
        
        # Draw label if provided
        if label:
            # Add a semi-transparent background for the label
            label_y = y + radius + 10
            bbox = draw.textbbox((x, label_y), label, font=font)
            draw.rectangle(bbox, fill=(*color, 100))
            draw.text((x, label_y), label, fill=(255, 255, 255), font=font)

    def annotate_click(
        self,
        screenshot_bytes: bytes,
        x: int,
        y: int,
        action_type: str = "click",
        label: str = ""
    ) -> bytes:
        """
        Annotate a single click on a screenshot.
        
        Args:
            screenshot_bytes: Screenshot image as bytes
            x: X coordinate of the click
            y: Y coordinate of the click
            action_type: Type of action (click, long_press, etc.)
            label: Optional label for the click
            
        Returns:
            Annotated screenshot as bytes
        """
        annotation = ClickAnnotation(
            x=x,
            y=y,
            action_type=action_type,
            label=label or f"Click: ({x}, {y})"
        )
        return self.annotate_screenshot(screenshot_bytes, [annotation])


class HighlightedElement:
    """
    TODO - Implementation Instructions:
        1. Define __init__ with id, element_type, bounding_box, center, text, confidence
        2. Implement to_dict()
        3. Implement __repr__ for logging
    """
    pass


class VisualHighlighter:
    """
    TODO - Implementation Instructions:
        1. Define __init__(self, config):
            - Load YOLOv8 model (cache it)
            - Set confidence threshold from config
            - Initialize logger
        2. Implement detect_elements(screenshot: bytes) -> List[HighlightedElement]:
            - Convert bytes to image
            - Run YOLOv8 inference
            - Extract detections
            - Filter by confidence
            - Create HighlightedElement objects
            - Return list
        3. Implement generate_highlighted_image(screenshot: bytes, elements: List) -> bytes:
            - Load image from bytes
            - Draw bounding boxes for each element
            - Add labels/text
            - Return image as bytes
        4. Implement element type classification
            - Classify detected boxes as button, text_input, link, etc.
        5. Add OCR for text extraction from elements (optional)
    """
    pass


def load_yolov8_model(model_name: str = "yolov8n"):
    """
    TODO - Implementation Instructions:
        1. Load YOLOv8 model using ultralytics
        2. Return loaded model
        3. Consider model caching
    """
    pass


# YOLOv8 Element Types
ELEMENT_TYPES = [
    "button",
    "text_input",
    "link",
    "checkbox",
    "radio",
    "image",
    "text",
    "icon",
    "dropdown"
]
