# Vision Module - Implementation Instructions

## Overview
The Vision module processes screenshots to understand the GUI state.
It includes both enhancement preprocessing and core GUI state compilation.

Features:
1. **Visual Highlighting**: YOLOv8-based UI element detection
2. **Masking**: Gaussian/Norm-based masking of irrelevant components
3. **Cropping/Zoom**: Optional region-based cropping
4. **GUI State Compilation**: Complete visual + semantic context

## Architecture

```
Screenshot
    ↓
Visual Highlighting (YOLOv8 or Set-of-Mask)
    ↓
Masking (Gaussian/Norm Distribution)
    ↓
Cropping (Optional, candidate regions from MLLM)
    ↓
GUI State Compiler
    ↓
Structured GUI State (elements, masks, crops, language context)
```

## Components

### 1. gui_state_compiler.py
Orchestrates complete GUI state compilation.

**Key Responsibilities:**
- Accept screenshot
- Apply enabled vision enhancements
- Extract detected elements
- Compile language context
- Return complete GUI state

**TODO - Implementation:**
- [ ] Define GUIState dataclass
- [ ] Implement GUIStateCompiler class
- [ ] Implement compile_gui_state(screenshot, config) method
- [ ] Integrate visual_highlighting module
- [ ] Integrate masking module
- [ ] Integrate cropping module (optional)
- [ ] Add element detection and formatting
- [ ] Add caching for identical screenshots

### 2. visual_highlighting.py
Detects and highlights GUI elements using YOLOv8.

**Key Responsibilities:**
- Load YOLOv8 model
- Detect clickable/interactive elements
- Generate highlighting visualization
- Return bounding boxes and confidence scores

Reference: https://arxiv.org/abs/2412.10342

**TODO - Implementation:**
- [ ] Define HighlightedElement dataclass
- [ ] Implement VisualHighlighter class
- [ ] Implement detect_elements(screenshot) -> List[HighlightedElement]
- [ ] Load YOLOv8 model
- [ ] Filter detections by confidence threshold
- [ ] Generate visualization image with highlights
- [ ] Add model caching

### 3. masking.py
Masks irrelevant components based on Gaussian/Norm distribution.

**Key Responsibilities:**
- Identify sensitive/irrelevant regions
- Apply Gaussian or Norm-based masking
- Generate masked screenshot
- Return mask metadata

Reference: https://arxiv.org/abs/2507.03730

**TODO - Implementation:**
- [ ] Define MaskRegion dataclass
- [ ] Implement Masker class
- [ ] Implement apply_masks(image, regions) -> masked_image
- [ ] Implement gaussian_mask(region) method
- [ ] Implement norm_mask(region) method
- [ ] Add region detection logic
- [ ] Return mask metadata

### 4. cropping.py (Optional)
Crops and zooms into candidate regions.

**Key Responsibilities:**
- Accept candidate regions from MLLM
- Crop and enhance regions
- Return cropped screenshots
- Track crop context

Reference: https://arxiv.org/abs/2505.00684

**TODO - Implementation:**
- [ ] Define CroppedRegion dataclass
- [ ] Implement Cropper class
- [ ] Implement crop_regions(image, regions) -> List[cropped_images]
- [ ] Implement zoom_level calculation
- [ ] Add context tracking for crop coordinates

## Data Structures

### GUIState
```python
{
    "screenshot": bytes,
    "detected_elements": List[HighlightedElement],
    "highlighted_image": bytes,
    "masks": List[MaskRegion],
    "masked_image": Optional[bytes],
    "crops": Optional[List[CroppedRegion]],
    "language_context": {
        "active_subgoal": str,
        "past_subgoals": List[str],
        "detected_text": str,
        "available_elements": List[str]
    },
    "metadata": {
        "timestamp": str,
        "image_hash": str
    }
}
```

### HighlightedElement
```python
{
    "id": str,
    "element_type": str,  # button, text_input, link, checkbox, etc.
    "bounding_box": (x1, y1, x2, y2),
    "center": (x, y),
    "text": Optional[str],
    "confidence": float
}
```

## Integration Points

- **Configuration**: Reads vision_enhancement, enable_highlighting, enable_masking, enable_cropping
- **Execution**: Used by SubGoalExecutor to get current GUI state
- **Grounder**: Provides visual context for action decision
- **MLLM**: May provide candidate regions for cropping
