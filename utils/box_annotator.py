# Source: copied from OmniParser/util/box_annotator.py and OmniParser/util/utils.py
# No logic changes — only added draw_parsed_elements() as an entry point
# assembled from the drawing portion of get_som_labeled_img() in OmniParser/util/utils.py.

from typing import List, Optional, Union, Tuple

import cv2
import numpy as np
import torch
from PIL import Image
from supervision.detection.core import Detections
from supervision.draw.color import Color, ColorPalette
from torchvision.ops import box_convert


# ---------------------------------------------------------------------------
# Section 1: BoxAnnotator class and helpers
# Source: OmniParser/util/box_annotator.py
# ---------------------------------------------------------------------------

class BoxAnnotator:
    """
    A class for drawing bounding boxes on an image using detections provided.

    Attributes:
        color (Union[Color, ColorPalette]): The color to draw the bounding box,
            can be a single color or a color palette
        thickness (int): The thickness of the bounding box lines, default is 2
        text_color (Color): The color of the text on the bounding box, default is white
        text_scale (float): The scale of the text on the bounding box, default is 0.5
        text_thickness (int): The thickness of the text on the bounding box,
            default is 1
        text_padding (int): The padding around the text on the bounding box,
            default is 5

    """

    def __init__(
        self,
        color: Union[Color, ColorPalette] = ColorPalette.DEFAULT,
        thickness: int = 3, # 1 for seeclick 2 for mind2web and 3 for demo
        text_color: Color = Color.BLACK,
        text_scale: float = 0.5, # 0.8 for mobile/web, 0.3 for desktop # 0.4 for mind2web
        text_thickness: int = 2, #1, # 2 for demo
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
        image_size: Optional[Tuple[int, int]] = None,
    ) -> np.ndarray:
        """
        Draws bounding boxes on the frame using the detections provided.

        Args:
            scene (np.ndarray): The image on which the bounding boxes will be drawn
            detections (Detections): The detections for which the
                bounding boxes will be drawn
            labels (Optional[List[str]]): An optional list of labels
                corresponding to each detection. If `labels` are not provided,
                corresponding `class_id` will be used as label.
            skip_label (bool): Is set to `True`, skips bounding box label annotation.
        Returns:
            np.ndarray: The image with the bounding boxes drawn on it
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

            text_width, text_height = cv2.getTextSize(
                text=text,
                fontFace=font,
                fontScale=self.text_scale,
                thickness=self.text_thickness,
            )[0]

            text_x = x1 + self.text_padding
            text_y = y1 - self.text_padding

            text_background_x1 = x1
            text_background_y1 = y1 - 2 * self.text_padding - text_height

            text_background_x2 = x1 + 2 * self.text_padding + text_width
            text_background_y2 = y1

            cv2.rectangle(
                img=scene,
                pt1=(text_background_x1, text_background_y1),
                pt2=(text_background_x2, text_background_y2),
                color=color.as_bgr(),
                thickness=cv2.FILLED,
            )
            box_color = color.as_rgb()
            luminance = 0.299 * box_color[0] + 0.587 * box_color[1] + 0.114 * box_color[2]
            text_color = (0,0,0) if luminance > 160 else (255,255,255)
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
# Section 2: annotate() function
# Source: OmniParser/util/utils.py
# ---------------------------------------------------------------------------

def annotate(
    image_source: np.ndarray,
    boxes: torch.Tensor,
    logits: torch.Tensor,
    phrases: List[str],
    text_scale: float,
    text_padding=5,
    text_thickness=2,
    thickness=3,
) -> np.ndarray:
    """
    Annotates an image with bounding boxes and labels.

    Parameters:
    image_source (np.ndarray): The source image to be annotated.
    boxes (torch.Tensor): Bounding box coordinates in cxcywh format, normalized 0-1.
    logits (torch.Tensor): Confidence scores (unused for drawing, kept for API compatibility).
    phrases (List[str]): Labels for each bounding box.
    text_scale (float): Scale of the text. 0.8 for mobile/web, 0.3 for desktop, 0.4 for mind2web.

    Returns:
    Tuple[np.ndarray, dict]: Annotated image and label_coordinates dict.
    """
    h, w, _ = image_source.shape
    boxes = boxes * torch.Tensor([w, h, w, h])
    xyxy = box_convert(boxes=boxes, in_fmt="cxcywh", out_fmt="xyxy").numpy()
    xywh = box_convert(boxes=boxes, in_fmt="cxcywh", out_fmt="xywh").numpy()
    detections = Detections(xyxy=xyxy)

    labels = [f"{phrase}" for phrase in range(boxes.shape[0])]

    box_annotator = BoxAnnotator(
        text_scale=text_scale,
        text_padding=text_padding,
        text_thickness=text_thickness,
        thickness=thickness,
    )
    annotated_frame = image_source.copy()
    annotated_frame = box_annotator.annotate(
        scene=annotated_frame, detections=detections, labels=labels, image_size=(w, h)
    )

    label_coordinates = {f"{phrase}": v for phrase, v in zip(phrases, xywh)}
    return annotated_frame, label_coordinates


# ---------------------------------------------------------------------------
# Section 3: draw_parsed_elements() entry point
# Source: assembled from the drawing portion of get_som_labeled_img()
#         in OmniParser/util/utils.py
# ---------------------------------------------------------------------------

def draw_parsed_elements(
    image_path: str,
    parsed_content_list: list,
    output_path: str,
    draw_bbox_config: dict = None,
) -> None:
    """
    Draw bounding boxes on an image given OmniParser parsed_content_list.

    Args:
        image_path: Path to the source image file.
        parsed_content_list: List of dicts from OmniParser parse(), each with:
            {
                "type": "text" | "icon",
                "bbox": [x1_ratio, y1_ratio, x2_ratio, y2_ratio],  # normalized 0-1
                "interactivity": bool,
                "content": str,
                "source": str,
            }
        output_path: Path to save the annotated image.
        draw_bbox_config: Optional dict with keys:
            text_scale, text_padding, text_thickness, thickness.
            Defaults to OmniParser desktop defaults if None.
    """
    elements = _extract_parsed_content_list(parsed_content_list)
    if not elements:
        raise ValueError("No parsed elements to draw")

    image = Image.open(image_path).convert("RGB")
    w, h = image.size
    image_np = np.asarray(image)

    filtered_boxes = torch.tensor([box["bbox"] for box in elements], dtype=torch.float32)
    filtered_boxes = box_convert(boxes=filtered_boxes, in_fmt="xyxy", out_fmt="cxcywh")
    phrases = [_build_element_label(item, idx) for idx, item in enumerate(elements)]

    cfg = draw_bbox_config or {"text_scale": 0.4, "text_padding": 5}
    annotated_frame, _ = annotate(
        image_source=image_np,
        boxes=filtered_boxes,
        logits=None,
        phrases=phrases,
        **cfg,
    )

    Image.fromarray(annotated_frame).save(output_path)


def _extract_parsed_content_list(payload) -> list:
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
