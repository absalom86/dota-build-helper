"""Find completed builds for exact games with a captured match-average MMR."""
from collections import Counter
import threading
import time

from .fast_lookup import DeadlineJobs
from .live_ratings import MAX_AGE, SOURCE, _match_id, _timestamp
from .providers import DataError
from .ratings import numeric_mmr
from .ranking import ranked


BATCH_SIZE = 10


def rated_routes(client, hero, role, candidates, progress, cancel, deadline, on_update=None):
    from .stratz import SUMMARY, PLAYER, eligible, normalize_stratz, reference_query

    cancel = cancel or threading.Event()
    jobs = DeadlineJobs(cancel)
    deadline = min(jobs.deadline, deadline)
    # Leave time for the independent parsed-match source if STRATZ is missing
    # these recently observed games or is unavailable.
    jobs.deadline = time.monotonic() + max(0, deadline - time.monotonic()) / 2
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
        if mid and mmr is not None and mmr >= 7000 and observed is not None and now - MAX_AGE <= observed <= now + 300:
            records[int(mid)] = {'average_mmr': mmr, 'observed_at': observed}
    pending = sorted(records, key=lambda mid: (records[mid]['average_mmr'], records[mid]['observed_at']), reverse=True)
    routes, skipped, checked = [], Counter(), 0
    fallback = set()
    failure = ''
    while pending and not cancel.is_set() and time.monotonic() < jobs.deadline:
        ids, pending = pending[:BATCH_SIZE], pending[BATCH_SIZE:]
        fields = SUMMARY + ' didRadiantWin durationSeconds endDateTime players {' + PLAYER + '}'
        query = '{constants {gameVersions{id name}} ' + ' '.join(
            f'm{i}:match(id:{mid}){{{fields}}}' for i, mid in enumerate(ids)) + '}'
        progress(f'Checking {len(ids)} games with captured MMR for completed {hero} / position {role} builds…')
        try:
            data = client.bounded(jobs, query)
            versions = {v['id']: v['name'] for v in data.get('constants', {}).get('gameVersions', [])}
            selected = {}
            for i, mid in enumerate(ids):
                checked += 1
                match = data.get(f'm{i}')
                if not isinstance(match, dict) or match.get('id') != mid:
                    skipped['match unavailable'] += 1
                    fallback.add(mid)
                    continue
                if match.get('leagueId'):
                    skipped['tournament game'] += 1
                    continue
                end = _timestamp(match.get('endDateTime'))
                duration = _timestamp(match.get('durationSeconds'))
                if not end or end > time.time() or not duration or type(match.get('didRadiantWin')) is not bool:
                    skipped['still live or completion unavailable'] += 1
                    continue
                players = [p for p in match.get('players') or []
                           if eligible(match, p, hero, role, recent=False)]
                if len(players) != 1 or not _match_id(players[0].get('steamAccountId')):
                    skipped['different hero, position or rank'] += 1
                    continue
                selected[mid] = players[0]['steamAccountId']
            if not selected:
                continue
            detail_ids = list(selected)
            details = client.bounded(jobs, '{' + reference_query(detail_ids, details=True, accounts=selected) + '}')
            for i, mid in enumerate(detail_ids):
                match = details.get(f'm{i}')
                if (not isinstance(match, dict) or match.get('id') != mid
                        or match.get('leagueId')
                        or type(match.get('didRadiantWin')) is not bool):
                    skipped['match details unavailable'] += 1
                    if not match or match.get('id') == mid and not match.get('leagueId'):
                        fallback.add(mid)
                    continue
                players = [p for p in match.get('players') or []
                           if p.get('steamAccountId') == selected[mid] and eligible(match, p, hero, role, recent=False)]
                if len(players) != 1:
                    skipped['details mismatch'] += 1
                    continue
                route = normalize_stratz(match, players[0], versions)
                if route is None or not route.skills:
                    skipped['purchase or skill history unavailable'] += 1
                    fallback.add(mid)
                    continue
                route.average_mmr = records[mid]['average_mmr']
                route.average_mmr_source = SOURCE
                route.evidence = route.evidence.replace('numeric MMR unavailable',
                    f'match-average MMR {route.average_mmr:,} · {SOURCE}')
                route.warnings.insert(0, 'Match-average MMR was captured from the OpenDota live feed for this exact game. Build and position were independently verified with STRATZ.')
                routes.append(route)
            if routes and on_update:
                on_update((ranked(routes), f'{len(routes)} completed builds with captured MMR ready'))
        except DataError as exc:
            failure = str(exc)
            accepted = {route.match_ids[0] for route in routes}
            fallback.update(mid for mid in ids if mid not in accepted)
            break
    if cancel.is_set():
        raise DataError('Search cancelled')
    fallback.update(pending)
    fallback_status = ''
    if fallback and time.monotonic() < deadline:
        from .rated_opendota import opendota_rated_routes
        def publish_fallback(result):
            if on_update:
                on_update((ranked(routes + result[0]), result[1]))
        found, fallback_status = opendota_rated_routes(client.cache_dir, hero, role,
            [dict(match_id=mid, **records[mid]) for mid in fallback], progress, cancel, deadline,
            on_update=publish_fallback)
        routes = ranked(routes + found)
    status = f'Captured MMR discovery: {len(routes)} usable builds from {checked}/{len(records)} candidate games. '
    if skipped:
        status += '; '.join(f'{count} {reason}' for reason, count in skipped.items()) + '. '
    if failure:
        status += failure
    elif pending:
        status += 'Time budget reached; cached responses are reused next time.'
    if fallback_status:
        status += ' ' + fallback_status
    return ranked(routes), status
