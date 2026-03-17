* Use **luminance (Y from YUV)**
* Use **SSIM instead of raw difference**
* Still **localized around a point of interest (POI)**
* Return a **binary indicator (changed / not changed)**

---

# 1) Inputs

* `img_prev` → previous frame (f_{N-1})
* `img_curr` → current frame (f_N)
* `poi = (x, y)`
* `roi_size` (e.g. 64 or 128)
* `ssim_threshold` (e.g. 0.90–0.98 depending sensitivity)

---

# 2) Convert RGB → YUV and extract luminance (Y)

Unlike previous version, now strictly follow paper:

```python
import cv2
import numpy as np

def extract_luminance(img):
    yuv = cv2.cvtColor(img, cv2.COLOR_BGR2YUV)
    Y = yuv[:, :, 0].astype(np.float32)
    return Y
```

---

# 3) Extract ROI centered at POI

```python
def extract_roi(Y, x, y, size):
    h, w = Y.shape
    half = size // 2

    x1 = max(0, x - half)
    y1 = max(0, y - half)
    x2 = min(w, x + half)
    y2 = min(h, y + half)

    return Y[y1:y2, x1:x2]
```

---

# 4) (Optional but recommended) Normalize ROI

SSIM is sensitive to scale differences:

```python
def normalize(img):
    return (img - np.mean(img)) / (np.std(img) + 1e-6)
```

---

# 5) Compute SSIM on luminance ROI

This replaces raw Y-Diff with **perceptual similarity**:

### Concept

* SSIM ∈ [0, 1]
* 1 → identical
* lower → more different

### Implementation

```python
from skimage.metrics import structural_similarity as ssim

def compute_ssim(roi1, roi2):
    score, ssim_map = ssim(roi1, roi2, full=True)
    return score, ssim_map
```

---

# 6) Localized change emphasis (important)

Even inside ROI, changes might be small. Focus more near POI center.

### Weighted SSIM (recommended)

```python
def weighted_ssim_score(ssim_map):
    h, w = ssim_map.shape
    cx, cy = w // 2, h // 2

    Y, X = np.ogrid[:h, :w]
    dist = (X - cx)**2 + (Y - cy)**2

    weights = np.exp(-dist / (2 * (w/4)**2))
    
    score = np.sum(ssim_map * weights) / np.sum(weights)
    return score
```

---

# 7) Decision rule (key difference)

Since SSIM measures **similarity**, invert logic:

```python
def is_changed(ssim_score, threshold):
    return ssim_score < threshold
```

---

# 8) Full pipeline

```python
def ydiff_ssim_poi(img_prev, img_curr, poi, roi_size=64, threshold=0.95):
    x, y = poi

    Y_prev = extract_luminance(img_prev)
    Y_curr = extract_luminance(img_curr)

    roi_prev = extract_roi(Y_prev, x, y, roi_size)
    roi_curr = extract_roi(Y_curr, x, y, roi_size)

    # optional normalization
    roi_prev = normalize(roi_prev)
    roi_curr = normalize(roi_curr)

    score, ssim_map = compute_ssim(roi_prev, roi_curr)

    # optional weighted refinement
    weighted_score = weighted_ssim_score(ssim_map)

    changed = weighted_score < threshold

    return {
        "changed": bool(changed),
        "ssim": float(score),
        "weighted_ssim": float(weighted_score),
        "poi": (x, y)
    }
```

---

# 9) Threshold tuning (VERY IMPORTANT)

Typical values:

| Scenario             | Threshold |
| -------------------- | --------- |
| Static UI            | 0.95–0.98 |
| Slight animation     | 0.90–0.95 |
| Aggressive detection | 0.85–0.90 |

---

# 10) Interpretation

* `SSIM ≈ 1.0` → no change
* `SSIM ↓ slightly (0.95)` → minor UI update
* `SSIM ↓ significantly (<0.9)` → real UI transition

---

# 11) Why this matches the paper

Your revised pipeline now correctly follows:

* ✅ Uses **Y channel from YUV**
* ✅ Uses **SSIM instead of raw pixel diff**
* ✅ Captures **perceptual similarity (mean, variance, correlation)**
* ✅ Adapted from frame-level → **localized ROI around POI**

---

# 12) Practical integration for your ADB action system

Use output like:

```json
{
  "changed": true,
  "weighted_ssim": 0.82
}
```

### Recommended logic

* If `changed == False` → action likely failed → retry
* If `changed == True` → UI updated → proceed

---

# 13) Key improvement over original version

| Method           | Behavior               |
| ---------------- | ---------------------- |
| Raw Y-Diff       | pixel-level, noisy     |
| SSIM on Y (this) | perceptual, robust     |
| + ROI            | localized to action    |
| + weighting      | focuses exactly on POI |