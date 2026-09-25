import json
from pathlib import Path

DATA = Path(__file__).parent / "data"


def read(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8-sig"))


HEROES = read("heroes")
ITEMS = read("items")
ABILITIES = read("abilities")
ABILITY_IDS = read("ability_ids")
PATCHES = read("patch")
ROLES = {1: "Carry", 2: "Mid", 3: "Offlane", 4: "Soft support", 5: "Hard support"}
LANES = {0: "Any lane", 1: "Safe lane", 2: "Mid lane", 3: "Off lane", 4: "Jungle"}


def item_name(key):
    return ITEMS.get(key, {}).get("dname") or key.replace("_", " ").title()


def ability_name(key):
    key = ABILITY_IDS.get(str(key), str(key))
    return ABILITIES.get(key, {}).get("dname") or key.replace("_", " ").title()


def patch_name(patch):
    return next((p["name"] for p in PATCHES if p["id"] == patch), f"ID {patch}")


def clock_text(seconds):
    if seconds is None:
        return "--:--"
    value = abs(int(seconds))
    return f"{'−' if seconds < 0 else ''}{value // 60:02d}:{value % 60:02d}"
