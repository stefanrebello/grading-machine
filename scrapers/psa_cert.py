"""
scrapers/psa_cert.py
---------------------
Pulls card data + images from PSA's public API using a cert number.
Reads API token from config.json in the project root.

Usage:
    python scrapers/psa_cert.py --cert 12345678
    python scrapers/psa_cert.py --cert 12345678 --save

What it does:
    1. Calls PSA API with cert number
    2. Gets card details (player, year, set, grade)
    3. Downloads front + back images
    4. Runs vision pipeline on each image
    5. Stores measurements in grade_profiles.json
       (builds up over time to create grade comparison data)
"""

import os
import sys
import json
import requests
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── CONFIG ────────────────────────────────────────────────────
ROOT         = Path(__file__).parent.parent
CONFIG_FILE  = ROOT / "config.json"
IMAGES_DIR   = ROOT / "data" / "psa_images"
PROFILES_FILE = ROOT / "data" / "grade_profiles.json"
PSA_API_BASE = "https://api.psacard.com/publicapi"


def load_token():
    if not CONFIG_FILE.exists():
        raise FileNotFoundError("config.json not found — run setup first")
    with open(CONFIG_FILE) as f:
        config = json.load(f)
    token = config.get("psa_token", "").strip()
    if not token or token == "PASTE_YOUR_TOKEN_HERE":
        raise ValueError("PSA token not set in config.json")
    return token


# ══════════════════════════════════════════════════════════════
# PSA API CALLS
# ══════════════════════════════════════════════════════════════

def get_cert_data(cert_number: str, token: str) -> dict:
    """
    Pull card details from PSA API for a given cert number.
    Returns dict with grade, player, year, set, image URLs.
    """
    url = f"{PSA_API_BASE}/cert/GetByCertNumber/{cert_number}"
    headers = {
        "Authorization": f"bearer {token}",
        "Accept": "application/json"
    }

    response = requests.get(url, headers=headers, timeout=15)

    if response.status_code == 200:
        return response.json()
    elif response.status_code == 401:
        raise ValueError("Invalid PSA token — check config.json")
    elif response.status_code == 404:
        raise ValueError(f"Cert number {cert_number} not found in PSA database")
    else:
        raise ValueError(f"PSA API error: {response.status_code} — {response.text}")


def parse_cert_response(data: dict) -> dict:
    """
    Parse PSA API response into clean card details.
    PSA returns a PSACert object with card info.
    """
    cert = data.get("PSACert", {})

    return {
        "cert_number":   cert.get("CertNumber", ""),
        "grade":         cert.get("CardGrade", ""),
        "grade_number":  extract_grade_number(cert.get("CardGrade", "")),
        "player":        cert.get("Subject", ""),
        "year":          cert.get("Year", ""),
        "set_name":      cert.get("Brand", ""),
        "card_number":   cert.get("CardNumber", ""),
        "variety":       cert.get("Variety", ""),
        "front_image":   cert.get("frontImageURL", ""),
        "back_image":    cert.get("backImageURL", ""),
        "spec_id":       cert.get("SpecID", ""),
    }


def extract_grade_number(grade_str: str) -> float:
    """Extract numeric grade from PSA grade string like 'PSA 10' or 'PSA 9'."""
    if not grade_str:
        return 0.0
    parts = grade_str.strip().split()
    for part in reversed(parts):
        try:
            return float(part)
        except ValueError:
            continue
    return 0.0


def download_image(url: str, save_path: Path) -> bool:
    """Download an image from URL and save to disk."""
    if not url:
        return False
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(response.content)
            return True
    except Exception as e:
        print(f"   ⚠️  Image download failed: {e}")
    return False


# ══════════════════════════════════════════════════════════════
# GRADE PROFILE BUILDER
# Stores vision measurements per grade
# Builds up over time as we scan more certs
# ══════════════════════════════════════════════════════════════

def load_profiles() -> dict:
    """Load existing grade profiles from disk."""
    if PROFILES_FILE.exists():
        with open(PROFILES_FILE) as f:
            return json.load(f)
    return {str(g): [] for g in range(1, 11)}


def save_profiles(profiles: dict):
    """Save grade profiles to disk."""
    PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILES_FILE, "w") as f:
        json.dump(profiles, f, indent=2)


def add_to_profile(card: dict, front_scores: dict, back_scores: dict):
    """
    Add vision measurements for this cert to the grade profile.
    Over time this builds a statistical model per grade.
    """
    grade = str(int(card["grade_number"])) if card["grade_number"] else None
    if not grade or grade == "0":
        print("   ⚠️  Could not determine grade — skipping profile update")
        return

    profiles = load_profiles()

    entry = {
        "cert":         card["cert_number"],
        "player":       card["player"],
        "year":         card["year"],
        "set":          card["set_name"],
        "front":        front_scores,
        "back":         back_scores,
    }

    if grade not in profiles:
        profiles[grade] = []
    profiles[grade].append(entry)

    save_profiles(profiles)

    # Print running stats for this grade
    grade_data = profiles[grade]
    if len(grade_data) >= 2:
        print_grade_stats(grade, grade_data)


def print_grade_stats(grade: str, data: list):
    """Print current statistical profile for a grade."""
    import statistics

    cats = ["centering_score", "corner_score", "edge_score", "surface_score"]
    labels = ["Centering", "Corners", "Edges", "Surface"]

    print(f"\n   📊 PSA {grade} profile ({len(data)} cards):")
    for cat, label in zip(cats, labels):
        front_vals = [d["front"].get(cat, 0) for d in data if d.get("front")]
        if front_vals:
            avg = round(statistics.mean(front_vals), 2)
            mn  = round(min(front_vals), 2)
            mx  = round(max(front_vals), 2)
            print(f"      {label:12} avg={avg}  min={mn}  max={mx}")


# ══════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ══════════════════════════════════════════════════════════════

def process_cert(cert_number: str, save: bool = True) -> dict:
    """
    Full pipeline for one cert number:
    1. Pull from PSA API
    2. Download images
    3. Run vision analysis
    4. Store in grade profiles
    """
    print(f"\n{'─'*55}")
    print(f"🔍 Processing PSA cert: {cert_number}")

    token = load_token()

    # Step 1 — Get cert data
    print("   Fetching from PSA API...")
    raw_data = get_cert_data(cert_number, token)
    card     = parse_cert_response(raw_data)

    print(f"   ✅ {card['player']} — {card['year']} {card['set_name']} #{card['card_number']}")
    print(f"   Grade: {card['grade']}")

    # Step 2 — Download images
    front_path = IMAGES_DIR / f"{cert_number}-FRONT.jpg"
    back_path  = IMAGES_DIR / f"{cert_number}-BACK.jpg"

    front_ok = download_image(card["front_image"], front_path)
    back_ok  = download_image(card["back_image"],  back_path)

    if front_ok: print(f"   ✅ Front image saved")
    if back_ok:  print(f"   ✅ Back image saved")
    if not front_ok and not back_ok:
        print("   ⚠️  No images available for this cert")

    # Step 3 — Run vision pipeline
    front_scores = {}
    back_scores  = {}

    try:
        from vision.grader import grade_card

        if front_ok and front_path.exists():
            result = grade_card(str(front_path))
            front_scores = {
                "centering_score": result.centering_score,
                "corner_score":    result.corner_score,
                "edge_score":      result.edge_score,
                "surface_score":   result.surface_score,
                "estimated_grade": result.estimated_grade,
            }
            print(f"   📸 Front analyzed — our estimate: PSA {result.estimated_grade}")

        if back_ok and back_path.exists():
            result = grade_card(str(back_path))
            back_scores = {
                "centering_score": result.centering_score,
                "corner_score":    result.corner_score,
                "edge_score":      result.edge_score,
                "surface_score":   result.surface_score,
                "estimated_grade": result.estimated_grade,
            }
            print(f"   📸 Back analyzed  — our estimate: PSA {result.estimated_grade}")

    except Exception as e:
        print(f"   ⚠️  Vision analysis failed: {e}")

    # Step 4 — Store in grade profiles
    if save and (front_scores or back_scores):
        add_to_profile(card, front_scores, back_scores)
        print(f"   ✅ Added to PSA {int(card['grade_number'])} grade profile")

    return {
        "card":          card,
        "front_scores":  front_scores,
        "back_scores":   back_scores,
    }


def process_cert_list(cert_numbers: list, save: bool = True):
    """Process multiple cert numbers in sequence."""
    print(f"\n🃏 Processing {len(cert_numbers)} certs...")
    results = []
    for cert in cert_numbers:
        try:
            result = process_cert(cert.strip(), save=save)
            results.append(result)
        except Exception as e:
            print(f"   ❌ Failed: {cert} — {e}")
    print(f"\n✅ Done — {len(results)}/{len(cert_numbers)} processed")
    return results


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PSA cert scraper")
    parser.add_argument("--cert",  type=str, help="Single cert number")
    parser.add_argument("--file",  type=str, help="Text file with one cert per line")
    parser.add_argument("--save",  action="store_true", default=True, help="Save to grade profiles")
    parser.add_argument("--stats", action="store_true", help="Show current grade profile stats")
    args = parser.parse_args()

    if args.stats:
        profiles = load_profiles()
        print("\n📊 Current grade profiles:")
        for grade, data in sorted(profiles.items(), key=lambda x: int(x[0])):
            print(f"   PSA {grade}: {len(data)} cards")
        sys.exit(0)

    if args.cert:
        process_cert(args.cert, save=args.save)

    elif args.file:
        with open(args.file) as f:
            certs = [line.strip() for line in f if line.strip()]
        process_cert_list(certs, save=args.save)

    else:
        parser.print_help()
