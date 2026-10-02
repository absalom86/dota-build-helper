from copy import deepcopy
import hashlib
import json
import time

import pytest

from dota_helper import quantity_evidence, starting_items
from dota_helper.models import Purchase, Route


@pytest.fixture
def route(tmp_path, monkeypatch):
    monkeypatch.setattr(starting_items, 'user_data_dir', lambda: tmp_path)
    monkeypatch.setattr(quantity_evidence, 'user_data_dir', lambda: tmp_path)
    starting_items.load.cache_clear()
    quantity_evidence._load.cache_clear()
    value = Route('stratz:100:0', 145, 1, 1, 0, 'Starting-buy example',
                  [Purchase('branches', -89), Purchase('tango', -89), Purchase('manta', 1200)],
                  [], [100], 0, '', 'Example', source='STRATZ', account_id=12345, player_slot=0)
    yield value
    starting_items.load.cache_clear()
    quantity_evidence._load.cache_clear()


def compare(route, counts, *, events=None, force=True):
    class Client:
        def get(self, path, **kwargs):
            assert path == 'matches/100'
            return {'match_id': 100, 'players': [{
                'hero_id': route.hero_id, 'account_id': route.account_id,
                'player_slot': route.player_slot,
                'purchase_log': (events if events is not None else
                                 [{'key': key, 'time': -89}
                                  for key, count in counts.items() for _ in range(count)])
                                + [{'key': 'branches', 'time': 0}],
            }]}
    return quantity_evidence.verify_selected(route, Client(), force=force)


def set_pregame(route, keys):
    route.purchases = [Purchase(key, -89) for key in keys] + [Purchase('manta', 1200)]


def test_five_starting_branches_are_recovered_from_exact_player_cache(route):
    set_pregame(route, ['branches', 'ward_observer', 'tango'])
    original = deepcopy(route.purchases)
    result = compare(route, {'branches': 5, 'ward_observer': 1, 'tango': 1})
    assert result['status'] == 'conflict'
    assert quantity_evidence.recoverable_counts(route) == {
        'branches': 5, 'ward_observer': 1, 'tango': 1}
    assert quantity_evidence.recoverable_counts(route, result) == result['counts']
    assert route.purchases == original
    assert starting_items.correction(route) is None


def test_watson_kez_start_recovers_two_branches(route):
    set_pregame(route, ['quelling_blade', 'branches', 'magic_stick', 'faerie_fire', 'tango'])
    compare(route, {'quelling_blade': 1, 'tango': 1, 'branches': 2,
                    'magic_stick': 1, 'faerie_fire': 1})
    assert quantity_evidence.recoverable_counts(route) == {
        'quelling_blade': 1, 'tango': 1, 'branches': 2, 'magic_stick': 1, 'faerie_fire': 1}


def test_wand_is_same_recipe_with_recovered_branch_and_faerie_quantities(route):
    set_pregame(route, ['magic_stick', 'branches', 'recipe_magic_wand', 'faerie_fire'])
    result = compare(route, {'magic_wand': 1, 'faerie_fire': 2})
    assert quantity_evidence.recoverable_counts(route) == {'magic_wand': 1, 'faerie_fire': 2}
    # Keep the raw evidence available even when its component representation differs.
    assert result['differences']['branches'] == {'recorded': 1, 'opendota': 0}
    assert result['differences']['magic_wand'] == {'recorded': 0, 'opendota': 1}


def test_equal_component_log_assembles_without_inventing_additional_branches(route):
    set_pregame(route, ['magic_stick', 'branches', 'branches', 'recipe_magic_wand'])
    result = compare(route, {'magic_stick': 1, 'branches': 2, 'recipe_magic_wand': 1})
    assert result['status'] == 'verified'
    assert quantity_evidence.recoverable_counts(route) == {'magic_wand': 1}


def test_quantities_are_not_special_cased_to_branches_or_consumable_charges(route):
    set_pregame(route, ['circlet', 'branches', 'tango', 'faerie_fire'])
    compare(route, {'circlet': 2, 'branches': 2, 'tango': 2, 'faerie_fire': 2})
    assert quantity_evidence.recoverable_counts(route) == {
        'circlet': 2, 'branches': 2, 'tango': 2, 'faerie_fire': 2}


def test_stacked_tangos_and_mangoes_are_recovered_as_packs_and_items(route):
    set_pregame(route, ['tango', 'enchanted_mango'])
    result = compare(route, {}, events=[{'key': 'tango', 'time': -89, 'charges': 6},
                                       {'key': 'enchanted_mango', 'time': -89, 'charges': 2}])
    assert result['counts'] == {'tango': 2, 'enchanted_mango': 2}
    assert quantity_evidence.recoverable_counts(route) == result['counts']


def test_partial_tango_stack_requires_review_instead_of_rounding(route):
    result = compare(route, {}, events=[{'key': 'tango', 'time': -89, 'charges': 4}])
    assert result['status'] == 'unavailable'
    assert quantity_evidence.recoverable_counts(route) is None


def test_verified_one_branch_remains_one(route):
    compare(route, {'branches': 1, 'tango': 1})
    assert quantity_evidence.recoverable_counts(route) == {'branches': 1, 'tango': 1}


@pytest.mark.parametrize('counts', [
    {'branches': 2},
    {'branches': 2, 'tango': 1, 'ward_sentry': 1},
    {'magic_wand': 1, 'tango': 1},
    {'branches': 31, 'tango': 1},
])
def test_different_or_implausible_starting_composition_stays_for_review(route, counts):
    compare(route, counts)
    assert quantity_evidence.recoverable_counts(route) is None


def test_fewer_branches_stays_for_review(route):
    set_pregame(route, ['branches', 'branches', 'tango'])
    compare(route, {'branches': 1, 'tango': 1})
    assert quantity_evidence.recoverable_counts(route) is None


def test_missing_recipe_cannot_be_treated_as_a_completed_wand(route):
    set_pregame(route, ['magic_stick', 'branches'])
    compare(route, {'magic_wand': 1})
    assert quantity_evidence.recoverable_counts(route) is None


@pytest.mark.parametrize('field,value', [
    ('account_id', 99999), ('player_slot', 128), ('match_id', 101), ('hero_id', 8),
    ('matched_by', ''), ('source', 'Unknown'), ('checked_at', float('nan')),
    ('checked_at', float('inf')), ('checked_at', True),
    ('checked_at', time.time() - quantity_evidence.SUCCESS_TTL - 60),
    ('checked_at', time.time() + 600), ('recorded_counts', {'branches': 99}),
    ('counts', {'branches': True, 'tango': 1}), ('differences', {}),
    ('status', 'unavailable'),
])
def test_supplied_results_cannot_bypass_identity_schema_or_freshness(route, field, value):
    result = compare(route, {'branches': 5, 'tango': 1})
    result[field] = value
    assert quantity_evidence.recoverable_counts(route, result) is None


def test_unknown_item_cache_cannot_supply_recommendations(route):
    result = compare(route, {'branches': 5, 'tango': 1})
    route.purchases.insert(0, Purchase('unknown_item', -89))
    result['recorded_counts']['unknown_item'] = 1
    result['counts']['unknown_item'] = 1
    assert quantity_evidence.recoverable_counts(route, result) is None


def test_anonymous_exact_slot_can_recover_without_an_account_guess(route):
    route.account_id = None
    result = compare(route, {'branches': 5, 'tango': 1})
    assert result['matched_by'] == 'player_slot'
    assert quantity_evidence.recoverable_counts(route) == {'branches': 5, 'tango': 1}
    result['matched_by'] = 'account_id'
    assert quantity_evidence.recoverable_counts(route, result) is None


def test_route_change_invalidates_cached_recovery_and_leaves_evidence_intact(route):
    compare(route, {'branches': 5, 'tango': 1})
    recovered = quantity_evidence.recoverable_counts(route)
    recovered['branches'] = 99
    assert quantity_evidence.recoverable_counts(route)['branches'] == 5
    route.purchases.append(Purchase('flask', -30))
    assert quantity_evidence.recoverable_counts(route) is None


@pytest.mark.parametrize('field,value', [('source', 'OpenDota'), ('demo', True),
                                         ('match_ids', [100, 101]), ('account_id', 99999)])
def test_unrelated_or_aggregate_routes_do_not_reuse_recovery(route, field, value):
    compare(route, {'branches': 5, 'tango': 1})
    setattr(route, field, value)
    assert quantity_evidence.recoverable_counts(route) is None


def test_legacy_comparison_is_recounted_from_exact_player_raw_cache(route, tmp_path):
    result = compare(route, {'branches': 5, 'tango': 1})
    result.pop('quantity_version')
    quantity_evidence._save(result)
    assert quantity_evidence.get_saved(route) is not None
    assert quantity_evidence.recoverable_counts(route) is None
    cache_dir = tmp_path / 'cache'
    cache_dir.mkdir()
    cache_key = hashlib.sha256(b'matches/100{}').hexdigest()
    raw = {'data': {'match_id': 100, 'players': [{
        'account_id': 12345, 'player_slot': 0, 'hero_id': 145,
        'purchase_log': [{'key': 'branches', 'time': -89}] * 5
                        + [{'key': 'tango', 'time': -89, 'charges': 6}],
    }]}}
    raw_path = cache_dir / f'{cache_key}.json'
    raw_path.write_text(json.dumps(raw), encoding='utf-8')
    saved_before = (tmp_path / 'quantity-evidence.json').read_bytes()
    assert quantity_evidence.recoverable_counts(route) == {'branches': 5, 'tango': 2}
    assert (tmp_path / 'quantity-evidence.json').read_bytes() == saved_before
    # A changed player in the underlying raw cache cannot hydrate legacy evidence.
    raw['data']['players'][0]['account_id'] = 99999
    raw_path.write_text(json.dumps(raw), encoding='utf-8')
    assert quantity_evidence.recoverable_counts(route) is None


def test_legacy_success_without_raw_cache_does_not_block_a_new_quantity_check(route):
    result = compare(route, {'branches': 1, 'tango': 1})
    result.pop('quantity_version')
    quantity_evidence._save(result)
    assert quantity_evidence.recoverable_counts(route) is None
    result = compare(route, {'branches': 5, 'tango': 1}, force=False)
    assert result['quantity_version'] == quantity_evidence.QUANTITY_VERSION
    assert result['counts']['branches'] == 5
    assert not result['cached']
