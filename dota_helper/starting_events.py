"""Quantities encoded in OpenDota's synthetic pregame purchase events."""
from collections import Counter
import math

from .catalog import ITEMS


# Only consumables whose charges represent stack quantity belong here. Wand,
# stick and raindrop charges count uses, not additional purchased items.
STACK_UNITS = {
    'tango': 3,
    'flask': 1, 'clarity': 1, 'enchanted_mango': 1, 'faerie_fire': 1,
    'ward_observer': 1, 'ward_sentry': 1, 'tpscroll': 1,
    'smoke_of_deceit': 1, 'dust': 1, 'blood_grenade': 1,
}


def purchase_count(event):
    """Return purchased units, or None when a pregame stack is ambiguous.

    OpenDota's initial inventory events may carry six Tango charges in one
    event. That means two purchased packs. A partial pack cannot establish a
    purchase quantity, and positive-time purchase events always count once.
    """
    second = event.get('time')
    key = event.get('key')
    if type(second) not in (int, float) or not math.isfinite(second) or not isinstance(key, str):
        return None
    if second >= 0 or key not in STACK_UNITS or 'charges' not in event:
        return 1
    charges = event['charges']
    unit = STACK_UNITS[key]
    if type(charges) is not int or charges <= 0 or charges % unit:
        return None
    count = charges // unit
    return count if count <= 30 else None


def starting_event_counts(events):
    """Count a validated OpenDota pregame log without guessing partial stacks."""
    if not isinstance(events, list) or not events:
        return None
    result = Counter()
    for event in events:
        if not isinstance(event, dict):
            return None
        count = purchase_count(event)
        if count is None:
            return None
        if event['time'] < 0:
            if event['key'] not in ITEMS:
                return None
            result[event['key']] += count
    return dict(result) if result else None
