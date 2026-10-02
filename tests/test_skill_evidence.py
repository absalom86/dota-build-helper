import threading

import pytest

from dota_helper.catalog import ABILITY_IDS
from dota_helper.skill_evidence import needs_recovery, recover_skills
from test_core import route_fixture

# Public match 8948311007: STRATZ supplies zero at upgrades 11 and 16;
# OpenDota identifies both talents and agrees at every other sequence position.
IDS = [1502,1500,1499,1500,1500,1501,1500,1502,1498,1502,1509,1499,1506,1503,1499,1511,1501]


def sample():
    route = route_fixture()
    route.hero_id, route.source, route.match_ids, route.player_slot = 145, 'STRATZ', [8948311007], 128
    route.skills = [ABILITY_IDS[str(i)] if n not in (10,15) else 'dota_base_ability' for n,i in enumerate(IDS)]
    return route


class Client:
    def __init__(self):
        self.calls = 0
        self.match = {'match_id':8948311007, 'players':[{'hero_id':145, 'player_slot':128, 'ability_upgrades_arr':IDS.copy()}]}

    def get(self, path, ttl):
        assert path == 'matches/8948311007'
        self.calls += 1
        return self.match


def test_recovers_exact_kez_talents_without_mutating_original():
    route, client = sample(), Client()
    result = recover_skills(route, client, threading.Event())
    assert result[10] == 'special_bonus_unique_kez_raptor_dance_radius'
    assert result[15] == 'special_bonus_unique_kez_falcon_rush_duration'
    assert route.skills[10] == 'dota_base_ability'
    assert len(result) == 17 and client.calls == 1


@pytest.mark.parametrize('failure', ['match', 'hero', 'player', 'sequence', 'length', 'ambiguous'])
def test_rejects_wrong_identity_or_disagreeing_sequence(failure):
    route, client = sample(), Client()
    player = client.match['players'][0]
    if failure == 'match': client.match['match_id'] = 1
    if failure == 'hero': player['hero_id'] = 1
    if failure == 'player': player['player_slot'] = 129
    if failure == 'sequence': player['ability_upgrades_arr'][0] = 1499
    if failure == 'length': player['ability_upgrades_arr'].pop()
    if failure == 'ambiguous': client.match['players'].append(player.copy())
    assert recover_skills(route, client, threading.Event()) is None


def test_complete_or_cancelled_routes_do_not_fetch():
    route, client = sample(), Client()
    cancel = threading.Event()
    cancel.set()
    assert recover_skills(route, client, cancel) is None
    route.skills = [ABILITY_IDS[str(i)] for i in IDS]
    assert not needs_recovery(route)
    assert recover_skills(route, client, threading.Event()) is None
    assert client.calls == 0


@pytest.mark.parametrize('unknown', [0, 999999])
def test_partial_recovery_keeps_unidentified_slot_without_discarding_known_talent(unknown):
    route, client = sample(), Client()
    client.match['players'][0]['ability_upgrades_arr'][10] = unknown
    skills = recover_skills(route, client, threading.Event())
    assert skills[10] == 'dota_base_ability'
    assert skills[15] == 'special_bonus_unique_kez_falcon_rush_duration'


def test_new_kez_talent_id_and_saved_numeric_import_resolve():
    from dataclasses import replace
    from dota_helper.talents import talent_branches
    route, client = sample(), Client()
    client.match['players'][0]['ability_upgrades_arr'][10] = 1748
    skills = recover_skills(route, client, threading.Event())
    assert skills[10] == 'special_bonus_unique_kez_switch_weapons_swap_bonus'
    assert replace(route, skills=['1748']).skills == [skills[10]]
    assert talent_branches(145, [skills[10], 'special_bonus_unique_kez_raptor_dance_radius'])[0] == {(10, 'right')}


def test_recovered_skills_survive_history_restart_without_changing_search_age(tmp_path):
    from dota_helper.history import SearchHistory, decode
    route = sample()
    history = SearchHistory(tmp_path)
    history.save(145, 1, 0, [route], route.id, 'Ready')
    before = history.find(145, 1, 0)['updated']
    original = list(route.skills)
    route.skills = recover_skills(route, Client(), threading.Event())
    history.save_recovered_skills(route, original)
    restored = SearchHistory(tmp_path).find(145, 1, 0)
    assert restored['updated'] == before and restored['selected'] == route.id
    assert decode(restored)[0].skills == route.skills


@pytest.mark.parametrize('switch_game', [False, True])
def test_background_result_updates_only_same_selected_game(tmp_path, monkeypatch, qt_application, switch_game):
    from dota_helper.app import MainWindow
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    monkeypatch.setenv('DOTA_HELPER_HOME', str(tmp_path))
    window = MainWindow(start_services=False)
    window.timer.stop()
    window.capture_timer.stop()
    route = sample()
    window.routes = [route]
    window.session.selected = route.id
    callbacks = []
    monkeypatch.setattr(window, 'launch_worker', lambda fn, done, failed: callbacks.append(done))
    monkeypatch.setattr(window, 'render_route', lambda: None)
    monkeypatch.setattr(window, 'tick', lambda: None)
    window.services_started = True
    window.schedule_skill_recovery()
    window.schedule_skill_recovery()
    assert len(callbacks) == 1 and window.skill_recovery_busy
    if switch_game:
        window.routes = [route_fixture()]
        window.routes[0].id = 'different-game'
        window.session.selected = 'different-game'
    window.services_started = False
    callbacks[0]([ABILITY_IDS[str(i)] for i in IDS])
    assert ('dota_base_ability' in route.skills) == switch_game
    assert not window.skill_recovery_busy
    window.close()
