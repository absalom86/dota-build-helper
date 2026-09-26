"""Observed live MMR seeds must resolve to completed builds for the exact hero/role."""
from copy import deepcopy
import re
import threading
import time

import pytest

from dota_helper.catalog import PATCHES
from dota_helper.live_ratings import MAX_AGE, SOURCE
from dota_helper.providers import DataError
from dota_helper.rated_builds import rated_routes
from dota_helper.stratz import Stratz
from test_stratz import match


NOW = int(time.time())


def completed(mid):
    game = match(mid)
    game.update(startDateTime=NOW - 3600, endDateTime=NOW - 60,
                durationSeconds=3540, actualRank=80, leagueId=0)
    return game


def candidate(mid, mmr=8500):
    return {'match_id': mid, 'average_mmr': mmr, 'observed_at': NOW - 120}


class FakeQueries:
    def __init__(self, summaries, details=None):
        self.summaries = summaries
        self.details = details if details is not None else summaries
        self.calls = []
        self.detail_calls = 0
        self.fail_detail_call = None

    def __call__(self, query, variables=None):
        is_detail = 'itemPurchases' in query
        aliases = re.findall(r'(m\d+):match\(id:(\d+)\)', query)
        self.calls.append((is_detail, [int(mid) for _, mid in aliases], query))
        assert aliases, 'Rated discovery should query exact match IDs'
        if is_detail:
            self.detail_calls += 1
            if self.detail_calls == self.fail_detail_call:
                raise DataError('STRATZ request limit reached; fixture cooldown')
        pool = self.details if is_detail else self.summaries
        response = {'constants': {'gameVersions': [{'id': 182, 'name': PATCHES[-1]['name']}]}}
        for alias, mid in aliases:
            game = deepcopy(pool.get(int(mid)))
            if game and not is_detail:
                for player in game.get('players', []):
                    player.pop('stats', None)
                    player.pop('abilities', None)
            response[alias] = game
        return response


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr('dota_helper.rated_opendota.opendota_rated_routes', lambda *args, **kw: ([], ''))
    monkeypatch.setattr('dota_helper.stratz.urlopen',
                        lambda *args, **kwargs: pytest.fail('Unexpected STRATZ network call'))
    monkeypatch.setattr('dota_helper.live_ratings.urlopen',
                        lambda *args, **kwargs: pytest.fail('Rated build lookup must not fetch the live feed'))
    monkeypatch.setattr('dota_helper.rated_builds.time.time', lambda: NOW)
    return Stratz(tmp_path, token='fixture-only')


def run(client, candidates, *, cancel=None, seconds=2, on_update=None):
    return rated_routes(client, 1, 1, candidates, lambda _: None,
                        cancel if cancel is not None else threading.Event(),
                        deadline=time.monotonic() + seconds, on_update=on_update)


def test_recorded_mmr_loads_exact_completed_games_with_stratz_build_provenance(client, monkeypatch):
    queries = FakeQueries({mid: completed(mid) for mid in (501, 502)})
    monkeypatch.setattr(client, 'query', queries)
    updates = []
    routes, status = run(client, [candidate(501, 8123), candidate(502, 9200)],
                         on_update=updates.append)
    assert [route.match_ids[0] for route in routes] == [502, 501]
    assert [route.average_mmr for route in routes] == [9200, 8123]
    assert all(route.average_mmr_source == SOURCE for route in routes)
    assert all(route.source == 'STRATZ' for route in routes)
    assert all(route.hero_id == 1 and route.role == 1 for route in routes)
    assert all([(p.key, p.time) for p in route.purchases] == [('tango', -89), ('bfury', 800)]
               for route in routes)
    assert all(route.skills == ['antimage_mana_break', 'antimage_mana_break'] for route in routes)
    assert updates and {r.id for r in updates[-1][0]} == {r.id for r in routes}
    assert status
    detail_queries = [query for detail, _, query in queries.calls if detail]
    assert detail_queries and all('players(steamAccountId:42)' in query for query in detail_queries)


def test_missing_stratz_game_uses_independent_opendota_fallback(client, monkeypatch):
    from dota_helper.stratz import normalize_stratz
    game = completed(501)
    route = normalize_stratz(game, game['players'][0], {})
    route.source = 'OpenDota'
    route.average_mmr = 8500
    calls, updates = [], []
    monkeypatch.setattr(client, 'query', FakeQueries({501: None}))
    def fallback(cache_dir, hero, role, candidates, progress, cancel, deadline, on_update=None):
        calls.append((cache_dir, hero, role, candidates, deadline))
        on_update(([route], 'OpenDota ready'))
        return [route], 'OpenDota verified'
    monkeypatch.setattr('dota_helper.rated_opendota.opendota_rated_routes', fallback)
    routes, status = run(client, [candidate(501)], on_update=updates.append)
    assert routes == [route] and updates[-1][0] == [route]
    assert calls[0][:3] == (client.cache_dir, 1, 1)
    assert calls[0][3] == [candidate(501)]
    assert 'OpenDota verified' in status


def test_summary_rejects_live_missing_and_wrong_role_games_before_detail_fetch(client, monkeypatch):
    games = {mid: completed(mid) for mid in range(1001, 1014)}
    games[1002]['endDateTime'] = None
    games[1003]['didRadiantWin'] = None
    games[1004]['players'][0]['heroId'] = 2
    games[1005]['players'][0]['position'] = 'POSITION_2'
    games[1006].update(rank=75, actualRank=75)
    games[1007]['leagueId'] = 42
    games[1008]['lobbyType'] = 'UNRANKED'
    games[1009]['durationSeconds'] = 0
    games[1010]['endDateTime'] = NOW + 1
    games[1011]['players'][0]['position'] = None
    games[1012]['endDateTime'] = 0
    games[1013]['didRadiantWin'] = 1  # An integer truth value is not a reported result.
    games[1014] = None
    queries = FakeQueries(games)
    monkeypatch.setattr(client, 'query', queries)
    routes, _ = run(client, [candidate(mid) for mid in games])
    assert [route.match_ids[0] for route in routes] == [1001]
    assert [mid for detail, ids, _ in queries.calls if detail for mid in ids] == [1001]


@pytest.mark.parametrize('changes', [
    {'match_id': True}, {'match_id': 501.5}, {'match_id': 'not-a-match'},
    {'average_mmr': None}, {'average_mmr': True}, {'average_mmr': 6999},
    {'average_mmr': float('nan')}, {'average_mmr': 30000},
    {'observed_at': None}, {'observed_at': NOW - MAX_AGE - 1},
    {'observed_at': NOW + 301}, {'observed_at': float('nan')},
])
def test_invalid_or_expired_candidates_do_not_trigger_match_queries(client, monkeypatch, changes):
    queries = FakeQueries({501: completed(501)})
    monkeypatch.setattr(client, 'query', queries)
    bad = candidate(501)
    bad.update(changes)
    routes, _ = run(client, [bad])
    assert not routes and not queries.calls


def test_exact_seven_thousand_threshold_and_duplicate_ids_fetch_once(client, monkeypatch):
    queries = FakeQueries({501: completed(501)})
    monkeypatch.setattr(client, 'query', queries)
    routes, _ = run(client, [candidate(501, 7000), candidate(501, 7000)])
    assert len(routes) == 1 and routes[0].average_mmr == 7000
    assert [mid for detail, ids, _ in queries.calls if detail for mid in ids] == [501]


@pytest.mark.parametrize('problem', ['wrong_id', 'wrong_hero', 'wrong_role', 'wrong_rank',
                                     'league', 'missing_result', 'no_purchases', 'no_skills'])
def test_details_must_still_be_the_eligible_recorded_match(client, monkeypatch, problem):
    details = completed(501)
    if problem == 'wrong_id':
        details['id'] = 777
    elif problem == 'wrong_hero':
        details['players'][0]['heroId'] = 2
    elif problem == 'wrong_role':
        details['players'][0]['position'] = 'POSITION_2'
    elif problem == 'wrong_rank':
        details.update(rank=75, actualRank=75)
    elif problem == 'league':
        details['leagueId'] = 42
    elif problem == 'missing_result':
        details['didRadiantWin'] = None
    elif problem == 'no_purchases':
        details['players'][0]['stats']['itemPurchases'] = []
    elif problem == 'no_skills':
        details['players'][0]['abilities'] = []
    queries = FakeQueries({501: completed(501)}, {501: details})
    monkeypatch.setattr(client, 'query', queries)
    routes, _ = run(client, [candidate(501, 9876)])
    assert routes == []


def test_more_than_ten_completed_candidates_remain_selectable_within_budget(client, monkeypatch):
    games = {mid: completed(mid) for mid in range(501, 526)}
    queries = FakeQueries(games)
    monkeypatch.setattr(client, 'query', queries)
    routes, _ = run(client, [candidate(mid, 7000 + mid) for mid in games])
    assert len(routes) == 25
    assert {r.match_ids[0] for r in routes} == set(games)
    assert all(len(ids) <= 10 for _, ids, _ in queries.calls)


def test_late_lookup_error_retains_already_published_builds(client, monkeypatch):
    games = {mid: completed(mid) for mid in range(501, 526)}
    queries = FakeQueries(games)
    queries.fail_detail_call = 2
    monkeypatch.setattr(client, 'query', queries)
    updates = []
    routes, status = run(client, [candidate(mid) for mid in games], on_update=updates.append)
    assert routes and len(routes) < len(games)
    assert updates and {r.id for r in updates[-1][0]} == {r.id for r in routes}
    assert 'limit' in status.lower() or 'cooldown' in status.lower()


def test_slow_summary_does_not_block_past_discovery_deadline(client, monkeypatch):
    release = threading.Event()
    started_query = threading.Event()
    def slow(query, variables=None):
        started_query.set()
        release.wait(1)
        return {}
    monkeypatch.setattr(client, 'query', slow)
    started = time.monotonic()
    try:
        routes, status = run(client, [candidate(501)], seconds=.08)
        assert started_query.is_set()
        assert time.monotonic() - started < .5
        assert routes == [] and status
    finally:
        release.set()


def test_cancelled_discovery_never_starts_queries(client, monkeypatch):
    cancel = threading.Event()
    cancel.set()
    queries = FakeQueries({501: completed(501)})
    monkeypatch.setattr(client, 'query', queries)
    with pytest.raises(DataError, match='cancelled'):
        run(client, [candidate(501)], cancel=cancel)
    assert queries.calls == []
