"""Resolve captured match MMR to already-parsed OpenDota builds by exact ID."""
from collections import Counter
from copy import deepcopy
import threading
import time

from .builds import normalize
from .catalog import HEROES, PATCHES
from .fast_lookup import DeadlineJobs
from .live_ratings import MAX_AGE, SOURCE, _match_id, _timestamp
from .providers import DataError, OpenDota
from .ratings import numeric_mmr, rank_tier
from .ranking import ranked
from .recency import RECENT_DAYS, in_recent_window


MAX_WORKERS = 2


def opendota_rated_routes(cache_dir, hero, role, candidates, progress, cancel,
                         deadline, on_update=None):
    """Keep every verified game available before the shared absolute deadline.

    Only GET existing match responses. Missing parsed histories are skipped; this
    fallback never submits parsing jobs or infers purchases from final inventory.
    """
    if type(hero) is not int or str(hero) not in HEROES or type(role) is not int or role not in range(1, 6):
        raise DataError('Choose a valid hero and position.')
    cancel = cancel or threading.Event()
    if cancel.is_set():
        raise DataError('Search cancelled')
    jobs = DeadlineJobs(cancel)
    jobs.deadline = min(jobs.deadline, deadline)
    now = time.time()
    records = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        mid = _match_id(candidate.get('match_id'))
        observed = _timestamp(candidate.get('observed_at'))
        try:
            mmr = numeric_mmr(candidate.get('average_mmr'))
        except OverflowError:
            mmr = None
        if (mid and mmr is not None and mmr > 0 and observed is not None
                and now - MAX_AGE <= observed <= now + 300):
            mid = int(mid)
            if mid not in records or observed >= records[mid]['observed_at']:
                records[mid] = {'average_mmr': mmr, 'observed_at': observed}
    pending = sorted(records, key=lambda mid: (records[mid]['average_mmr'],
                                              records[mid]['observed_at']), reverse=True)
    client = OpenDota(cache_dir)
    client.cancel = cancel
    routes, skipped, failures = [], Counter(), []
    checked = 0
    rate_limited = False

    def collect(mid, match):
        if not isinstance(match, dict) or _match_id(match.get('match_id')) != str(mid):
            skipped['match unavailable or mismatched'] += 1
            return
        start = _timestamp(match.get('start_time'))
        duration = _timestamp(match.get('duration'))
        if (type(match.get('radiant_win')) is not bool or start is None
                or duration is None or duration <= 0 or start + duration > now):
            skipped['still live or completion unavailable'] += 1
            return
        if not in_recent_window(start, now):
            skipped[f'outside {RECENT_DAYS}-day window'] += 1
            return
        if match.get('leagueid') or type(match.get('lobby_type')) is not int or match['lobby_type'] != 7:
            skipped['not a ranked pub'] += 1
            return
        players = match.get('players')
        if not isinstance(players, list):
            skipped['players unavailable'] += 1
            return
        players = [player for player in players if isinstance(player, dict)]
        try:
            average_rank = rank_tier(match.get('avg_rank_tier'), average=True)
        except OverflowError:
            average_rank = None
        if average_rank is not None and average_rank < 80:
            skipped['conflicting below-Immortal match average'] += 1
            return
        for player in players:
            profile = _timestamp(player.get('rank_tier'))
            if profile is not None and 0 < profile < 80:
                skipped['conflicting below-Immortal profile'] += 1
                return
        all_immortal = (len(players) == 10
                        and all(type(player.get('player_slot')) is int for player in players)
                        and {player.get('player_slot') for player in players} == {*range(5), *range(128, 133)}
                        and all(type(player.get('rank_tier')) in (int, float)
                                and player['rank_tier'] == 80 for player in players))
        if records[mid]['average_mmr'] < 7000 and average_rank != 80 and not all_immortal:
            skipped['Immortal rank unverified'] += 1
            return
        matching = [player for player in players
                    if type(player.get('hero_id')) is int and player['hero_id'] == hero]
        if (len(matching) != 1 or type(matching[0].get('position_est')) is not int
                or matching[0]['position_est'] != role):
            skipped['different or unknown hero/position'] += 1
            return
        player = dict(matching[0])
        slot = player.get('player_slot')
        if type(slot) is not int or slot not in (*range(5), *range(128, 133)):
            skipped['player slot unavailable'] += 1
            return
        log = player.get('purchase_log')
        abilities = player.get('ability_upgrades_arr')
        if not isinstance(log, list) or not isinstance(abilities, list):
            skipped['purchase or skill history unavailable'] += 1
            return
        # Sanitize old cache entries before the common normalizer sorts them.
        clean_log = []
        for entry in log:
            if not isinstance(entry, dict) or not isinstance(entry.get('key'), str) or not entry['key']:
                continue
            second = entry.get('time')
            # Purchases before horn have negative times; _timestamp is nonnegative.
            if type(second) not in (int, float) or _timestamp(abs(second)) is None:
                continue
            clean_log.append(entry)
        player['purchase_log'] = clean_log
        player['ability_upgrades_arr'] = [ability for ability in abilities
                                         if type(ability) is int and ability > 0]
        if not clean_log or not player['ability_upgrades_arr']:
            skipped['purchase or skill history unavailable'] += 1
            return
        match = dict(match, match_id=mid, avg_mmr=records[mid]['average_mmr'],
                     avg_rank_tier=average_rank)
        if type(match.get('patch')) is not int:
            match['patch'] = 0
        evidence = (f"OpenDota ranked pub · match-average MMR {records[mid]['average_mmr']:,} "
                    f'· {SOURCE} · OpenDota estimated position {role}')
        try:
            route = normalize(match, player, evidence)
        except (TypeError, ValueError, KeyError, OverflowError):
            route = None
        if route is None or not route.skills:
            skipped['usable purchase or skill history unavailable'] += 1
            return
        route.average_mmr_source = SOURCE
        patch = next((item for item in PATCHES if item['id'] == route.patch), None) if route.patch else None
        route.patch_label = patch['name'] if patch else 'Patch unverified'
        if not patch:
            route.warnings.append('PATCH UNVERIFIED: OpenDota did not supply a known patch.')
        route.warnings.insert(0, 'Match-average MMR was captured from the OpenDota live feed for this exact game. Build history comes from OpenDota; position is estimated by OpenDota.')
        routes.append(route)
        if on_update:
            on_update((deepcopy(ranked(routes)), f'{len(routes)} OpenDota builds with captured MMR ready'))

    while not cancel.is_set() and time.monotonic() < jobs.deadline:
        while pending and jobs.active < MAX_WORKERS and not rate_limited:
            mid = pending[0]
            if not jobs.submit(mid, lambda mid=mid: client.get(f'matches/{mid}', ttl=300)):
                break
            pending.pop(0)
            progress(f'OpenDota · checking game {mid} with captured MMR for position {role}…')
        if not jobs.active:
            break
        event = jobs.next()
        if event is None:
            break
        mid, match, error = event
        checked += 1
        if error:
            message = str(error) if isinstance(error, DataError) else 'OpenDota response unavailable'
            failures.append(message)
            rate_limited = rate_limited or '429' in message
        else:
            collect(mid, match)
    if cancel.is_set():
        raise DataError('Search cancelled')
    for route in routes:
        route.warnings.extend(warning for warning in client.stale if warning not in route.warnings)
    status = f'OpenDota captured MMR fallback: {len(routes)} usable builds from {checked}/{len(records)} candidate games. '
    if skipped:
        status += '; '.join(f'{count} {reason}' for reason, count in skipped.items()) + '. '
    if failures:
        status += ' '.join(dict.fromkeys(failures)) + ' '
    if pending or jobs.active:
        status += 'Partial search: request or time budget reached; cached responses are reused next time. '
    return ranked(routes), status
