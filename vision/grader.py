"""
vision/grader.py
-----------------
Card grading vision pipeline — Option A (Image Similarity).

Given a photo of a card, analyzes:
  1. Centering     — measures border ratios left/right and top/bottom
  2. Corners       — detects wear/rounding at all 4 corners
  3. Edges         — detects chips, nicks, roughness along all 4 edges
  4. Surface       — detects scratches, print lines, stains

Scores each category 1-10, combines into a final estimated grade
that matches PSA's grading scale.

Usage:
    from vision.grader import grade_card

    result = grade_card("path/to/card.jpg")
    print(result)
"""

import cv2
import numpy as np
from PIL import Image
from dataclasses import dataclass


# ══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ══════════════════════════════════════════════════════════════

@dataclass
class GradeResult:
    estimated_grade: float
    centering_score: float
    corner_score: float
    edge_score: float
    surface_score: float
    centering_lr: float   # left/right % off center
    centering_tb: float   # top/bottom % off center
    confidence: str       # HIGH / MEDIUM / LOW
    notes: list

    def display(self):
        print("\n" + "═" * 50)
        print("  🃏 CARD GRADE ESTIMATE")
        print("═" * 50)
        print(f"\n  Estimated Grade : PSA {self.estimated_grade}")
        print(f"  Confidence      : {self.confidence}")
        print(f"\n  Centering       : {self.centering_score}/10  (L/R: {self.centering_lr:.1f}%  T/B: {self.centering_tb:.1f}% off)")
        print(f"  Corners         : {self.corner_score}/10")
        print(f"  Edges           : {self.edge_score}/10")
        print(f"  Surface         : {self.surface_score}/10")
        if self.notes:
            print(f"\n  Notes:")
            for note in self.notes:
                print(f"    • {note}")
        print("\n" + "═" * 50)


# ══════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════

def grade_card(image_path: str) -> GradeResult:
    """
    Full grading pipeline. Pass in path to card image.
    Returns a GradeResult with scores and estimated PSA grade.
    """
    # Load image
    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        raise ValueError(f"Could not load image: {image_path}")

    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    gray    = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # Step 1 — Find and crop the card
    card_region = detect_card_region(img_bgr)

    # Step 2 — Analyze each grading category
    centering_score, lr_off, tb_off = analyze_centering(card_region)
    corner_score, corner_notes      = analyze_corners(card_region)
    edge_score, edge_notes          = analyze_edges(card_region)
    surface_score, surface_notes    = analyze_surface(card_region)

    # Step 3 — Calculate final grade
    estimated_grade = calculate_grade(centering_score, corner_score, edge_score, surface_score)

    # Step 4 — Confidence based on image clarity
    confidence = assess_confidence(card_region)

    notes = corner_notes + edge_notes + surface_notes

    return GradeResult(
        estimated_grade=estimated_grade,
        centering_score=centering_score,
        corner_score=corner_score,
        edge_score=edge_score,
        surface_score=surface_score,
        centering_lr=lr_off,
        centering_tb=tb_off,
        confidence=confidence,
        notes=notes
    )


# ══════════════════════════════════════════════════════════════
# STEP 1 — CARD DETECTION
# Finds the card in the image, crops and straightens it
# ══════════════════════════════════════════════════════════════

def detect_card_region(img):
    """
    Detect and crop the card from the image.
    Assumes card is the largest rectangular object in frame.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    # Find contours
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return img  # return full image if no contour found

    # Find largest rectangular contour (the card)
    best = None
    best_area = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 10000:  # ignore small noise
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) == 4 and area > best_area:
            best = approx
            best_area = area

    if best is None:
        return img

    # Crop to the card bounding box
    x, y, w, h = cv2.boundingRect(best)
    card = img[y:y+h, x:x+w]

    # Resize to standard size for consistent analysis
    card = cv2.resize(card, (500, 700))
    return card


# ══════════════════════════════════════════════════════════════
# STEP 2A — CENTERING ANALYSIS
# Measures border widths on all 4 sides
# PSA standard: 55/45 or better for PSA 10
# ══════════════════════════════════════════════════════════════

def analyze_centering(card):
    """
    Measure border widths on all 4 sides.
    Returns score 1-10 and % off center for L/R and T/B.
    """
    H, W = card.shape[:2]
    gray = cv2.cvtColor(card, cv2.COLOR_BGR2GRAY)

    # Find card content area by detecting the inner border
    # Using edge detection to find where card art starts
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

    # Scan from each edge to find where content starts
    left_border   = _find_border(thresh, direction="left")
    right_border  = _find_border(thresh, direction="right")
    top_border    = _find_border(thresh, direction="top")
    bottom_border = _find_border(thresh, direction="bottom")

    # Calculate centering ratios
    lr_ratio = left_border / (left_border + right_border) if (left_border + right_border) > 0 else 0.5
    tb_ratio = top_border  / (top_border + bottom_border) if (top_border + bottom_border) > 0 else 0.5

    # % off from perfect center (0.5)
    lr_off = abs(lr_ratio - 0.5) * 100
    tb_off = abs(tb_ratio - 0.5) * 100

    # PSA centering standards:
    # PSA 10: 55/45 or better  = ~9% off max
    # PSA 9:  60/40 or better  = ~17% off max
    # PSA 8:  65/35 or better  = ~23% off max
    # PSA 7:  70/30 or better  = ~29% off max
    worst_off = max(lr_off, tb_off)

    if worst_off <= 9:
        score = 10
    elif worst_off <= 14:
        score = 9
    elif worst_off <= 20:
        score = 8
    elif worst_off <= 26:
        score = 7
    elif worst_off <= 32:
        score = 6
    elif worst_off <= 38:
        score = 5
    else:
        score = max(1, 4 - int(worst_off / 10))

    return float(score), lr_off, tb_off


def _find_border(thresh, direction):
    """Find border width by scanning from an edge."""
    H, W = thresh.shape
    if direction == "left":
        for x in range(W):
            if thresh[:, x].max() > 0:
                return x
        return W // 2
    elif direction == "right":
        for x in range(W-1, -1, -1):
            if thresh[:, x].max() > 0:
                return W - x
        return W // 2
    elif direction == "top":
        for y in range(H):
            if thresh[y, :].max() > 0:
                return y
        return H // 2
    elif direction == "bottom":
        for y in range(H-1, -1, -1):
            if thresh[y, :].max() > 0:
                return H - y
        return H // 2


# ══════════════════════════════════════════════════════════════
# STEP 2B — CORNER ANALYSIS
# Checks all 4 corners for wear, rounding, fraying
# ══════════════════════════════════════════════════════════════

def analyze_corners(card):
    """
    Analyze all 4 corners for sharpness.
    Sharp corners = high score. Rounded/worn = lower score.
    """
    H, W = card.shape[:2]
    corner_size = 40  # pixel region to analyze per corner

    corners = {
        "top_left":     card[0:corner_size,    0:corner_size],
        "top_right":    card[0:corner_size,    W-corner_size:W],
        "bottom_left":  card[H-corner_size:H,  0:corner_size],
        "bottom_right": card[H-corner_size:H,  W-corner_size:W],
    }

    scores = []
    notes = []

    for name, region in corners.items():
        score = _score_corner(region)
        scores.append(score)
        if score < 7:
            notes.append(f"Corner wear detected: {name.replace('_', ' ')}")

    avg_score = np.mean(scores)
    worst_score = min(scores)

    # Weight worst corner more heavily (like PSA does)
    final_score = (avg_score * 0.4) + (worst_score * 0.6)

    return round(final_score, 1), notes


def _score_corner(region):
    """
    Score a corner region 1-10 based on sharpness.
    Uses edge density — sharp corners have strong, clean edges.
    """
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)

    # Edge density in the corner
    edge_density = np.count_nonzero(edges) / edges.size

    # Color variance — worn corners show mixed colors
    color_std = np.std(region)

    # Sharp corner: high edge density at the actual corner point
    H, W = gray.shape
    corner_point = gray[0:5, 0:5]  # tiny corner region
    corner_sharpness = np.std(corner_point)

    # Combine signals
    if edge_density > 0.15 and corner_sharpness > 30:
        return 10
    elif edge_density > 0.12:
        return 9
    elif edge_density > 0.09:
        return 8
    elif edge_density > 0.07:
        return 7
    elif edge_density > 0.05:
        return 6
    elif edge_density > 0.03:
        return 5
    else:
        return max(1, int(edge_density * 100))


# ══════════════════════════════════════════════════════════════
# STEP 2C — EDGE ANALYSIS
# Checks all 4 edges for chips, nicks, roughness
# ══════════════════════════════════════════════════════════════

def analyze_edges(card):
    """
    Analyze all 4 edges for damage.
    Looks for irregularities in the edge line.
    """
    H, W = card.shape[:2]
    edge_width = 8  # pixels to sample along each edge

    edges_regions = {
        "top":    card[0:edge_width, :],
        "bottom": card[H-edge_width:H, :],
        "left":   card[:, 0:edge_width],
        "right":  card[:, W-edge_width:W],
    }

    scores = []
    notes = []

    for name, region in edges_regions.items():
        score = _score_edge(region)
        scores.append(score)
        if score < 7:
            notes.append(f"Edge damage detected: {name} edge")

    avg_score = np.mean(scores)
    worst = min(scores)
    final_score = (avg_score * 0.5) + (worst * 0.5)

    return round(final_score, 1), notes


def _score_edge(region):
    """Score an edge strip for roughness/damage."""
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)

    # Measure variance along the edge — rough edges = high variance
    row_means = np.mean(gray, axis=1) if gray.shape[0] > gray.shape[1] else np.mean(gray, axis=0)
    variance = np.std(row_means)

    # Low variance = clean straight edge = high score
    if variance < 5:
        return 10
    elif variance < 10:
        return 9
    elif variance < 15:
        return 8
    elif variance < 22:
        return 7
    elif variance < 30:
        return 6
    elif variance < 40:
        return 5
    else:
        return max(1, int(10 - variance / 10))


# ══════════════════════════════════════════════════════════════
# STEP 2D — SURFACE ANALYSIS
# Detects scratches, print lines, stains, gloss loss
# ══════════════════════════════════════════════════════════════

def analyze_surface(card):
    """
    Analyze card surface for scratches, print defects, staining.
    """
    gray = cv2.cvtColor(card, cv2.COLOR_BGR2GRAY)
    notes = []

    # Detect scratches — long thin bright lines
    edges = cv2.Canny(gray, 30, 100)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=50,
                             minLineLength=50, maxLineGap=5)

    scratch_count = len(lines) if lines is not None else 0

    # Detect surface noise/grain (print defects)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    noise = cv2.absdiff(gray, blurred)
    noise_level = np.mean(noise)

    # Detect staining — unusual color blobs
    hsv = cv2.cvtColor(card, cv2.COLOR_BGR2HSV)
    saturation = hsv[:,:,1]
    stain_score = np.std(saturation)

    # Score based on findings
    if scratch_count > 20:
        notes.append(f"Heavy scratching detected ({scratch_count} lines)")
        surface_score = max(1, 6 - scratch_count // 10)
    elif scratch_count > 10:
        notes.append(f"Moderate scratching ({scratch_count} lines)")
        surface_score = 7
    elif scratch_count > 5:
        notes.append(f"Light scratching ({scratch_count} lines)")
        surface_score = 8
    else:
        surface_score = 10

    # Adjust for noise
    if noise_level > 15:
        surface_score = max(1, surface_score - 2)
        notes.append("Print defects or surface wear detected")
    elif noise_level > 10:
        surface_score = max(1, surface_score - 1)

    return float(surface_score), notes


# ══════════════════════════════════════════════════════════════
# STEP 3 — FINAL GRADE CALCULATION
# Combines all 4 scores into PSA grade estimate
# Weights match PSA's known emphasis on corners/centering
# ══════════════════════════════════════════════════════════════

def calculate_grade(centering, corners, edges, surface):
    """
    Combine category scores into final PSA grade estimate.
    PSA weighs corners and centering most heavily.
    """
    # Weights based on PSA grading emphasis
    weighted = (
        centering * 0.25 +   # 25% — centering
        corners   * 0.35 +   # 35% — corners (most important)
        edges     * 0.20 +   # 20% — edges
        surface   * 0.20     # 20% — surface
    )

    # The weakest category can drag the grade down
    # (PSA won't give PSA 10 if any one category is poor)
    min_score = min(centering, corners, edges, surface)
    if min_score < 7 and weighted > 8:
        weighted = min(weighted, min_score + 1.5)

    # Map to PSA grade scale (whole numbers 1-10)
    if weighted >= 9.5:
        grade = 10
    elif weighted >= 8.5:
        grade = 9
    elif weighted >= 7.5:
        grade = 8
    elif weighted >= 6.5:
        grade = 7
    elif weighted >= 5.5:
        grade = 6
    elif weighted >= 4.5:
        grade = 5
    elif weighted >= 3.5:
        grade = 4
    elif weighted >= 2.5:
        grade = 3
    elif weighted >= 1.5:
        grade = 2
    else:
        grade = 1

    return float(grade)


# ══════════════════════════════════════════════════════════════
# STEP 4 — CONFIDENCE ASSESSMENT
# ══════════════════════════════════════════════════════════════

def assess_confidence(card):
    """Assess how confident we are in the grade based on image quality."""
    gray = cv2.cvtColor(card, cv2.COLOR_BGR2GRAY)

    # Check focus/sharpness using Laplacian variance
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

    # Check brightness
    mean_brightness = np.mean(gray)

    if laplacian_var > 500 and 80 < mean_brightness < 200:
        return "HIGH"
    elif laplacian_var > 200:
        return "MEDIUM"
    else:
        return "LOW — retake photo (blurry or poor lighting)"


# ══════════════════════════════════════════════════════════════
# TEST RUN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import os
    test_dir = os.path.join(os.path.dirname(__file__), "test_images")

    test_cards = [
        ("test_psa10.jpg", "Expected: PSA 10"),
        ("test_psa9.jpg",  "Expected: PSA 9"),
        ("test_psa8.jpg",  "Expected: PSA 8"),
        ("test_psa6.jpg",  "Expected: PSA 6"),
    ]

    for filename, expected in test_cards:
        path = os.path.join(test_dir, filename)
        if os.path.exists(path):
            print(f"\n{'─'*50}")
            print(f"📸 Grading: {filename}  ({expected})")
            result = grade_card(path)
            result.display()
        else:
            print(f"⚠️  Not found: {path}")
