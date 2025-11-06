#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fetches UMA MUSUME skill data from the specified Gametora JSON URL,
extracts detailed skill info, and saves the formatted list to a JSON file.
"""

import argparse
import json
import requests
import sys
from typing import Any, Dict, List, Optional, Tuple

# Base URL for skill icon images (deduced from Gametora structure)
ICON_BASE_URL = "https://gametora.com/images/umamusume/skill_icons/"

# --- Rarity Mapping based on User Input ---
RARITY_MAP = {
    # Key: Rarity Code (1, 2, 3) or a custom status ('inherited')
    # Value: (Output Rarity String, Color Class)
    1: ("normal", "dnlGQR"), 
    2: ("gold", "geDDHx"), 
    3: ("unique", "bhlwbP"),
    "inherited": ("inherited", "dnlGQR"), 
}

# --------------------------------- Utils ------------------------------------
def dbg(on: bool, *args, **kwargs):
    """Prints debug messages to stderr if debug is enabled."""
    if on:
        print(*args, file=sys.stderr, **kwargs)

# -------------------------- Skill Deduction Helpers --------------------------

def get_skill_symbol(name: str) -> Optional[str]:
    """
    Extracts grade symbol (◎, ○) from the skill name.
    Returns None if no symbol is found.
    """
    if name.endswith("◎"):
        return "◎"
    elif name.endswith("○"):
        return "○"
    return None # Changed from "" to None


def deduce_skill_attributes(skill: Dict[str, Any]) -> Tuple[str, str, Optional[str]]:
    """
    Deduces the rarity string, color class, and grade symbol based on 
    available skill properties and the RARITY_MAP.
    """
    skill_id = skill.get("id", 0)
    name_en = skill.get("name_en", "")

    rarity_code = skill.get("rarity")
    
    # 1. Check for specific rarity codes (1, 2, 3)
    if rarity_code in RARITY_MAP:
        rarity_str, color_class = RARITY_MAP[rarity_code]
    # 2. Check for inherited status (ID range logic is a reliable guess)
    elif skill_id >= 900000:
        rarity_str, color_class = RARITY_MAP.get("inherited", ("unknown", "dnlGQR"))
    # 3. Fallback to normal (1) if no other clear status is found
    else:
        rarity_str, color_class = RARITY_MAP.get(1, ("normal", "dnlGQR"))
    
    # 4. Get Grade Symbol
    grade_symbol = get_skill_symbol(name_en)

    # Note: We return Optional[str] for grade_symbol now
    return rarity_str, color_class, grade_symbol

# ---------------------------------- Main ------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Scrape and parse skills.")
    ap.add_argument("--url", type=str, required=True, help="Url find by going to https://gametora.com/umamusume/skills open Inspector->Network select XHR file 'skills.*.json' right click->Copy Value->Copy Url (e.g., https://gametora.com/data/umamusume/skills.81413efc.json)")
    ap.add_argument("--out", default="in_game/skills.json", help="Output JSON file (array of detailed skill objects)")
    ap.add_argument("--debug", action="store_true", help="Enable verbose debug prints to stderr")
    args = ap.parse_args()

    # 1. Fetch the JSON data from the URL
    url = args.url
    dbg(args.debug, f"[DEBUG] Attempting to fetch URL: {url}")
    
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Failed to fetch URL {url}: {e}", file=sys.stderr)
        return

    # 2. Parse the JSON content
    try:
        raw_skills_data: List[Dict[str, Any]] = response.json()
        dbg(args.debug, f"[DEBUG] Successfully parsed JSON. Found {len(raw_skills_data)} skills.")
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to decode JSON content: {e}", file=sys.stderr)
        return
    
    # 3. Process and filter/format the data
    detailed_skills: List[Dict[str, Any]] = []
    
    for skill in raw_skills_data:
        skill_id = skill.get("id")
        name_en = skill.get("name_en")
        desc_en = skill.get("desc_en")
        icon_id = skill.get("iconid")

        if skill_id is None or not name_en or not desc_en or icon_id is None:
            dbg(args.debug, f"[DEBUG] Skipping skill with missing key data (ID: {skill_id}).")
            continue
        
        # Determine Rarity, Color Class, and Grade Symbol
        rarity, color_class, grade_symbol = deduce_skill_attributes(skill)
        
        # Format Icon Filename and URL
        icon_filename = f"utx_ico_skill_{icon_id}.png"
        icon_src = ICON_BASE_URL + icon_filename
        
        # Build the detailed output object
        detailed_skills.append({
            "id": skill_id,
            "icon_filename": icon_filename,
            "icon_src": icon_src,
            "name": name_en,
            "description": desc_en,
            "color_class": color_class,
            "rarity": rarity,
            "grade_symbol": grade_symbol # This will be "◎", "○", or None (which serializes to null)
        })

    dbg(args.debug, f"[DEBUG] Formatted {len(detailed_skills)} skills.")

    # 4. Save the formatted data to the output JSON file
    try:
        # json.dump naturally converts Python's None to JSON's null
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(detailed_skills, f, ensure_ascii=False, indent=2)

        print(f"[OK] Wrote {len(detailed_skills)} detailed skill entries → {args.out}")
    except IOError as e:
        print(f"[ERROR] Failed to write to file {args.out}: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()