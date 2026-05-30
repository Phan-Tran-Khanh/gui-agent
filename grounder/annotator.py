"""
Bounding box annotation for grounded screenshots.

Migrated from utils/box_annotator.py (OmniParser/util/box_annotator.py +
OmniParser/util/utils.py). All original functionality is preserved.

Public API
----------
annotate(image, elements)
    PIL-based annotation for the grounder pipeline.
    Takes a PIL.Image and a list of ParsedElement objects.

draw_parsed_elements(image_path, parsed_content_list, output_path, draw_bbox_config)
    File-path-based annotation compatible with the original utils/box_annotator.py
    interface. Used by the web backend's sequential executor.

BoxAnnotator
    Low-level class for drawing bounding boxes on numpy arrays.
"""
# pylint: disable=no-member  # cv2 and torch are C extensions; pylint cannot introspect their members

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
import torch
from PIL import Image
from supervision.detection.core import Detections
from supervision.draw.color import Color, ColorPalette
from torchvision.ops import box_convert

from grounder.models import ParsedElement

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Section 1: BoxAnnotator class
# Source: OmniParser/util/box_annotator.py
# ---------------------------------------------------------------------------

class BoxAnnotator:
    """
    Draws bounding boxes on a frame using Supervision Detections.

    Attributes:
        color (Union[Color, ColorPalette]): Box colour or colour palette.
        thickness (int): Box line thickness.
        text_color (Color): Label text colour.
        text_scale (float): Label text scale.
        text_thickness (int): Label text stroke thickness.
        text_padding (int): Padding around label text.
    """

    def __init__(
        self,
        color: Union[Color, ColorPalette] = ColorPalette.DEFAULT,
        thickness: int = 3,
        text_color: Color = Color.BLACK,
        text_scale: float = 0.5,
        text_thickness: int = 2,
        text_padding: int = 10,
    ):
        self.color: Union[Color, ColorPalette] = color
        self.thickness: int = thickness
        self.text_color: Color = text_color
        self.text_scale: float = text_scale
        self.text_thickness: int = text_thickness
        self.text_padding: int = text_padding

    def annotate(
        self,
        scene: np.ndarray,
        detections: Detections,
        labels: Optional[List[str]] = None,
        skip_label: bool = False,
        image_size: Optional[Tuple[int, int]] = None,  # pylint: disable=unused-argument
    ) -> np.ndarray:
        """
        Draw bounding boxes on *scene* for every detection.

        Args:
            scene:      BGR numpy array to draw on.
            detections: Supervision Detections object (xyxy pixel coords).
            labels:     Optional label per detection; falls back to class_id.
            skip_label: When True, skip text drawing.
            image_size: Unused; kept for API compatibility.

        Returns:
            Annotated BGR numpy array (same object as *scene*).
        """
        font = cv2.FONT_HERSHEY_SIMPLEX
        for i in range(len(detections)):
            x1, y1, x2, y2 = detections.xyxy[i].astype(int)
            class_id = (
                detections.class_id[i] if detections.class_id is not None else None
            )
            idx = class_id if class_id is not None else i
            color = (
                self.color.by_idx(idx)
                if isinstance(self.color, ColorPalette)
                else self.color
            )

            cv2.rectangle(
                img=scene,
                pt1=(x1, y1),
                pt2=(x2, y2),
                color=color.as_bgr(),
                thickness=self.thickness,
            )

            if skip_label:
                continue

            text = (
                f"{class_id}"
                if (labels is None or len(detections) != len(labels))
                else labels[i]
            )

            (text_width, text_height), _ = cv2.getTextSize(
                text=text,
                fontFace=font,
                fontScale=self.text_scale,
                thickness=self.text_thickness,
            )

            text_x = x1 + self.text_padding
            text_y = y1 - self.text_padding
            bg_x2 = x1 + 2 * self.text_padding + text_width
            bg_y1 = y1 - 2 * self.text_padding - text_height

            cv2.rectangle(
                img=scene,
                pt1=(x1, bg_y1),
                pt2=(bg_x2, y1),
                color=color.as_bgr(),
                thickness=cv2.FILLED,
            )

            box_rgb = color.as_rgb()
            luminance = 0.299 * box_rgb[0] + 0.587 * box_rgb[1] + 0.114 * box_rgb[2]
            text_color = (0, 0, 0) if luminance > 160 else (255, 255, 255)

            cv2.putText(
                img=scene,
                text=text,
                org=(text_x, text_y),
                fontFace=font,
                fontScale=self.text_scale,
                color=text_color,
                thickness=self.text_thickness,
                lineType=cv2.LINE_AA,
            )

        return scene


# ---------------------------------------------------------------------------
# Section 2: _annotate_detections() — internal helper for draw_parsed_elements
# Source: annotate() in OmniParser/util/utils.py
# Renamed to avoid collision with the PIL-based annotate() below.
# ---------------------------------------------------------------------------

def _annotate_detections(
    image_source: np.ndarray,
    boxes: torch.Tensor,
    phrases: List[str],
    text_scale: float,
    text_padding: int = 5,
    text_thickness: int = 2,
    thickness: int = 3,
) -> np.ndarray:
    """
    Annotate *image_source* with bounding boxes and element-index labels.

    Args:
        image_source: RGB numpy array.
        boxes:        Bounding boxes in cxcywh format, normalised 0-1.
        phrases:      Label per box.
        text_scale:   Font scale (0.8 mobile/web, 0.3 desktop, 0.4 mind2web).
        text_padding, text_thickness, thickness: Drawing parameters.

    Returns:
        Annotated RGB numpy array.
    """
    h, w, _ = image_source.shape
    boxes = boxes * torch.Tensor([w, h, w, h])
    xyxy = box_convert(boxes=boxes, in_fmt="cxcywh", out_fmt="xyxy").numpy()
    xywh = box_convert(boxes=boxes, in_fmt="cxcywh", out_fmt="xywh").numpy()
    detections = Detections(xyxy=xyxy)

    labels = [str(phrase) for phrase in range(boxes.shape[0])]

    box_annotator = BoxAnnotator(
        text_scale=text_scale,
        text_padding=text_padding,
        text_thickness=text_thickness,
        thickness=thickness,
    )
    annotated_frame = image_source.copy()
    annotated_frame = box_annotator.annotate(
        scene=annotated_frame,
        detections=detections,
        labels=labels,
        image_size=(w, h),
    )

    label_coordinates = {str(phrase): v for phrase, v in zip(phrases, xywh)}
    del label_coordinates  # result unused; kept for parity with original signature
    return annotated_frame


# ---------------------------------------------------------------------------
# Section 3: draw_parsed_elements() — public file-path-based entry point
# Source: OmniParser/util/utils.py (get_som_labeled_img drawing portion)
# ---------------------------------------------------------------------------

def draw_parsed_elements(
    image_path: str,
    parsed_content_list: list,
    output_path: str,
    draw_bbox_config: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Draw bounding boxes on an image given an OmniParser parsed_content_list.

    Args:
        image_path:          Path to the source image.
        parsed_content_list: List of element dicts from OmniParser, each with::

                                 {
                                     "type": "text" | "icon",
                                     "bbox": [x1, y1, x2, y2],  # normalised 0-1
                                     "interactivity": bool,
                                     "content": str,
                                     "source": str,
                                 }

        output_path:     Path to save the annotated image.
        draw_bbox_config: Optional drawing config with keys
                          text_scale, text_padding, text_thickness, thickness.
    """
    elements = _extract_parsed_content_list(parsed_content_list)
    if not elements:
        raise ValueError("No parsed elements to draw")

    image = Image.open(image_path).convert("RGB")
    image_np = np.asarray(image)

    filtered_boxes = torch.tensor(
        [box["bbox"] for box in elements], dtype=torch.float32
    )
    filtered_boxes = box_convert(
        boxes=filtered_boxes, in_fmt="xyxy", out_fmt="cxcywh"
    )
    phrases = [_build_element_label(item, idx) for idx, item in enumerate(elements)]

    cfg = draw_bbox_config or {"text_scale": 0.4, "text_padding": 5}
    annotated_frame = _annotate_detections(
        image_source=image_np,
        boxes=filtered_boxes,
        phrases=phrases,
        **cfg,
    )

    Image.fromarray(annotated_frame).save(output_path)


def _extract_parsed_content_list(payload: Any) -> list:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise TypeError("parsed payload must be a list or dict")
    if isinstance(payload.get("parsed_screen"), list):
        return payload["parsed_screen"]
    if isinstance(payload.get("parsed_content_list"), list):
        return payload["parsed_content_list"]
    raise ValueError("Could not find parsed list in payload")


def _build_element_label(item: dict, fallback_index: int) -> str:
    element_index = item.get("element_index")
    if isinstance(element_index, int):
        return str(element_index)
    return str(fallback_index)


# ---------------------------------------------------------------------------
# Section 4: annotate() — PIL-based grounder pipeline annotation
# ---------------------------------------------------------------------------

# BGR colours — green for text elements, blue-orange for icons
_COLOR_TEXT = (34, 197, 94)
_COLOR_ICON = (255, 120, 0)

_FONT = cv2.FONT_HERSHEY_SIMPLEX
_FONT_SCALE = 0.45
_FONT_THICKNESS = 1
_BOX_THICKNESS = 2
_LABEL_PAD = 3


def annotate(image: Image.Image, elements: List[ParsedElement]) -> Image.Image:
    """
    Draw numbered bounding boxes on interactable UI elements.

    Used by the grounder pipeline. Each element receives:
    - A coloured rectangle (green = text, blue-orange = icon)
    - A filled ID badge in the top-left corner

    Args:
        image:    Source PIL Image (converted to RGB internally).
        elements: Interactable elements from OmniParser with
                  idx, bbox (normalised xyxy), and type.

    Returns:
        New PIL Image with annotations. Input image is not modified.
    """
    if not elements:
        return image.copy()

    img = np.array(image.convert("RGB"))
    h, w = img.shape[:2]

    for elem in elements:
        x1, y1, x2, y2 = elem.bbox
        px1 = max(0, int(x1 * w))
        py1 = max(0, int(y1 * h))
        px2 = min(w - 1, int(x2 * w))
        py2 = min(h - 1, int(y2 * h))

        if px2 <= px1 or py2 <= py1:
            _logger.debug("Skipping degenerate bbox for element %d", elem.idx)
            continue

        color = _COLOR_TEXT if elem.type == "text" else _COLOR_ICON

        cv2.rectangle(img, (px1, py1), (px2, py2), color, _BOX_THICKNESS)

        label = str(elem.idx)
        (lw, lh), _ = cv2.getTextSize(label, _FONT, _FONT_SCALE, _FONT_THICKNESS)
        badge_x2 = px1 + lw + 2 * _LABEL_PAD
        badge_y1 = max(0, py1 - lh - 2 * _LABEL_PAD)
        cv2.rectangle(img, (px1, badge_y1), (badge_x2, py1), color, cv2.FILLED)
        cv2.putText(
            img, label,
            (px1 + _LABEL_PAD, py1 - _LABEL_PAD),
            _FONT, _FONT_SCALE, (255, 255, 255), _FONT_THICKNESS, cv2.LINE_AA,
        )

    return Image.fromarray(img)
