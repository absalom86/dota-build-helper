"""Fill unidentified upgrades only when the same player's full sequence agrees."""
from .catalog import ABILITY_IDS
from .quantity_evidence import _identity, _matching_player

UNKNOWN = {'0', 'dota_base_ability'}
RECOVERY_NOTE = 'Missing skill IDs recovered from the same OpenDota player/game; all identified upgrades agree.'


def unidentified(key):
    return key in UNKNOWN or str(key).isdecimal()


def needs_recovery(route):
    return (not route.demo and route.source == 'STRATZ' and
            any(unidentified(key) for key in route.skills) and _identity(route) is not None)


def recover_skills(route, client, cancel):
    if not needs_recovery(route) or cancel.is_set():
        return None
    identity = _identity(route)
    client.cancel = cancel
    match = client.get(f"matches/{identity['match_id']}", ttl=30 * 86400)
    if cancel.is_set():
        return None
    player, _, error = _matching_player(match, identity)
    if error:
        return None
    ids = player.get('ability_upgrades_arr')
    if not isinstance(ids, list) or len(ids) != len(route.skills):
        return None
    if any(type(value) is not int or value < 0 for value in ids):
        return None
    skills = [ABILITY_IDS.get(str(value), str(value)) for value in ids]
    if any(not unidentified(old) and not unidentified(new) and old != new
           for old, new in zip(route.skills, skills)):
        return None
    if not any(not unidentified(old) and old == new for old, new in zip(route.skills, skills)):
        return None
    # An unknown ID elsewhere must not discard talents that are recoverable.
    merged = [new if unidentified(old) and not unidentified(new) else old
              for old, new in zip(route.skills, skills)]
    return merged if merged != route.skills else None
