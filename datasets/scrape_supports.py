#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Scrape UMA MUSUME Event Data from Gametora for multiple support cards,
parse the embedded Next.js JSON, score options, and output a single file.
"""

import argparse
import json
import re 
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
import requests
import sys
import os 
import shutil 

# --- Scoring Weights (kept from original script) ---
W_ENERGY   = 100.0
W_STAT     = 10.0
W_SKILLPTS = 2.0
W_HINT     = 1.0
W_BOND     = 0.3
W_MOOD     = 2.0

STAT_WEIGHTS = {
    "speed": 5.0,
    "stamina": 4.0,
    "power": 3.0,
    "wit": 2.0,
    "guts": 1.0,
}

BASE_URL = "https://gametora.com"
SUPPORT_BASE_URL = BASE_URL + "/umamusume/supports/"

# --------------------------------- Utils ------------------------------------
def dbg(on: bool, *args, **kwargs):
    if on:
        print(*args, file=sys.stderr, **kwargs)

def load_skill_data(file_path: str, debug: bool) -> Dict[str, str]:
    """Loads the skills JSON file into a dictionary for quick lookup (ID -> name_en)."""
    skill_map: Dict[str, str] = {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for skill in data:
                # Assuming the 'id' is a number and 'name_en' is a string
                skill_id = str(skill.get("id"))
                skill_name = skill.get("name_en")
                if skill_id and skill_name:
                    skill_map[skill_id] = skill_name
        dbg(debug, f"[DEBUG] Loaded {len(skill_map)} skills from {file_path}.")
    except FileNotFoundError:
        print(f"[WARN] Skill file not found at: {file_path}. Skill IDs will not be translated.", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to decode skill JSON file {file_path}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"[ERROR] An unexpected error occurred loading skill data: {e}", file=sys.stderr)
        
    return skill_map

# -------------------------- Parsing Helpers ---------------------------------

def parse_effects_from_event_dict(event_dict: Dict[str, Any], skill_map: Dict[str, str]) -> Dict[str, Any]:
    """
    Parses the effects dictionary ('r' list) from the raw JSON structure
    into a flat dictionary of stats/effects, translating skill IDs to names.
    """
    eff: Dict[str, Any] = {}
    for item in event_dict.get('r', []):
        type_code = item.get('t')
        value_raw = item.get('v')
        
        try:
            # Safely handle value, stripping potential '+' sign
            value = int(str(value_raw).strip('+'))
        except (ValueError, TypeError):
            continue
        
        if type_code == 'en':
            eff['energy'] = eff.get('energy', 0) + value
        elif type_code == 'sp':
            eff['speed'] = eff.get('speed', 0) + value
        elif type_code == 'st':
            eff['stamina'] = eff.get('stamina', 0) + value
        elif type_code == 'po':
            eff['power'] = eff.get('power', 0) + value
        elif type_code == 'gu':
            eff['guts'] = eff.get('guts', 0) + value
        elif type_code == 'in':
            eff['wit'] = eff.get('wit', 0) + value
        elif type_code == 'pt':
            eff['skill_pts'] = eff.get('skill_pts', 0) + value
        elif type_code == 'bo':
            eff['bond'] = eff.get('bond', 0) + value
        elif type_code == 'sk': # Skill: translate ID to name
            skill_id = str(item.get('d', ''))
            # **TRANSLATE SKILL ID HERE**
            skill_name = skill_map.get(skill_id, f"Skill ID: {skill_id}")
            eff.setdefault('hints', []).append(skill_name)
            
    return {k: v for k, v in eff.items() if v not in (None, 0, [])}


def score_outcome(eff: Dict[str, Any]) -> float:
    """Calculate a score for an event outcome based on weighted stats."""
    energy = float(eff.get("energy", 0))
    stats_sum = 0.0
    for stat, weight in STAT_WEIGHTS.items():
        stats_sum += weight * float(eff.get(stat, 0))
    spts   = float(eff.get("skill_pts", 0))
    hints  = len(eff.get("hints", []))
    bond   = float(eff.get("bond", 0))
    mood   = float(eff.get("mood", 0)) 
    
    return (W_ENERGY*energy + W_STAT*stats_sum + W_SKILLPTS*spts +
            W_HINT*hints + W_BOND*bond + W_MOOD*mood)

def choose_default_preference(options: Dict[str, List[Dict[str, Any]]]) -> int:
    """Choose the best option using WORST-CASE scoring for each option."""
    best_key = 1
    best_score = float("-inf")
    for k, outs in options.items():
        if not outs:
            continue
        # Use minimum score (worst case) for this option
        worst_case = min(score_outcome(o) for o in outs)
        
        # Tie-breaker for same score: prefer lower option number (1 > 2 > 3)
        current_key = int(k) if str(k).isdigit() else 1
        if worst_case > best_score or (worst_case == best_score and current_key < best_key):
            best_score = worst_case
            best_key = current_key
    return best_key

# ------------------------------ Event Parsing -------------------------------

def parse_events_from_json_data(event_data: Dict[str, Any], debug: bool, skill_map: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Parses event data from the 'eventData' dictionary in the Next.js JSON.
    """
    out: List[Dict[str, Any]] = []

    # Prefer 'en' (English) data for titles/names, fall back to 'ja' if 'en' is missing
    lang = 'en'
    if lang not in event_data:
        lang = 'ja'
        
    try:
        events_struct = json.loads(event_data.get(lang, '{}'))
    except json.JSONDecodeError:
        dbg(debug, f"[ERROR] Could not decode '{lang}' event data JSON string.")
        return out

    # 1. Random Events
    for random_event in events_struct.get('random', []):
        title = random_event.get('n', 'Unknown Random Event')
        options: Dict[str, List[Dict[str, Any]]] = {}
        
        for idx, choice in enumerate(random_event.get('c', []), 1):
            option_key = str(idx)
            # PASS skill_map HERE
            outcome_effects = parse_effects_from_event_dict(choice, skill_map)
            options[option_key] = [outcome_effects]
        
        if options:
            default_pref = choose_default_preference(options)
            out.append({
                "type": "random",
                "chain_step": 1,
                "name": title,
                "options": options,
                "default_preference": default_pref
            })
            dbg(debug, f" [INFO] Parsed random event: {title!r}")


    # 2. Chain Events (Arrows) - often "After a Race" or "Continuous" events
    chain_step = 1
    for chain_event in events_struct.get('arrows', []):
        title = chain_event.get('n', 'Unknown Chain Event')
        options: Dict[str, List[Dict[str, Any]]] = {}
        
        for idx, choice in enumerate(chain_event.get('c', []), 1):
            option_key = str(idx)
            # PASS skill_map HERE
            outcome_effects = parse_effects_from_event_dict(choice, skill_map)
            options[option_key] = [outcome_effects]

        if options:
            default_pref = choose_default_preference(options)
            out.append({
                "type": "chain",
                "chain_step": chain_step,
                "name": title,
                "options": options,
                "default_preference": default_pref
            })
            dbg(debug, f" [INFO] Parsed chain event: {title!r} (step {chain_step})")
        
        chain_step += 1
        
    return out

# ---------------------------------- Main ------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Scrape and parse Umamusume support card event data.")
    ap.add_argument("--skills", type=str, default="skills.json", help="Skills JSON file (id -> name_en lookup).")
    ap.add_argument("--supports-card", type=str, required=True, help="Comma-separated list of support card URL names (e.g., 30062-silence-suzuka,30063-taiki-shooting)")
    ap.add_argument("--out", default="supports_events.json", help="Output JSON file (array of support card objects)")
    ap.add_argument("--img-dir", default="images", help="Directory to save downloaded card images")
    ap.add_argument("--debug", action="store_true", help="Enable verbose debug prints to stderr")
    args = ap.parse_args()

    # **LOAD SKILL DATA HERE**
    skill_lookup = load_skill_data(args.skills, args.debug)

    supported_cards = [card.strip() for card in args.supports_card.split(",") if card.strip()]
    if not supported_cards:
        print("[ERROR] No support cards specified.", file=sys.stderr)
        return

    all_supports: List[Dict[str, Any]] = []

    img_dir_path = args.img_dir
    
    # Clear existing content in the image directory
    if os.path.exists(img_dir_path):
        print(f"[INFO] Clearing existing content in {img_dir_path}...")
        for item in os.listdir(img_dir_path):
            item_path = os.path.join(img_dir_path, item)
            try:
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    os.unlink(item_path)  # Delete files and symlinks
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)  # Delete subdirectories
            except Exception as e:
                print(f"[WARN] Failed to delete {item_path}. Reason: {e}", file=sys.stderr)

    # Create image directory if it doesn't exist
    if not os.path.exists(args.img_dir):
        os.makedirs(args.img_dir)

    # Mapping of raw type/attribute values to desired acronyms
    ATTRIBUTE_MAP = {
        "speed": "SPD",
        "stamina": "STA",
        "power": "PWR",
        "guts": "GUTS",
        "intelligence": "WIT",
        "friend": "PAL",
    }

    # Regex pattern for the image class prefix
    IMG_CLASS_PATTERN = re.compile(r"^supports_infobox_top_image__")


    for card_slug in supported_cards:
        url = SUPPORT_BASE_URL + card_slug
        dbg(args.debug, f"[DEBUG] Fetching URL: {url}")
        
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"[WARN] Failed to fetch {card_slug}: {e}", file=sys.stderr)
            continue
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # --- JSON DATA EXTRACTION ---
        
        next_data_tag = soup.find(id="__NEXT_DATA__")

        if not next_data_tag:
            print(f"[WARN] Could not find __NEXT_DATA__ tag for {card_slug}.", file=sys.stderr)
            continue
        
        try:
            json_content = next_data_tag.decode_contents()
            data = json.loads(json_content)
            
            page_props = data['props']['pageProps']
            item_data = page_props['itemData']
            event_data = page_props['eventData']
            
            # Extract basic card metadata
            name = item_data.get("char_name", "Unknown")
            rarity_code = item_data.get("rarity")
            rarity = "SSR" if rarity_code == 3 else f"Rarity_{rarity_code}"
            
            # Get the raw type (e.g., 'speed', 'friend') and convert it using the map
            raw_attribute = item_data.get("type", "unknown").lower()
            attribute = ATTRIBUTE_MAP.get(raw_attribute, raw_attribute.upper())
            
            # **1. Calculate formatted_id**
            formatted_id = f"{name}_{attribute}_{rarity}".replace(" ", "_")
            
            dbg(args.debug, f"[DEBUG] Successfully extracted JSON for: {name}")

        except (json.JSONDecodeError, KeyError) as e:
            print(f"[ERROR] Failed to parse JSON or access keys for {card_slug}: {e}", file=sys.stderr)
            continue
        
        # --- JSON DATA EXTRACTION END ---
        
        
        # --- IMAGE FIND & DOWNLOAD LOGIC START ---
        
        image_tag = soup.find("img", class_=IMG_CLASS_PATTERN)
        image_url = None
        filename = None
        
        if image_tag and image_tag.get('src'):
            raw_src = image_tag['src']
            
            # Use safe concatenation (casting to str and handling leading slash)
            cleaned_src = str(raw_src).lstrip('/')
            image_url = BASE_URL + '/' + cleaned_src

            dbg(args.debug, f"[DEBUG] Found image URL: {image_url}")
            
            # 2. Construct the file path and name using the formatted_id
            ext = os.path.splitext(image_url.split('?')[0])[-1]
            
            # **2. Use formatted_id as the base filename**
            filename = formatted_id + ext 
            save_path = os.path.join(args.img_dir, filename)
            
            # 3. Download the image
            try:
                img_response = requests.get(image_url, timeout=10)
                img_response.raise_for_status()
                
                with open(save_path, 'wb') as f:
                    f.write(img_response.content)
                print(f"[INFO] Downloaded image to: {save_path}")
                
            except requests.exceptions.RequestException as e:
                print(f"[WARN] Failed to download image for {card_slug} from {image_url}: {e}", file=sys.stderr)
        
        # --- IMAGE FIND & DOWNLOAD LOGIC END ---
        
        # Process events - **PASS SKILL LOOKUP DICTIONARY**
        events = parse_events_from_json_data(event_data, args.debug, skill_lookup)

        support_obj = {
            "type": "support",
            "name": name,
            "rarity": rarity,
            "attribute": attribute, 
            "id": formatted_id,
            "choice_events": events
        }
        all_supports.append(support_obj)
        print(f"[INFO] Parsed support card: {name} ({len(events)} events)")

    # --- Final Output ---
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(all_supports, f, ensure_ascii=False, indent=2)

    print(f"[OK] Wrote {len(all_supports)} support card entries → {args.out}")

if __name__ == "__main__":
    main()