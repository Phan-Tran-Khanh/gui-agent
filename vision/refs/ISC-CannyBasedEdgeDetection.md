# Information Sensitive Cropping-Edge Detection (ISC)

## Overview

The goal of **Information Detection** is to produce a **binary information matrix** that highlights regions of meaningful GUI content.

Unlike a vanilla Canny edge detector, this pipeline introduces **two important modifications**:

1. **Adaptive Histogram Equalization (CLAHE)** to enhance subtle GUI elements.
2. **Edge Dilation** to preserve **information density and semantic grouping** of interface components.

The final output is a **binary matrix ( M )** where:

```
M[i,j] = 1  → pixel contains meaningful visual information
M[i,j] = 0  → background / non-informative region
```

This matrix is later used by **AdaptiveRegionExtraction** in the ISC cropping stage.

---

# Pipeline Overview

The algorithm contains **five stages**:

```
Input GUI Screenshot
        │
        ▼
1. Pre-processing
        │
        ▼
2. Noise Reduction
        │
        ▼
3. Gradient Computation
        │
        ▼
4. Edge Formation (Canny)
        │
        ▼
5. Edge Density Preservation (Dilation)
        │
        ▼
Binary Information Matrix M
```

---

# Inputs

| Parameter         | Type              | Description                      |
| ----------------- | ----------------- | -------------------------------- |
| `I`               | Image (H × W × 3) | Input GUI screenshot             |
| `clipLimit`       | float             | CLAHE contrast limit             |
| `tileGridSize`    | tuple             | CLAHE grid size                  |
| `sigma`           | float             | Gaussian smoothing parameter     |
| `T_low`           | float             | Low threshold for hysteresis     |
| `T_high`          | float             | High threshold for hysteresis    |
| `dilation_kernel` | matrix            | Structuring element for dilation |
| `dilation_iter`   | int               | Number of dilation iterations    |

---

# Output

| Variable | Type                  | Description                   |
| -------- | --------------------- | ----------------------------- |
| `M`      | Binary matrix (H × W) | Information indication matrix |

```
M ∈ {0,1}^{H×W}
```

---

# Step-by-Step Implementation

---

# Step 1 — Pre-processing

## Purpose

Enhance structural information in GUI screenshots.

GUI interfaces often contain **small icons, text, and thin separators**.
Adaptive histogram equalization helps reveal these subtle structures.

## Operations

1. Convert image to grayscale
2. Apply adaptive histogram equalization (CLAHE)

---

### Pseudocode

```
function PREPROCESS(I):

    # Convert to grayscale
    G ← convert_to_grayscale(I)

    # Apply adaptive histogram equalization
    G_enhanced ← CLAHE(
        image = G,
        clipLimit = clipLimit,
        tileGridSize = tileGridSize
    )

    return G_enhanced
```

---

# Step 2 — Noise Reduction

## Purpose

Reduce noise that could generate false edges.

Gaussian smoothing removes:

* compression artifacts
* texture noise
* minor pixel fluctuations

while preserving major boundaries.

---

### Pseudocode

```
function DENOISE(G):

    G_smooth ← GaussianBlur(
        image = G,
        sigma = sigma
    )

    return G_smooth
```

---

# Step 3 — Gradient Computation

## Purpose

Detect intensity changes that correspond to edges.

Gradients are computed in both **horizontal and vertical directions**.

---

## Gradient Equations

Horizontal gradient:

```
Gx = ∂I / ∂x
```

Vertical gradient:

```
Gy = ∂I / ∂y
```

Gradient magnitude:

```
|G| = sqrt(Gx² + Gy²)
```

Gradient direction:

```
θ = arctan(Gy / Gx)
```

---

### Pseudocode

```
function COMPUTE_GRADIENTS(G):

    Gx ← Sobel(G, direction = x)
    Gy ← Sobel(G, direction = y)

    magnitude ← sqrt(Gx² + Gy²)
    direction ← arctan2(Gy, Gx)

    return magnitude, direction
```

---

# Step 4 — Edge Formation (Canny Core)

This stage corresponds to the **core Canny algorithm**.

It converts gradient responses into **thin edges**.

---

## 4.1 Non-Maximum Suppression

Purpose:

Thin wide gradient responses into **1-pixel edges**.

Process:

* For each pixel
* Compare gradient magnitude with neighbors
* Keep only local maxima along gradient direction

---

### Pseudocode

```
function NON_MAX_SUPPRESSION(magnitude, direction):

    edges ← zero_matrix(size(magnitude))

    for each pixel (x,y):

        neighbors ← pixels along gradient direction

        if magnitude(x,y) is local maximum:
            edges(x,y) ← magnitude(x,y)

    return edges
```

---

## 4.2 Hysteresis Thresholding

Purpose:

Connect strong edges and discard weak noise edges.

Two thresholds are used:

```
T_high → strong edges
T_low  → weak edges
```

Rules:

* strong edges → always kept
* weak edges → kept if connected to strong edges
* others → removed

---

### Pseudocode

```
function HYSTERESIS(edges):

    strong_edges ← edges ≥ T_high
    weak_edges ← T_low ≤ edges < T_high

    for each weak edge pixel:

        if connected_to(strong_edges):
            keep pixel
        else:
            remove pixel

    return binary_edge_map
```

---

# Step 5 — Edge Density Preservation (Paper Modification)

This is **not part of standard Canny**.

The paper deliberately **dilates edges** to create **connected information regions**.

## Motivation

Without dilation:

```
icon edges → thin fragmented lines
```

With dilation:

```
icon edges → filled region approximating UI component
```

This better represents **information density**.

---

## Morphological Dilation

For each edge pixel:

* expand the edge region using a structuring element

Example kernel:

```
3 × 3 square
```

---

### Pseudocode

```
function PRESERVE_DENSITY(edge_map):

    M ← dilate(
        image = edge_map,
        kernel = dilation_kernel,
        iterations = dilation_iter
    )

    M ← convert_to_binary(M)

    return M
```

---

# Final Algorithm

---

### Complete Information Detection Pipeline

```
function INFORMATION_DETECTION(I):

    # Stage 1 — Pre-processing
    G ← PREPROCESS(I)

    # Stage 2 — Noise reduction
    G_smooth ← DENOISE(G)

    # Stage 3 — Gradient computation
    magnitude, direction ← COMPUTE_GRADIENTS(G_smooth)

    # Stage 4 — Canny edge formation
    thin_edges ← NON_MAX_SUPPRESSION(magnitude, direction)

    edge_map ← HYSTERESIS(thin_edges)

    # Stage 5 — Density preservation (paper modification)
    M ← PRESERVE_DENSITY(edge_map)

    return M
```

---

# Differences from Standard Canny

| Component               | Standard Canny | ISC Implementation |
| ----------------------- | -------------- | ------------------ |
| Histogram Equalization  | ❌ not used     | ✅ CLAHE applied    |
| Gaussian smoothing      | ✅              | ✅                  |
| Gradient computation    | ✅              | ✅                  |
| Non-maximum suppression | ✅              | ✅                  |
| Hysteresis thresholding | ✅              | ✅                  |
| Edge dilation           | ❌              | ✅ added            |

So the paper uses:

```
Modified Canny Edge Detector
```

---

# Practical Parameter Suggestions

Typical values for GUI screenshots:

```
CLAHE clipLimit = 2.0
CLAHE tileGridSize = (8,8)

Gaussian sigma = 1.0

T_low  = 50
T_high = 150

dilation kernel = 3×3
dilation iterations = 1 or 2
```

---

# Final Output Example

Binary matrix (M):

```
0 0 0 1 1 1 0
0 1 1 1 1 1 0
0 1 1 1 0 0 0
0 0 0 0 0 0 0
```

Where **1 represents visually meaningful interface regions**.

---

If you'd like, I can also show a **much clearer conceptual diagram of how ISC converts a GUI screenshot into adaptive crops**, because the **edge dilation step only makes sense when you see the full pipeline with AdaptiveRegionExtraction.**
