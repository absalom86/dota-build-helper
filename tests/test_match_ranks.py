from dataclasses import asdict

import pytest

from dota_helper.builds import normalize
from dota_helper.guides import title
from dota_helper.history import decode
from dota_helper.overlay import route_identity
from dota_helper.ratings import (rating_text, rating_help, match_rank, rank_tier,
                                 average_mmr_text, average_mmr_help,
                                 average_rank_text, average_rank_help, average_rank_value)
from dota_helper.ranking import ranked
from dota_helper.stratz import normalize_stratz
from test_stratz import match
from test_core import match_fixture, route_fixture


@pytest.mark.parametrize('value,expected', [(80, 'Immortal'), (75, 'Divine 5'), (71, 'Divine 1'),
                                         (60, 'Ancient'), (55, 'Legend 5'), (41, 'Archon 1'),
                                         (31, 'Crusader 1'), (21, 'Guardian 1'), (11, 'Herald 1'),
                                         (None, 'Rank unknown'), (0, 'Rank unknown'), (99, 'Rank unknown')])
def test_stratz_match_rank_display_without_profile_substitution(value, expected):
    data = match()
    data['rank'] = value
    data['players'][0]['steamAccount']['seasonRank'] = 80
    route = normalize_stratz(data, data['players'][0], {})
    assert rating_text(route) == expected
    assert expected in route_identity(route)
    assert expected in title(route)
    assert '#710' not in rating_text(route)


@pytest.mark.parametrize('value', [True, False, '80', -1, 81, 76, float('nan'), float('inf'), 74.3])
def test_invalid_discrete_match_rank_is_not_a_medal(value):
    assert rank_tier(value) is None


def test_opendota_average_and_player_profile_are_distinct():
    data = match_fixture()
    data['players'][0]['rank_tier'] = 80
    assert rating_text(normalize(data, data['players'][0], 'profile')) == 'Rank unknown'
    data['avg_rank_tier'] = 73.6
    route = normalize(data, data['players'][0], 'average')
    assert route.match_rank == 73.6
    assert rating_text(route) == 'Divine (avg)'
    assert 'OpenDota match average' in rating_help(route)
    route.average_mmr = 8123
    assert rating_text(route) == '8,123 MMR'
    route.pro_player = True
    assert rating_text(route) == 'PRO'


def test_rank_sort_preserves_patch_pro_and_mmr_groups_with_stable_ties():
    routes = []
    for name, rank, timestamp in [('unknown', None, 999), ('divine', 75, 800),
                                  ('immortal-old', 80, 100), ('immortal-new', 80, 200),
                                  ('ancient', 65, 900)]:
        route = route_fixture()
        route.id, route.match_rank, route.start_time = name, rank, timestamp
        route.match_ids = [100 + len(routes)]
        routes.append(route)
    pro = route_fixture()
    pro.id, pro.pro_player = 'pro', True
    pro.match_ids = [201]
    mmr = route_fixture()
    mmr.id, mmr.average_mmr = 'mmr', 9000
    mmr.match_ids = [202]
    assert [r.id for r in ranked(routes + [pro, mmr])] == [
        'pro', 'mmr', 'immortal-new', 'immortal-old', 'divine', 'ancient', 'unknown']


def test_legacy_history_rank_recovery_does_not_need_network():
    data = match()
    route = normalize_stratz(data, data['players'][0], {})
    old = asdict(route)
    old.pop('match_rank')
    old.pop('match_rank_source')
    restored = decode({'hero': 1, 'role': 1, 'routes': [old]})[0]
    assert restored.match_rank is None
    assert rating_text(restored) == 'Immortal'
    restored.evidence = 'Immortal-ranked player profile · Match MMR UNVERIFIED'
    assert match_rank(restored) is None
    restored.source = 'OpenDota'
    assert match_rank(restored) is None
    restored.evidence = 'OpenDota sampled pub · 10/10 recorded ranks Immortal · numeric MMR unavailable'
    assert rating_text(restored) == 'Immortal'


def test_structured_rank_survives_history_round_trip():
    data = match()
    data['rank'] = 75
    route = normalize_stratz(data, data['players'][0], {})
    restored = decode({'hero': 1, 'role': 1, 'routes': [asdict(route)]})[0]
    assert restored.match_rank == 75
    assert restored.match_rank_source == 'STRATZ match bracket'
    assert rating_text(restored) == 'Divine 5'


def test_mmr_and_average_rank_display_independently_even_for_pro_pub():
    data = match_fixture()
    data.update(avg_mmr=8123, avg_rank_tier=73.6)
    data['players'][0]['rank_tier'] = 80
    route = normalize(data, data['players'][0], 'fixture')
    route.pro_player = True
    assert route.average_mmr_source == 'OpenDota avg_mmr'
    assert route.average_rank == 73.6 and route.match_rank == 73.6
    assert average_mmr_text(route) == '8,123'
    assert average_rank_text(route) == 'Divine'
    assert 'OpenDota avg_mmr' in average_mmr_help(route)
    assert 'OpenDota match average' in average_rank_help(route)
    assert '73.6' in average_rank_help(route)
    route.average_mmr_source = 'Valve live match average via OpenDota'
    assert 'Valve live match average via OpenDota' in average_mmr_help(route)


@pytest.mark.parametrize('value', [None, True, False, '80', -1, 0, 81, {}, [], float('nan'), float('inf')])
def test_invalid_average_rank_never_becomes_mmr_or_player_rank(value):
    data = match()
    data.update(averageRank=value, rank=None, actualRank=None)
    route = normalize_stratz(data, data['players'][0], {})
    assert route.average_rank is None and route.average_rank_source == ''
    assert average_rank_text(route) == '—'
    assert average_mmr_text(route) == '—'
    assert route.average_mmr is None
    assert 'individual player' in average_rank_help(route)


@pytest.mark.parametrize('value', [None, True, False, '8000', -1, 0, 30000, {}, [], float('nan'), float('inf')])
def test_invalid_average_mmr_is_missing_even_with_profile_estimate(value):
    data = match_fixture()
    data['avg_mmr'] = value
    data['players'][0].update(mmr_estimate={'estimate':9000}, rank_tier=80)
    route = normalize(data, data['players'][0], 'profile')
    assert route.average_mmr is None and route.average_mmr_source == ''
    assert average_mmr_text(route) == '—'
    assert average_rank_text(route) == '—'


def test_stratz_average_and_bracket_are_separate_and_used_in_rank_order():
    data = match()
    data.update(rank=80, actualRank=80, averageRank=73.6)
    route = normalize_stratz(data, data['players'][0], {})
    assert route.match_rank == 80
    assert route.average_rank == 73.6
    assert route.average_rank_source == 'STRATZ averageRank'
    assert average_rank_text(route) == 'Divine'
    assert 'STRATZ averageRank' in average_rank_help(route)
    assert match_rank(route) == 73.6
    assert average_mmr_text(route) == '—'
    assert route.average_mmr is None
    higher = route_fixture()
    higher.id, higher.average_rank = 'higher-average', 79.5
    assert ranked([route, higher])[0] is higher


def test_average_rank_missing_uses_explicit_bracket_label():
    data = match()
    route = normalize_stratz(data, data['players'][0], {})
    assert average_rank_text(route) == 'Immortal (bracket)'
    assert 'fallback' in average_rank_help(route)
    assert 'not an exact match average' in average_rank_help(route)
    data.update(rank=None, actualRank=75)
    route = normalize_stratz(data, data['players'][0], {})
    assert average_rank_text(route) == 'Divine 5 (bracket)'
    assert route.match_rank_source == 'STRATZ actualRank bracket'


def test_new_average_fields_survive_history_and_old_opendota_source_recovers():
    data = match_fixture()
    data.update(avg_mmr=8123, avg_rank_tier=73.6)
    route = normalize(data, data['players'][0], 'average')
    record = asdict(route)
    restored = decode({'hero':1, 'role':route.role, 'routes':[record]})[0]
    assert restored.average_mmr == 8123 and restored.average_mmr_source == 'OpenDota avg_mmr'
    assert restored.average_rank == 73.6 and restored.average_rank_source == 'OpenDota match average'
    for key in ('average_rank', 'average_rank_source', 'average_mmr_source'):
        record.pop(key)
    legacy = decode({'hero':1, 'role':route.role, 'routes':[record]})[0]
    assert average_rank_value(legacy) == 73.6
    assert average_rank_text(legacy) == 'Divine'
    assert 'OpenDota match average' in average_rank_help(legacy)
    assert average_mmr_text(legacy) == '8,123'


@pytest.mark.parametrize('field', ['demo', 'tournament'])
def test_non_pub_average_columns_are_unavailable(field):
    route = route_fixture()
    route.average_mmr, route.average_rank = 8123, 80
    setattr(route, field, True)
    assert average_mmr_text(route) == average_rank_text(route) == '—'
    expected = 'does not apply' if field == 'tournament' else 'Synthetic demo'
    assert expected in average_mmr_help(route)
    assert expected in average_rank_help(route)
