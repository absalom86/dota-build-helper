"""Six-slot examples require a recorded main inventory, not six purchase events."""
from .catalog import ITEMS, item_name

ITEM_KEYS = {int(v['id']): k for k, v in ITEMS.items() if v.get('id') is not None}
NON_SLOT_UPGRADES = {'ultimate_scepter_2', 'aghanims_shard', 'moon_shard'}


def inventory_keys(values):
    return [ITEM_KEYS.get(value, '') if type(value) is int else '' for value in values]


def finished_item(key):
    if not isinstance(key, str):
        return False
    item = ITEMS.get(key, {})
    return (bool(item) and not key.startswith('recipe_') and key not in NON_SLOT_UPGRADES
            and item.get('qual') not in ('consumable', 'component')
            and bool(item.get('created')) and (item.get('cost') or 0) >= 1000) or key in {'blink', 'ghost', 'gem'}


def six_slot_items(route):
    """Six main slots, each a substantial completed item; duplicates occupy slots."""
    slots = route.final_items
    return list(slots) if (not route.demo and isinstance(slots, list) and len(slots) == 6
                          and all(finished_item(k) for k in slots)) else []


def six_slot_text(route):
    return ' · '.join(item_name(k) for k in six_slot_items(route))


def endgame_examples(routes, hero, role, limit=3):
    """Independent observed finishes; never change the ranked build list.

    Slot order is not a different build. Keep the best source for each distinct
    six-item inventory, including duplicated items when actually recorded.
    """
    from .ranking import route_key
    unique = {r.id: r for r in routes if r.hero_id == hero and r.role == role and six_slot_items(r)}
    result, inventories = [], set()
    for route in sorted(unique.values(), key=route_key, reverse=True):
        items = six_slot_items(route)
        signature = tuple(sorted(items))
        if items and signature not in inventories:
            result.append(route)
            inventories.add(signature)
            if len(result) >= limit:
                break
    return result if limit > 0 else []
