from types import SimpleNamespace

import pytest

from dota_helper.builds import overlay_sections
from dota_helper.models import Purchase


def route_with(*purchases):
    return SimpleNamespace(purchases=list(purchases))


@pytest.mark.parametrize('second,components,supplies', [
    (None, ['circlet'], ['flask', 'infused_raindrop']),
    (-30, ['circlet'], ['flask', 'infused_raindrop']),
    (0, ['circlet'], ['flask', 'infused_raindrop']),
    (299, ['circlet'], ['flask', 'infused_raindrop']),
    (300, [], ['flask', 'infused_raindrop']),
    (599, [], ['flask', 'infused_raindrop']),
    (600, [], []),
    (1800, [], []),
])
def test_sections_expire_independently_and_keep_full_build(second, components, supplies):
    route = route_with(
        Purchase('tango', -60), Purchase('boots', 0), Purchase('flask', 299),
        Purchase('circlet', 299), Purchase('gauntlets', 300),
        Purchase('infused_raindrop', 599), Purchase('clarity', 600),
        Purchase('black_king_bar', 1500),
    )
    sections = overlay_sections(route, second)
    assert [p.key for p in sections['items']] == ['boots', 'black_king_bar']
    assert [p.key for p in sections['components']] == components
    assert [p.key for p in sections['supplies']] == supplies


def test_supplies_are_explicit_and_never_duplicate_other_sections():
    keys = ['tango', 'flask', 'clarity', 'enchanted_mango', 'faerie_fire',
            'infused_raindrop', 'blood_grenade']
    route = route_with(*(Purchase(key, 120) for key in keys),
                       Purchase('magic_stick', 150), Purchase('magic_wand', 600))
    sections = overlay_sections(route, 0)
    assert [p.key for p in sections['supplies']] == keys
    assert [p.key for p in sections['items']] == ['magic_stick', 'magic_wand']
    assert sections['components'] == []


def test_wards_utility_recipes_late_parts_and_unknown_items_stay_out():
    excluded = ['ward_observer', 'ward_sentry', 'ward_dispenser', 'tpscroll',
                'smoke_of_deceit', 'dust', 'recipe_manta', 'unknown_item']
    route = route_with(*(Purchase(key, 120) for key in excluded),
                       Purchase('recipe_manta', 800), Purchase('ogre_axe', 900),
                       Purchase('black_king_bar', 1200))
    sections = overlay_sections(route, 0)
    assert [p.key for p in sections['items']] == ['black_king_bar']
    assert sections['components'] == []
    assert sections['supplies'] == []


def test_supply_duration_controls_purchase_window_and_visibility_only():
    route = route_with(Purchase('circlet', 0), Purchase('flask', 299),
                       Purchase('clarity', 300), Purchase('tango', 899),
                       Purchase('faerie_fire', 900), Purchase('manta', 1200))
    assert [p.key for p in overlay_sections(route, 299, 5)['supplies']] == ['flask']
    assert overlay_sections(route, 300, 5)['supplies'] == []
    assert [p.key for p in overlay_sections(route, 899, 15)['supplies']] == ['flask', 'clarity', 'tango']
    assert overlay_sections(route, 900, 15)['supplies'] == []
    disabled = overlay_sections(route, 0, 0)
    assert disabled['supplies'] == []
    assert [p.key for p in disabled['components']] == ['circlet']
    assert [p.key for p in disabled['items']] == ['manta']


def test_repeated_events_keep_their_quantities_timings_and_identity():
    initial = Purchase('flask', -60)
    first = Purchase('flask', 301, 2)
    second = Purchase('flask', 301, 3)
    route = route_with(initial, first, second, Purchase('manta', 1200))
    original = [vars(p).copy() for p in route.purchases]
    sections = overlay_sections(route, 301)
    assert sections['supplies'] == [first, second]
    assert sections['supplies'][0] is first and sections['supplies'][1] is second
    assert [vars(p) for p in route.purchases] == original
