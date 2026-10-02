"""Optional endgame references must never take over the followed build."""
from dataclasses import asdict
from copy import deepcopy
import time

import pytest
from dota_helper.catalog import PATCHES
from dota_helper.endgame import endgame_examples
from dota_helper.history import SearchHistory, decode, decode_examples
from test_core import route_fixture
from test_endgame import complete, FINAL


def test_options_rank_sources_deduplicate_slot_order_and_filter_context():
    low, high, pro, duplicate = [complete(key) for key in ('low', 'high', 'pro', 'duplicate')]
    low.average_mmr, high.average_mmr = 7000, 10000
    pro.pro_player = True
    pro.final_items[-1] = 'travel_boots'
    duplicate.average_mmr = 8000
    duplicate.final_items.reverse()
    wrong_hero, wrong_role, demo, incomplete = [complete(key) for key in ('hero', 'role', 'demo', 'incomplete')]
    wrong_hero.hero_id = 74
    wrong_role.role = 5
    demo.demo = True
    incomplete.final_items.pop()
    options = endgame_examples([low, high, pro, duplicate, wrong_hero, wrong_role, demo, incomplete], 1, 1)
    assert [r.id for r in options] == ['pro', 'high']
    assert high.final_items == FINAL


def test_recent_pro_examples_precede_pubs_across_patch_versions():
    current, old, unknown = [complete(key) for key in ('current', 'old', 'unknown')]
    current.patch, current.patch_label = PATCHES[-1]['id'], PATCHES[-1]['name']
    old.patch, old.patch_label, old.pro_player = PATCHES[-2]['id'], PATCHES[-2]['name'], True
    unknown.patch, unknown.patch_label, unknown.pro_player = PATCHES[-1]['id'], 'unverified', True
    now = int(time.time())
    current.start_time, old.start_time, unknown.start_time = [now-days*86400 for days in (1, 60, 75)]
    assert endgame_examples([old, unknown, current], 1, 1) == [old]
    unknown.start_time = now - 30 * 86400
    assert endgame_examples([old, unknown, current], 1, 1) == [unknown]


def test_three_distinct_targets_keep_best_sources_and_survive_history(tmp_path):
    routes = [complete(str(index)) for index in range(5)]
    for index, route in enumerate(routes):
        route.average_mmr = 11000 - index * 1000
        route.final_items[-1] = ['travel_boots', 'power_treads', 'abyssal_blade', 'butterfly', 'travel_boots'][index]
    routes[-1].pro_player = True
    expected = [routes[-1].id, routes[1].id, routes[2].id]
    assert [r.id for r in endgame_examples(routes, 1, 1)] == expected
    history = SearchHistory(tmp_path)
    history.save(1, 1, 0, routes, routes[0].id, 'Ready')
    restored = SearchHistory(tmp_path).find(1, 1, 0)
    assert [r.id for r in decode_examples(restored)] == expected


def test_history_keeps_optional_finish_after_top_ten_and_across_refresh(tmp_path):
    history = SearchHistory(tmp_path)
    routes = []
    for i in range(10):
        route = route_fixture()
        route.id, route.average_mmr = f'high:{i}', 11000-i
        route.match_ids = [100 + i]
        routes.append(route)
    finish = complete('finish')
    finish.average_mmr = 7000
    history.save(1, 1, 0, routes + [finish], routes[0].id, 'Ready')
    entry = history.find(1, 1, 0)
    assert [r.id for r in decode(entry)] == [r.id for r in routes] + [finish.id]
    assert [r.id for r in decode_examples(entry)] == [finish.id]
    history.save(1, 1, 0, routes, routes[2].id, 'Refreshed')
    restored = SearchHistory(tmp_path).find(1, 1, 0)
    assert [r.id for r in decode_examples(restored)] == [finish.id]
    assert restored['selected'] == routes[2].id
    assert len(decode(restored)) == 11


def test_missing_refreshed_inventory_does_not_erase_saved_observation(tmp_path):
    history = SearchHistory(tmp_path)
    finish = complete()
    history.save(1, 1, 0, [finish], finish.id, 'Ready')
    refreshed = deepcopy(finish)
    refreshed.final_items = []
    history.save(1, 1, 0, [refreshed], finish.id, 'Refreshed')
    restored = SearchHistory(tmp_path).find(1, 1, 0)
    assert decode(restored)[0].final_items == []
    assert decode_examples(restored)[0].final_items == FINAL


@pytest.mark.parametrize('invalid', [None, 1, 'manta', [None]*6, [{}]*6])
def test_malformed_saved_inventories_are_skipped(invalid):
    record = asdict(complete())
    record['final_items'] = invalid
    entry = {'hero': 1, 'role': 1, 'routes': [record], 'endgame_routes': None}
    assert not decode_examples(entry)
