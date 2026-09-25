from collections import Counter
from types import SimpleNamespace

import pytest

from dota_helper.models import Session


def payload(hero=1, match=42, clock=100):
    return {
        'hero': {'id': hero, 'level': 4},
        'player': {'steamid': 'local-test-player'},
        'map': {'matchid': match, 'clock_time': clock,
                'game_state': 'DOTA_GAMERULES_STATE_GAME_IN_PROGRESS'},
    }


@pytest.fixture
def now(monkeypatch):
    value = [100.0]
    monkeypatch.setattr('dota_helper.models.time.monotonic', lambda: value[0])
    return value


def test_missing_items_and_skills_are_not_received_with_hero_clock(now):
    session = Session()
    assert session.ingest(payload())
    assert session.field_status('hero') == 'fresh'
    assert session.field_status('clock') == 'fresh'
    assert session.field_status('inventory') == 'missing'
    assert session.field_status('charges') == 'missing'
    assert session.field_status('skills') == 'missing'
    assert session.inventory == Counter()


def test_missing_fields_preserve_last_values_without_refreshing_them(now):
    session = Session()
    first = payload()
    first['map']['paused'] = True
    first['items'] = {'slot0': {'name': 'item_tango', 'charges': 2}}
    first['abilities'] = {'ability0': {'name': 'antimage_mana_break', 'level': 2}}
    session.ingest(first)
    now[0] = 107.0
    update = payload()
    del update['map']['clock_time']
    del update['hero']['level']
    assert session.ingest(update)
    assert session.field_status('hero') == 'fresh'
    assert session.last_gsi == 107.0
    for field in ('clock', 'inventory', 'charges', 'skills'):
        assert session.field_status(field) == 'stale'
    assert session.clock == 100 and session.paused and session.level == 4
    assert session.inventory['tango'] == 1
    assert session.inventory_charges['tango'] == 2
    assert session.learned['antimage_mana_break'] == 2


def test_items_count_occupied_slots_separately_from_primary_secondary_charges(now):
    session = Session()
    update = payload()
    update['items'] = {
        'slot0': {'name': 'item_tango', 'charges': 3},
        'slot1': {'name': 'item_tango', 'primary_charges': 2},
        'slot2': {'name': 'item_branches'},
        'slot3': {'name': 'item_branches'},
        'slot4': {'name': 'item_ward_dispenser', 'charges': 2, 'secondary_charges': 4},
        'slot5': {'name': 'empty'},
        'stash0': {'name': 'item_flask', 'item_charges': 0, 'charges2': 1},
        'teleport0': {'name': 'item_tpscroll', 'charges': 2},
    }
    session.ingest(update)
    assert session.inventory == Counter(tango=2, branches=2, ward_dispenser=1, flask=1)
    assert session.inventory_slots['slot0'] == 'tango'
    assert session.inventory_slot_charges['slot1'] == 2
    assert session.inventory_charges == Counter(tango=5, ward_dispenser=2, flask=0)
    assert session.inventory_secondary_charges == Counter(ward_dispenser=4, flask=1)
    assert 'branches' not in session.inventory_charges
    assert session.field_status('inventory') == 'fresh'
    assert session.field_status('charges') == 'fresh'
    assert not session.completed


def test_partial_charge_fields_do_not_become_zero_or_partial_totals(now):
    session = Session()
    update = payload()
    update['items'] = {'slot0': {'name': 'item_tango', 'charges': 3},
                       'slot1': {'name': 'item_tango'}}
    session.ingest(update)
    assert session.inventory['tango'] == 2
    assert session.inventory_slot_charges == {'slot0': 3}
    assert 'tango' not in session.inventory_charges
    now[0] += 1
    update['items'] = {'slot0': {'name': 'item_tango'}}
    session.ingest(update)
    assert session.inventory['tango'] == 1
    assert session.inventory_charges == Counter()
    assert session.field_status('charges') == 'missing'
    assert session.field_status('inventory') == 'fresh'


@pytest.mark.parametrize('items', [{}, {'slot0': {'name': 'empty'}}])
def test_explicit_empty_inventory_is_fresh_and_clears_previous_stacks(now, items):
    session = Session()
    first = payload()
    first['items'] = {'slot0': {'name': 'item_tango', 'charges': 3}}
    session.ingest(first)
    now[0] += 10
    update = payload()
    update['items'] = items
    session.ingest(update)
    assert not session.inventory and not session.inventory_slots
    assert not session.inventory_charges and not session.inventory_slot_charges
    assert session.inventory_at == now[0]
    assert session.field_status('inventory') == 'fresh'


def test_malformed_or_spectator_sections_do_not_replace_last_good_snapshot(now):
    session = Session()
    first = payload()
    first['items'] = {'slot0': {'name': 'item_tango', 'charges': 3}}
    first['abilities'] = {'ability0': {'name': 'antimage_mana_break', 'level': 2}}
    session.ingest(first)
    now[0] += 10
    for items, abilities in (({'slot0': {}}, {'ability0': {'name': 'x'}}),
                             ({'team2': {'slot0': {}}}, {'team2': {'ability0': {}}})):
        update = payload()
        update['items'], update['abilities'] = items, abilities
        session.ingest(update)
        assert session.inventory == Counter(tango=1)
        assert session.learned == Counter(antimage_mana_break=2)
        assert session.field_status('inventory') == 'stale'
        assert session.field_status('skills') == 'stale'


def test_skills_keep_passives_and_talents_but_exclude_explicit_hidden_innates(now):
    session = Session()
    update = payload()
    update['abilities'] = {
        'ability0': {'name': 'antimage_mana_break', 'level': 2, 'ability_passive': True},
        'ability1': {'name': 'hidden', 'level': 2, 'hidden': True},
        'ability2': {'name': 'hidden_alias', 'level': 2, 'ability_hidden': True},
        'ability3': {'name': 'innate', 'level': 1, 'innate': True},
        'ability4': {'name': 'innate_alias', 'level': 1, 'is_innate': True},
        'ability5': {'name': 'special_bonus_test', 'level': 1},
        'ability6': {'name': 'not_learned', 'level': 0},
    }
    session.ingest(update)
    assert session.learned == Counter(antimage_mana_break=2, special_bonus_test=1)
    assert session.field_status('skills') == 'fresh'
    now[0] += 6
    session.ingest(payload())
    assert session.field_status('skills') == 'stale'
    route = SimpleNamespace(skills=['antimage_mana_break', 'antimage_mana_break',
                                    'special_bonus_test', 'antimage_blink'])
    assert session.next_skill(route)[0] == 'antimage_blink'
    update['abilities'] = {}
    session.ingest(update)
    assert not session.learned and session.field_status('skills') == 'fresh'


@pytest.mark.parametrize('invalid', [None, True, '123', 123.5])
def test_invalid_clock_does_not_reset_or_refresh_previous_clock(now, invalid):
    session = Session()
    session.ingest(payload(clock=100))
    session.completed.add(('bfury', 1))
    now[0] += 6
    session.ingest(payload(clock=invalid))
    assert session.clock == 100 and session.clock_at == 100
    assert session.field_status('clock') == 'stale'
    assert session.completed == {('bfury', 1)}


def test_no_clock_payload_allows_caller_to_use_manual_clock(now):
    session = Session()
    update = payload()
    del update['map']['clock_time']
    session.ingest(update)
    assert session.clock is None and session.clock_at is None
    assert session.field_status('clock') == 'missing'
    assert session.field_status('hero') == 'fresh'


def test_new_hero_and_explicit_reset_clear_all_field_data(now):
    session = Session()
    first = payload()
    first['items'] = {'slot0': {'name': 'item_tango', 'charges': 3}}
    first['abilities'] = {'ability0': {'name': 'antimage_mana_break', 'level': 2}}
    session.ingest(first)
    now[0] += 1
    update = payload(hero=2)
    del update['map']['clock_time']
    session.ingest(update)
    assert session.hero_id == 2 and session.field_status('hero') == 'fresh'
    assert not session.inventory and not session.inventory_charges and not session.learned
    for field in ('clock', 'inventory', 'charges', 'skills'):
        assert session.field_status(field) == 'missing'
    session.reset()
    assert session.last_gsi == 0 and session.hero_id == 2
    assert session.field_status('hero') == 'missing'


def test_freshness_handles_zero_monotonic_start_and_configured_age(now):
    now[0] = 0
    session = Session()
    session.ingest(payload())
    assert session.field_status('clock', now=5) == 'fresh'
    assert session.field_status('clock', now=5.01) == 'stale'
    assert session.field_status('clock', now=6, max_age=10) == 'fresh'
    with pytest.raises(ValueError):
        session.field_status('unknown')
