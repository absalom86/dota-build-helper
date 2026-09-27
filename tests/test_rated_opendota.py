"""Captured match MMR may seed a parsed OpenDota build, never a different game."""
from copy import deepcopy
import threading
import time

import pytest

from dota_helper.catalog import PATCHES
from dota_helper.live_ratings import MAX_AGE, SOURCE
from dota_helper.providers import DataError
from dota_helper.rated_opendota import opendota_rated_routes
from test_fast_lookup import match


NOW = int(time.time())


def completed(mid):
    game = match(mid)
    game.update(start_time=NOW - 1900, duration=1800, radiant_win=False,
                lobby_type=7, leagueid=0)
    return game


def candidate(mid, mmr=8500):
    return {'match_id': mid, 'average_mmr': mmr, 'observed_at': NOW - 120}


@pytest.fixture
def install_games(monkeypatch):
    monkeypatch.setattr('dota_helper.rated_opendota.time.time', lambda: NOW)
    monkeypatch.setattr('dota_helper.providers.urlopen',
                        lambda *args, **kwargs: pytest.fail('Unexpected OpenDota network call'))
    monkeypatch.setattr('dota_helper.live_ratings.urlopen',
                        lambda *args, **kwargs: pytest.fail('Build discovery must not fetch the live feed'))
    def install(games):
        calls = []
        def get(self, path, **kwargs):
            calls.append((path, kwargs))
            mid = int(path.removeprefix('matches/'))
            value = games[mid]
            if isinstance(value, Exception):
                raise value
            return deepcopy(value)
        monkeypatch.setattr('dota_helper.rated_opendota.OpenDota.get', get)
        return calls
    return install


def run(tmp_path, candidates, *, cancel=None, seconds=2, on_update=None):
    return opendota_rated_routes(tmp_path, 1, 1, candidates, lambda _: None,
                                 cancel if cancel is not None else threading.Event(),
                                 deadline=time.monotonic() + seconds, on_update=on_update)


def test_exact_match_mmr_uses_parsed_opendota_without_inventing_rank(tmp_path, install_games):
    first, second = completed(501), completed(502)
    for game in (first, second):
        game['players'][0]['rank_tier'] = None
        game['avg_mmr'] = 9999  # The explicit captured observation is the requested source.
    calls = install_games({501: first, 502: second})
    updates = []
    routes, status = run(tmp_path, [candidate(501, 8123), candidate(502, 9200)],
                         on_update=updates.append)
    assert [route.match_ids[0] for route in routes] == [502, 501]
    assert [route.average_mmr for route in routes] == [9200, 8123]
    assert all(route.source == 'OpenDota' and route.average_mmr_source == SOURCE for route in routes)
    assert all(route.average_rank is None and route.match_rank is None for route in routes)
    assert all(route.hero_id == 1 and route.role == 1 for route in routes)
    assert all([(p.key, p.time) for p in route.purchases] == [('tango', -30), ('bfury', 900)]
               for route in routes)
    assert all(route.skills == ['antimage_mana_break'] for route in routes)
    assert updates and {route.id for route in updates[-1][0]} == {route.id for route in routes}
    assert {path for path, _ in calls} == {'matches/501', 'matches/502'}
    assert all(options.get('ttl') == 300 for _, options in calls)
    assert status


def test_reported_match_average_rank_is_preserved(tmp_path, install_games):
    game = completed(501)
    game['avg_rank_tier'] = 80
    install_games({501: game})
    routes, _ = run(tmp_path, [candidate(501)])
    assert len(routes) == 1
    assert routes[0].average_rank == routes[0].match_rank == 80
    assert routes[0].average_rank_source == 'OpenDota match average'


@pytest.mark.parametrize('source_patch', [PATCHES[-1]['id'] - 1, 0])
def test_recent_game_does_not_get_relabelled_as_current_patch(tmp_path, install_games, source_patch):
    game = completed(501)
    game['patch'] = source_patch
    install_games({501: game})
    routes, _ = run(tmp_path, [candidate(501)])
    assert len(routes) == 1
    assert routes[0].patch == source_patch
    assert routes[0].patch != PATCHES[-1]['id']
    assert not any('older patch' in warning.lower() for warning in routes[0].warnings)
    if source_patch:
        assert routes[0].patch_label == next(p['name'] for p in PATCHES if p['id'] == source_patch)
    else:
        assert 'unverified' in routes[0].patch_label.lower()


def test_sixty_day_prior_patch_completed_game_is_accepted_without_outdated_warning(tmp_path, install_games):
    game = completed(501)
    game.update(start_time=NOW - 60 * 86400, patch=PATCHES[-1]['id'] - 1)
    install_games({501: game})
    routes, _ = run(tmp_path, [candidate(501)])
    assert len(routes) == 1 and routes[0].average_mmr == 8500
    assert routes[0].patch == PATCHES[-1]['id'] - 1
    assert not any('older patch' in warning.lower() for warning in routes[0].warnings)


@pytest.mark.parametrize('problem', [
    'wrong_id', 'wrong_hero', 'ambiguous_hero', 'wrong_role', 'missing_role',
    'below_immortal_opponent', 'league', 'unranked', 'missing_result', 'integer_result',
    'zero_duration', 'missing_duration', 'nonfinite_duration', 'future_finish',
    'future_start', 'outside_90_day_window', 'no_purchases', 'no_skills',
])
def test_only_completed_eligible_exact_games_supply_builds(tmp_path, install_games, problem):
    game = completed(501)
    if problem == 'wrong_id':
        game['match_id'] = 777
    elif problem == 'wrong_hero':
        game['players'][0]['hero_id'] = 2
    elif problem == 'ambiguous_hero':
        game['players'].append(deepcopy(game['players'][0]))
    elif problem == 'wrong_role':
        game['players'][0]['position_est'] = 2
    elif problem == 'missing_role':
        game['players'][0].pop('position_est')
    elif problem == 'below_immortal_opponent':
        game['players'].append({'hero_id': 2, 'rank_tier': 75})
    elif problem == 'league':
        game['leagueid'] = 42
    elif problem == 'unranked':
        game['lobby_type'] = 0
    elif problem == 'missing_result':
        game['radiant_win'] = None
    elif problem == 'integer_result':
        game['radiant_win'] = 1
    elif problem == 'zero_duration':
        game['duration'] = 0
    elif problem == 'missing_duration':
        game.pop('duration')
    elif problem == 'nonfinite_duration':
        game['duration'] = float('nan')
    elif problem == 'future_finish':
        game['start_time'] = NOW - 10
    elif problem == 'future_start':
        game['start_time'] = NOW + 1
    elif problem == 'outside_90_day_window':
        game['start_time'] = NOW - 91 * 86400
    elif problem == 'no_purchases':
        game['players'][0]['purchase_log'] = []
    elif problem == 'no_skills':
        game['players'][0]['ability_upgrades_arr'] = []
    calls = install_games({501: game})
    routes, _ = run(tmp_path, [candidate(501)])
    assert routes == []
    assert len(calls) == 1


@pytest.mark.parametrize('changes', [
    {'match_id': True}, {'match_id': 501.5}, {'average_mmr': None},
    {'average_mmr': True}, {'average_mmr': 0}, {'average_mmr': float('nan')},
    {'average_mmr': 30000}, {'observed_at': None},
    {'observed_at': NOW - MAX_AGE - 1}, {'observed_at': NOW + 301},
])
def test_invalid_candidate_cannot_trigger_detail_request(tmp_path, install_games, changes):
    calls = install_games({501: completed(501)})
    invalid = candidate(501)
    invalid.update(changes)
    routes, _ = run(tmp_path, [invalid])
    assert routes == [] and calls == []


def test_threshold_duplicates_and_more_than_ten_results(tmp_path, install_games):
    games = {mid: completed(mid) for mid in range(501, 519)}
    calls = install_games(games)
    candidates = [candidate(mid, 7000 + mid - 501) for mid in games]
    updates = []
    routes, _ = run(tmp_path, candidates + [candidates[0]], on_update=updates.append)
    assert len(routes) == 18
    assert {route.match_ids[0] for route in routes} == set(games)
    assert min(route.average_mmr for route in routes) == 7000
    assert len(calls) == len(games)
    assert any(len(ready) > 10 for ready, _ in updates)


def test_failed_detail_keeps_other_captured_builds(tmp_path, install_games):
    calls = install_games({501: completed(501), 502: DataError('OpenDota offline'),
                           503: completed(503)})
    updates = []
    routes, status = run(tmp_path, [candidate(mid) for mid in (501, 502, 503)],
                         on_update=updates.append)
    assert {route.match_ids[0] for route in routes} == {501, 503}
    assert len(calls) == 3
    assert updates and {r.id for r in updates[-1][0]} == {r.id for r in routes}
    assert 'failure' in status.lower() or 'error' in status.lower() or 'offline' in status.lower()


def test_slow_requests_respect_deadline_and_at_most_two_in_flight(tmp_path, install_games, monkeypatch):
    release = threading.Event()
    lock = threading.Lock()
    started_ids = []
    def slow(self, path, **kwargs):
        with lock:
            started_ids.append(path)
        release.wait(1)
        return completed(int(path.removeprefix('matches/')))
    monkeypatch.setattr('dota_helper.rated_opendota.OpenDota.get', slow)
    start = time.monotonic()
    try:
        routes, status = run(tmp_path, [candidate(mid) for mid in (501, 502, 503)], seconds=.08)
        assert time.monotonic() - start < .5
        assert 1 <= len(started_ids) <= 2
        assert not routes and status
    finally:
        release.set()


def test_cancelled_discovery_never_starts_queries(tmp_path, install_games):
    calls = install_games({501: completed(501)})
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(DataError, match='cancelled'):
        run(tmp_path, [candidate(501)], cancel=cancel)
    assert calls == []


def test_cancel_after_first_stream_is_respected(tmp_path, install_games):
    install_games({mid: completed(mid) for mid in range(501, 510)})
    cancel = threading.Event()
    updates = []
    def on_update(value):
        updates.append(value)
        cancel.set()
    with pytest.raises(DataError, match='cancelled'):
        run(tmp_path, [candidate(mid) for mid in range(501, 510)], cancel=cancel, on_update=on_update)
    assert updates and updates[0][0]


def riki_completed():
    """Shape of the observed 5,869 MMR Riki carry match, including ten ranks."""
    game = completed(9017846688)
    game['players'] = [dict(hero_id=hero, player_slot=slot, rank_tier=80)
                       for hero, slot in zip(range(1, 11), (*range(5), *range(128, 133)))]
    game['players'][4].update(
        hero_id=32, position_est=1, lane_role=1,
        purchase_log=[{'time': -89, 'key': 'tango'}, {'time': -89, 'key': 'branches'},
                      {'time': -89, 'key': 'branches'}, {'time': -89, 'key': 'branches'},
                      {'time': 417, 'key': 'phylactery'}, {'time': 891, 'key': 'diffusal_blade'}],
        ability_upgrades_arr=[5143, 5145, 5143, 5142, 5143, 5144])
    return game


def run_riki(tmp_path):
    return opendota_rated_routes(tmp_path, 32, 1, [candidate(9017846688, 5869)],
                                 lambda _: None, threading.Event(),
                                 deadline=time.monotonic() + 2)


def test_recorded_immortal_riki_match_below_seven_thousand_keeps_actual_average(tmp_path, install_games):
    calls = install_games({9017846688: riki_completed()})
    routes, _ = run_riki(tmp_path)
    assert len(calls) == len(routes) == 1
    route = routes[0]
    assert route.hero_id == 32 and route.role == 1 and route.match_ids == [9017846688]
    assert route.average_mmr == 5869 and route.average_mmr_source == SOURCE
    assert [purchase.key for purchase in route.purchases].count('branches') == 3
    assert route.skills[:2] == ['riki_blink_strike', 'riki_tricks_of_the_trade']


@pytest.mark.parametrize('problem', ['divine_player', 'missing_rank', 'missing_player',
                                    'duplicate_slot', 'divine_match_average'])
def test_low_mmr_game_needs_independent_immortal_evidence(tmp_path, install_games, problem):
    game = riki_completed()
    if problem == 'divine_player':
        game['players'][0]['rank_tier'] = 75
        game['avg_rank_tier'] = 80
    elif problem == 'missing_rank':
        game['players'][0]['rank_tier'] = None
    elif problem == 'missing_player':
        game['players'].pop(0)
    elif problem == 'duplicate_slot':
        game['players'][0]['player_slot'] = 1
    elif problem == 'divine_match_average':
        game['avg_rank_tier'] = 75
    calls = install_games({9017846688: game})
    routes, status = run_riki(tmp_path)
    assert not routes and len(calls) == 1
    assert 'Immortal' in status


def test_source_immortal_average_can_qualify_low_mmr_with_missing_profiles(tmp_path, install_games):
    game = riki_completed()
    game['players'][0]['rank_tier'] = None
    game['avg_rank_tier'] = 80
    install_games({9017846688: game})
    routes, _ = run_riki(tmp_path)
    assert len(routes) == 1 and routes[0].average_mmr == 5869
    assert routes[0].average_rank == 80
