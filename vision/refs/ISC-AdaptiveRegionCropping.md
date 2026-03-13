# Information Sensitive Cropping-Adaptive Region Extraction

This document explains how to implement the **Adaptive Region Extraction** algorithm used in Information-Sensitive Cropping (ISC). The goal is to extract **regions with high visual information density** from an edge-detection matrix.

## Reference
**Research Paper**: [Iris: Breaking GUI Complexity with Adaptive Focus and Self-Refining](https://arxiv.org/pdf/2412.10342)

---

# 1. Overview

The algorithm scans an **edge detection matrix** using **multi-scale sliding windows**.
At each scale:

* A window slides across the image.
* Edge density inside the window is calculated.
* If density exceeds a threshold, the region is extracted.
* The region is marked as processed to avoid overlaps.
* Window size increases gradually.

The algorithm stops when:

* The window size exceeds the image dimension, or
* The maximum number of regions is reached.

---

# 2. Inputs

| Variable  | Type                | Description                                                          |
| --------- | ------------------- | -------------------------------------------------------------------- |
| `M`       | 2D matrix `(H × W)` | Binary edge matrix where `1` indicates meaningful visual information |
| `k_min`   | integer             | Initial sliding window size                                          |
| `rho_min` | float               | Base density threshold                                               |
| `alpha`   | float               | Window expansion factor                                              |
| `N_max`   | integer             | Maximum number of regions to extract                                 |

---

# 3. Output

The algorithm returns a **set of extracted regions**:

```
Ω = [
  (x, y, k, id, density),
  ...
]
```

Each region contains:

| Field     | Description                    |
| --------- | ------------------------------ |
| `x`       | top-left x-coordinate          |
| `y`       | top-left y-coordinate          |
| `k`       | window size                    |
| `id`      | unique region ID               |
| `density` | edge density inside the region |

---

# 4. Key Concepts

### Edge Density

For a window of size `k × k`:

```
density = sum(M[y:y+k, x:x+k]) / k²
```

This measures the **amount of edge information in the window**.

---

### Scale-Adaptive Threshold

The density threshold changes depending on window size:

```
rho_k = rho_min / (k / k_min)^2
```

This prevents **larger windows from dominating selection**.

---

### Sliding Step Size

The sliding step is defined as:

```
step = max(k / 4, 32)
```

This balances **coverage vs computational efficiency**.

---

# 5. Step-by-Step Implementation

## Step 1 — Initialize Variables

Initialize the algorithm state.

```
k = k_min
Ω = empty list
```

---

## Step 2 — Start Multi-Scale Loop

Continue scanning while:

```
k ≤ max(height, width)
AND
len(Ω) < N_max
```

---

## Step 3 — Determine Sliding Step

Compute the sliding window stride.

```
step = max(k / 4, 32)
```

Convert to integer if necessary.

---

## Step 4 — Compute Density Threshold

Adjust threshold based on window size.

```
rho_k = rho_min / (k / k_min)^2
```

---

## Step 5 — Slide Window Across Image

Iterate across coordinates:

```
for y in range(0, height, step):
    for x in range(0, width, step):
```

---

## Step 6 — Check Window Boundaries

Skip windows that exceed image size.

```
if x + k > width:
    continue

if y + k > height:
    continue
```

---

## Step 7 — Compute Edge Density

Extract window from edge matrix:

```
window = M[y : y+k, x : x+k]
```

Compute density:

```
density = sum(window) / (k * k)
```

---

## Step 8 — Check Density Threshold

If density is high enough:

```
if density >= rho_k:
```

Then the region is considered information-rich.

---

## Step 9 — Store Extracted Region

Create a region entry:

```
id = len(Ω) + 1
region = (x, y, k, id, density)
```

Add to result set:

```
Ω.append(region)
```

---

## Step 10 — Prevent Overlapping Regions

Set the selected region in the edge matrix to zero:

```
M[y : y+k, x : x+k] = 0
```

This ensures the region will **not be selected again**.

---

## Step 11 — Expand Window Size

After scanning the entire image at the current scale:

```
k = ceil(alpha * k)
```

This increases the window size for the next iteration.

---

## Step 12 — Sort Regions by Density

After finishing the extraction process:

```
sort Ω by density (descending)
```

This prioritizes regions with the most information.

---

## Step 13 — Return Results

Return the extracted region list:

```
return Ω
```

---

# 6. Example Workflow

### Input

```
Edge matrix size: 1024 × 1024
k_min = 64
rho_min = 0.15
alpha = 1.5
N_max = 50
```

---

### Extraction Process

Iteration example:

| Iteration | Window Size |
| --------- | ----------- |
| 1         | 64          |
| 2         | 96          |
| 3         | 144         |
| 4         | 216         |

At each scale:

* Slide window
* Compute density
* Select regions
* Remove overlaps

---

# 7. Implementation Tips

### Speed Optimization

Use **integral images** for fast density computation.

Instead of summing each window:

```
density = integral_sum / k²
```

This reduces complexity from:

```
O(k²) → O(1)
```

---

### Data Structures

Recommended:

```
M → numpy array
Ω → list of dictionaries
```

Example region structure:

```
{
  "x": x,
  "y": y,
  "size": k,
  "id": id,
  "density": density
}
```

---

# 8. Complexity

Worst-case complexity:

```
O(S * (H/step) * (W/step))
```

Where:

* `S` = number of scales
* `H,W` = image dimensions

---