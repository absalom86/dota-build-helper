"""Optional, cached comparison of one selected game's starting purchase logs.

No requests run during module import or preview. Call verify_selected in a
background worker with a dedicated OpenDota client. Results never mutate routes
or accepted starting quantities, even when the providers disagree.
"""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import json
import math
import re
import threading
import time
import uuid

from .catalog import ITEMS
from .paths import user_data_dir

_WRITE_LOCK = threading.Lock()
SUCCESS_TTL = 30 * 86400
RETRY_TTL = 15 * 60


def _integer(value, *, zero=False):
    if type(value) is int and (value >= 0 if zero else value > 0):
        return value
    return None


def _identity(route):
    matches = getattr(route, 'match_ids', [])
    match_id = _integer(matches[0]) if len(matches) == 1 else None
    hero_id = _integer(getattr(route, 'hero_id', None))
    account_id = _integer(getattr(route, 'account_id', None))
    player_slot = _integer(getattr(route, 'player_slot', None), zero=True)
    if player_slot not in (*range(5), *range(128, 133)):
        player_slot = None
    if not match_id or not hero_id or (account_id is None and player_slot is None):
        return None
    return {'match_id': match_id, 'hero_id': hero_id, 'account_id': account_id,
            'player_slot': player_slot}


def _key(identity):
    return ':'.join(str(identity[name]) for name in ('match_id', 'hero_id', 'account_id', 'player_slot'))


@lru_cache(maxsize=4)
def _load(path):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _saved(identity):
    result = _load(user_data_dir() / 'quantity-evidence.json').get(_key(identity))
    if not isinstance(result, dict) or any(result.get(k) != v for k, v in identity.items()):
        return None
    if result.get('status') not in ('verified', 'conflict', 'unavailable'):
        return None
    if not isinstance(result.get('checked_at'), (int, float)):
        return None
    recorded = result.get('recorded_counts')
    if not isinstance(recorded, dict) or any(not isinstance(k, str) or type(v) is not int or v <= 0
                                              for k, v in recorded.items()):
        return None
    if result.get('status') in ('verified', 'conflict'):
        counts = result.get('counts')
        if not isinstance(counts, dict) or not counts or any(not isinstance(k, str) or type(v) is not int or v <= 0
                                               for k, v in counts.items()):
            return None
        differences = {key: {'recorded': recorded.get(key, 0), 'opendota': counts.get(key, 0)}
                       for key in sorted(set(recorded) | set(counts))
                       if recorded.get(key, 0) != counts.get(key, 0)}
        if result.get('differences') != differences or (result['status'] == 'conflict') != bool(differences):
            return None
    return result


def get_saved(route):
    """Return a fresh comparison for this exact match/player and original log."""
    identity = _identity(route)
    if identity is None:
        return None
    result = _saved(identity)
    if result is None:
        return None
    ttl = SUCCESS_TTL if result['status'] in ('verified', 'conflict') else RETRY_TTL
    if not 0 <= time.time() - result['checked_at'] < ttl:
        return None
    from .starting_items import recorded_counts
    if result.get('recorded_counts') != recorded_counts(route):
        return None
    return {**deepcopy(result), 'cached': True}


def _save(result):
    path = user_data_dir() / 'quantity-evidence.json'
    with _WRITE_LOCK:
        data = dict(_load(path))
        data[_key(result)] = result
        # Bound this auxiliary cache independently of the saved-build history.
        if len(data) > 256:
            ordered = sorted(data, key=lambda k: data[k].get('checked_at', 0)
                             if isinstance(data[k], dict) else 0)
            data = {key: data[key] for key in ordered[-256:]}
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(f'.{uuid.uuid4().hex}.tmp')
        try:
            temp.write_text(json.dumps(data), encoding='utf-8')
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
        _load.cache_clear()


def _matching_player(match, identity):
    if not isinstance(match, dict) or match.get('match_id') != identity['match_id']:
        return None, '', 'The OpenDota response did not identify the selected match.'
    players = match.get('players')
    if not isinstance(players, list):
        return None, '', 'OpenDota has no player records for this match.'
    candidates = []
    for player in players:
        if not isinstance(player, dict) or player.get('hero_id') != identity['hero_id']:
            continue
        account = _integer(player.get('account_id'))
        slot = _integer(player.get('player_slot'), zero=True)
        # Known contradictions are rejected even when the other field agrees.
        if identity['account_id'] is not None and account is not None and account != identity['account_id']:
            continue
        if identity['player_slot'] is not None and slot is not None and slot != identity['player_slot']:
            continue
        account_matches = identity['account_id'] is not None and account == identity['account_id']
        slot_matches = identity['player_slot'] is not None and slot == identity['player_slot']
        if account_matches or slot_matches:
            candidates.append((player, 'account_id' if account_matches else 'player_slot'))
    if len(candidates) != 1:
        return None, '', 'Could not uniquely match this hero and player across the two sources.'
    return *candidates[0], ''


def verify_selected(route, client, cancel=None, force=False):
    """Compare one match via client.get; never request replay parsing or apply counts."""
    from .providers import DataError
    from .starting_items import correction, recorded_counts
    identity = _identity(route)
    result = {'status': 'skipped', 'message': '', 'counts': None,
              'recorded_counts': recorded_counts(route), 'differences': {}, 'source': 'OpenDota',
              'match_id': None, 'hero_id': route.hero_id, 'account_id': None, 'player_slot': None,
              'matched_by': '', 'checked_at': time.time(), 'cached': False}
    if route.demo or route.source != 'STRATZ':
        result['message'] = 'Secondary quantity verification is available for STRATZ match builds.'
        return result
    if correction(route) is not None:
        result['message'] = 'Saved starting quantities take priority; reset them before comparing source logs.'
        return result
    if identity is None:
        result['message'] = 'Refresh this lookup to retain the selected match and explicit player identity.'
        return result
    result.update(identity)
    if cancel is not None and cancel.is_set():
        return {**result, 'status': 'cancelled', 'message': 'Quantity verification cancelled.'}
    if not force:
        saved = get_saved(route)
        if saved is not None:
            return saved
    if cancel is not None:
        client.cancel = cancel
    try:
        match = client.get(f"matches/{identity['match_id']}", ttl=0 if force else SUCCESS_TTL)
    except (DataError, OSError, ValueError) as exc:
        # Do not include raw exception text: request URLs can contain API keys.
        http = re.search(r'\bOpenDota HTTP ([1-5][0-9]{2})\b', str(exc))
        reason = f'OpenDota HTTP {http[1]}' if http else 'OpenDota could not verify this match'
        result.update(status='unavailable', message=reason + '. Recorded quantities remain unchanged.')
    else:
        if cancel is not None and cancel.is_set():
            return {**result, 'status': 'cancelled', 'message': 'Quantity verification cancelled.'}
        player, matched_by, error = _matching_player(match, identity)
        if error:
            result.update(status='unavailable', message=error)
        else:
            log = player.get('purchase_log')
            if not isinstance(log, list) or not log:
                result.update(status='unavailable', message='OpenDota has no parsed purchase log for the matched player.')
            else:
                valid = all(isinstance(event, dict) and type(event.get('time')) in (int, float)
                            and math.isfinite(event['time']) and isinstance(event.get('key'), str)
                            for event in log)
                events = [event for event in log if event['time'] < 0] if valid else []
                if not events or any(event['key'] not in ITEMS for event in events):
                    result.update(status='unavailable', message='OpenDota does not expose usable recorded starting purchases.')
                else:
                    counts = dict(Counter(event['key'] for event in events))
                    recorded = result['recorded_counts']
                    differences = {key: {'recorded': recorded.get(key, 0), 'opendota': counts.get(key, 0)}
                                   for key in sorted(set(recorded) | set(counts))
                                   if recorded.get(key, 0) != counts.get(key, 0)}
                    result.update(status='conflict' if differences else 'verified', counts=counts,
                                  differences=differences, matched_by=matched_by,
                                  message=('OpenDota records different starting quantities. Review both logs before applying.'
                                           if differences else 'OpenDota agrees with the recorded starting purchases; inventory completeness is not guaranteed.'))
                    if getattr(client, 'stale', []):
                        result['message'] += ' Using cached OpenDota data.'
    if cancel is not None and cancel.is_set():
        return {**result, 'status': 'cancelled', 'message': 'Quantity verification cancelled.'}
    result['checked_at'] = time.time()
    try:
        _save(result)
    except OSError:
        result['message'] += ' Comparison could not be cached locally.'
    return result
