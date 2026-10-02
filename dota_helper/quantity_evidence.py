"""Optional, cached comparison of one selected game's starting purchase logs.

No requests run during module import or preview. Call verify_selected in a
background worker with a dedicated OpenDota client. Raw comparisons never mutate
routes or explicit corrections. Compatible quantity evidence can supply a
separate, labelled starting-buy projection through recoverable_counts.
"""
from copy import deepcopy
from functools import lru_cache
import hashlib
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
QUANTITY_VERSION = 2


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


def _validated_result(identity, result):
    """Validate persisted and freshly returned evidence by the same rules."""
    if not isinstance(result, dict) or any(result.get(k) != v or type(result.get(k)) is not type(v)
                                            for k, v in identity.items()):
        return None
    if result.get('status') not in ('verified', 'conflict', 'unavailable'):
        return None
    checked_at = result.get('checked_at')
    if type(checked_at) not in (int, float) or not math.isfinite(checked_at):
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


def _saved(identity):
    result = _load(user_data_dir() / 'quantity-evidence.json').get(_key(identity))
    return _validated_result(identity, result)


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
    if result['status'] in ('verified', 'conflict') and result.get('quantity_version') != QUANTITY_VERSION:
        result = _hydrate_legacy(identity, result)
    return {**deepcopy(result), 'cached': True}


def _hydrate_legacy(identity, result):
    """Recount one old comparison from its raw provider cache, without a request."""
    cache_key = hashlib.sha256((f"matches/{identity['match_id']}" + '{}').encode()).hexdigest()
    path = user_data_dir() / 'cache' / f'{cache_key}.json'
    try:
        stat = path.stat()
        response = _raw_cached_match(path, stat.st_mtime_ns, stat.st_size)
        player, matched_by, error = _matching_player(response.get('data'), identity)
    except (OSError, ValueError, AttributeError):
        return result
    if error:
        return result
    from .starting_events import starting_event_counts
    counts = starting_event_counts(player.get('purchase_log'))
    if counts is None:
        return result
    recorded = result['recorded_counts']
    differences = {key: {'recorded': recorded.get(key, 0), 'opendota': counts.get(key, 0)}
                   for key in sorted(set(recorded) | set(counts))
                   if recorded.get(key, 0) != counts.get(key, 0)}
    return {**result, 'counts': counts, 'differences': differences,
            'status': 'conflict' if differences else 'verified', 'matched_by': matched_by,
            'quantity_version': QUANTITY_VERSION,
            'message': ('OpenDota records different starting quantities. Review both logs before applying.'
                        if differences else 'OpenDota agrees with the recorded starting purchases; inventory completeness is not guaranteed.')}


@lru_cache(maxsize=16)
def _raw_cached_match(path, modified_ns, size):
    # Repeated overlay renders should not reparse an unchanged match response.
    return json.loads(path.read_text(encoding='utf-8'))


def recoverable_counts(route, result=None):
    """Recover compatible quantities for one exact player without editing a route.

    STRATZ can collapse repeated starting buys while OpenDota can represent
    assembled starting items. Compare complete component multisets so a wand
    agrees with its stick, two branches and recipe. Different item kinds or
    fewer observed components require review instead of automatic replacement.
    """
    if route.demo or route.source != 'STRATZ':
        return None
    identity = _identity(route)
    if identity is None:
        return None
    result = get_saved(route) if result is None else _validated_result(identity, result)
    if result is None or result['status'] not in ('verified', 'conflict'):
        return None
    if result.get('quantity_version') != QUANTITY_VERSION:
        return None
    if result.get('source') != 'OpenDota':
        return None
    matched_by = result.get('matched_by')
    if matched_by not in ('account_id', 'player_slot') or identity[matched_by] is None:
        return None
    if not 0 <= time.time() - result['checked_at'] < SUCCESS_TTL:
        return None
    from .starting_items import recorded_counts
    recorded = recorded_counts(route)
    alternate = result['counts']
    if recorded != result['recorded_counts'] or not recorded:
        return None
    if any(key not in ITEMS or count > 30 for values in (recorded, alternate)
           for key, count in values.items()):
        return None
    from .item_recipes import assemble_counts, expanded_counts
    original_parts = expanded_counts(recorded)
    alternate_parts = expanded_counts(alternate)
    if (set(original_parts) != set(alternate_parts)
            or any(alternate_parts[key] < count for key, count in original_parts.items())):
        return None
    return dict(assemble_counts(alternate))


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
              'matched_by': '', 'checked_at': time.time(), 'cached': False,
              'quantity_version': QUANTITY_VERSION}
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
        if saved is not None and (saved['status'] == 'unavailable'
                                  or saved.get('quantity_version') == QUANTITY_VERSION):
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
                from .starting_events import starting_event_counts
                counts = starting_event_counts(log)
                if counts is None:
                    result.update(status='unavailable', message='OpenDota does not expose usable recorded starting purchases.')
                else:
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
