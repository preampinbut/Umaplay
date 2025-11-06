#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fetches UMA MUSUME skill data from the specified Gametora JSON URL,
extracts ID and English name, and saves the filtered list to a JSON file.
"""

import argparse
import json
import requests
import sys
from typing import Any, Dict, List, Optional

# --------------------------------- Utils ------------------------------------
def dbg(on: bool, *args, **kwargs):
    """Prints debug messages to stderr if debug is enabled."""
    if on:
        print(*args, file=sys.stderr, **kwargs)

# ---------------------------------- Main ------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Scrape and parse skills.")
    ap.add_argument("--url", type=str, required=True, help="Url find by going to https://gametora.com/umamusume/skills open Inspector->Network select XHR file 'skills.*.json' right click->Copy Value->Copy Url (e.g., https://gametora.com/data/umamusume/skills.81413efc.json)")
    ap.add_argument("--out", default="skills.json", help="Output JSON file (array of support card objects)")
    ap.add_argument("--debug", action="store_true", help="Enable verbose debug prints to stderr")
    args = ap.parse_args()

    # 1. Fetch the JSON data from the URL
    url = args.url
    dbg(args.debug, f"[DEBUG] Attempting to fetch URL: {url}")
    
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
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
    
    # 3. Process and filter the data
    filtered_skills: List[Dict[str, Any]] = []
    
    for skill in raw_skills_data:
        skill_id = skill.get("id")
        name_en = skill.get("name_en")
        
        # Ensure required fields exist and are valid
        if skill_id is not None and name_en:
            filtered_skills.append({
                "id": skill_id,
                "name_en": name_en
            })

    dbg(args.debug, f"[DEBUG] Filtered down to {len(filtered_skills)} skills with 'id' and 'name_en'.")

    # 4. Save the filtered data to the output JSON file
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(filtered_skills, f, ensure_ascii=False, indent=2)

        print(f"[OK] Wrote {len(filtered_skills)} skill entries → {args.out}")
    except IOError as e:
        print(f"[ERROR] Failed to write to file {args.out}: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()