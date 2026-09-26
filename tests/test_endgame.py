from dataclasses import asdict
import re
import time
from zlib import crc32

import pytest

from dota_helper.catalog import ITEMS, PATCHES
from dota_helper.endgame import six_slot_items, finished_item
from dota_helper.builds import normalize
from dota_helper.guides import build_text
from dota_helper.history import decode
from dota_helper.models import Purchase
from dota_helper.ranking import ranked
from dota_helper.stratz import Stratz, normalize_stratz
from dota_helper.recommendations import recommended_routes
from test_core import route_fixture, match_fixture
from test_stratz import match

FINAL = ['butterfly', 'basher', 'manta', 'bfury', 'skadi', 'power_treads']


def complete(key='complete'):
    route = route_fixture()
    route.id = key
    route.match_ids = [crc32(key.encode()) + 1]
    route.final_items = FINAL.copy()
    return route


@pytest.mark.parametrize('bad', ['tango', 'enchanted_mango', 'ward_observer', 'recipe_manta',
                               'eagle', 'magic_wand', 'boots', 'branches', 'aghanims_shard',
                               'ultimate_scepter_2', 'moon_shard', '', 'unknown'])
def test_consumables_parts_fillers_missing_slots_and_consumed_upgrades_do_not_qualify(bad):
    route = complete()
    route.final_items[-1] = bad
    assert not six_slot_items(route)


def test_inventory_is_required_and_duplicate_completed_items_occupy_two_slots():
    route = complete()
    route.final_items[-1] = 'manta'
    assert len(six_slot_items(route)) == 6
    route.final_items.pop()
    assert not six_slot_items(route)
    route.final_items = []
    assert not six_slot_items(route)  # Never reconstruct sold/upgraded items from purchases.
    assert finished_item('blink') and finished_item('ghost') and finished_item('gem')


def test_provider_main_slots_survive_history_and_export_without_fabricated_timings():
    data = match()
    player = data['players'][0]
    for i, key in enumerate(FINAL):
        player[f'item{i}Id'] = ITEMS[key]['id']
    route = normalize_stratz(data, player, {})
    assert six_slot_items(route) == FINAL
    restored = decode({'hero': 1, 'role': 1, 'routes': [asdict(route)]})[0]
    assert six_slot_items(restored) == FINAL
    assert len(route.purchases) == 2  # Inventory does not add synthetic purchases.
    guide = build_text(route)
    assert 'Six-slot finish' in guide and 'not six additional purchases' in guide
    player.pop('item5Id')
    player['backpack0Id'] = ITEMS['power_treads']['id']
    assert not six_slot_items(normalize_stratz(data, player, {}))
    od = match_fixture()
    od['players'][0].update({f'item_{i}': ITEMS[key]['id'] for i, key in enumerate(FINAL)})
    assert six_slot_items(normalize(od, od['players'][0], 'fixture')) == FINAL


def test_six_slot_finish_never_displaces_better_ranked_games():
    normal = [route_fixture() for _ in range(10)]
    for i, route in enumerate(normal):
        route.id, route.average_mmr = str(i), 11000 - i
        route.match_ids = [100 + i]
    lower = complete('lower')
    lower.average_mmr = 8000
    assert ranked(normal + [lower]) == normal + [lower]
    assert ranked(normal + [lower], limit=10) == normal
    # Normal source preferences apply equally to short and complete games.
    lower.pro_player = True
    assert ranked(normal + [lower])[0] is lower
    assert not ranked([lower], 0)
    assert len(ranked(normal + [lower, lower])) == 11


@pytest.mark.parametrize('finish_match', [None, 10, 15])
def test_discovery_continues_past_ten_regardless_of_six_slot_finish(tmp_path, monkeypatch, finish_match):
    client = Stratz(tmp_path, token='test')
    calls = []
    games = {mid: match(mid) for mid in range(1, 31)}
    for mid, data in games.items():
        data['startDateTime'] = int(time.time()) - mid
        data['players'][0]['stats']['itemPurchases'].append({'itemId':ITEMS['branches']['id'], 'time':mid})
        data['players'][0]['abilities'].append({'abilityId':5004, 'time':mid, 'level':mid})
        # Distinct purchase signatures, not just timing differences.
        data['players'][0]['stats']['itemPurchases'] += [{'itemId':ITEMS['tango']['id'], 'time':100+j} for j in range(mid)]
    if finish_match:
        games[finish_match]['players'][0].update({f'item{i}Id':ITEMS[key]['id'] for i,key in enumerate(FINAL)})
    def query(q, variables=None):
        if 'heroStats' in q:
            return {'constants':{'gameVersions':[{'id':182,'name':PATCHES[-1]['name']}]},
                    'heroStats':{'guide':[{'matchCount':30,'guides':[
                        {'match':data,'heroId':1,'steamAccountId':42} for data in games.values()]}]}}
        if 'leaderboard' in q:
            return {'leaderboard':{'season':{'players':[]}}}
        mids = [int(n) for n in re.findall(r'match\(id:(\d+)\)',q)]
        calls.append(mids)
        assert 'item0Id' in q and 'item5Id' in q
        return {f'm{i}':games[mid] for i,mid in enumerate(mids)}
    monkeypatch.setattr(client, 'query', query)
    routes, status = client.routes(1, 1, reference_ids=[])
    assert len(routes) == 30 and calls == [list(range(1, 11)), list(range(11, 21)), list(range(21, 31))]
    assert bool(any(six_slot_items(r) for r in routes)) == bool(finish_match)
    assert '30 games' in status and '30 distinct builds' in status and '/10' not in status


def test_full_current_tournament_list_still_searches_pubs_with_remaining_budget(tmp_path, monkeypatch):
    client = Stratz(tmp_path, token='test')
    pros = []
    for i in range(10):
        route = route_fixture()
        route.id, route.tournament, route.patch = str(i), True, PATCHES[-1]['id']
        route.match_ids = [100 + i]
        route.purchases += [Purchase('branches', 60, occurrence=j+1) for j in range(i)]
        pros.append(route)
    final = complete()
    final.patch = PATCHES[-1]['id']
    calls = []
    monkeypatch.setattr('dota_helper.recommendations.tournament_routes', lambda *a, **kw: (pros, 'ready'))
    monkeypatch.setattr(client, 'routes', lambda *a, **kw: (calls.append(kw['deadline']), ([final], 'ready'))[1])
    routes, status = recommended_routes(client, 1, 1)
    assert len(calls) == 1 and routes == pros + [final]
    assert 'six-slot' not in status
