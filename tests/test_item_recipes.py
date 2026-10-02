from collections import Counter

import pytest

from dota_helper import item_recipes


def test_wand_retains_both_branches_and_paid_recipe():
    assert item_recipes.component_counts('magic_wand') == Counter(
        magic_stick=1, branches=2, recipe_magic_wand=1)
    assert item_recipes.expanded_counts({'magic_wand': 2}) == Counter(
        magic_stick=2, branches=4, recipe_magic_wand=2)


@pytest.mark.parametrize('counts', [
    {'magic_stick': 1, 'branches': 1, 'recipe_magic_wand': 1},
    {'magic_stick': 1, 'branches': 2},
    {'branches': 2, 'recipe_magic_wand': 1},
])
def test_wand_requires_every_component(counts):
    assert item_recipes.assemble_counts(counts) == counts


def test_assembly_preserves_extra_branches_and_existing_wands():
    inventory = {'magic_wand': 1, 'magic_stick': 1, 'branches': 5, 'recipe_magic_wand': 1}
    assert item_recipes.assemble_counts(inventory) == Counter(magic_wand=2, branches=3)
    assert inventory['branches'] == 5


def test_multiple_wands_consume_two_branches_apiece():
    assert item_recipes.assemble_counts({
        'magic_stick': 2, 'branches': 5, 'recipe_magic_wand': 2,
    }) == Counter(magic_wand=2, branches=1)


def test_nested_recipe_expansion_and_assembly():
    leaves = Counter(magic_stick=1, branches=2, recipe_magic_wand=1,
                     crown=1, recipe_holy_locket=1)
    assert item_recipes.expanded_counts({'holy_locket': 1}) == leaves
    assert item_recipes.expanded_counts({'holy_locket': 1}, include_roots=True) == (
        leaves + Counter(holy_locket=1, magic_wand=1))
    assert item_recipes.assemble_counts(leaves) == Counter(holy_locket=1)


def test_upgrade_reuses_explicit_recipe_without_inventing_another():
    assert item_recipes.component_counts('travel_boots_2') == Counter(
        travel_boots=1, recipe_travel_boots=1)
    assert item_recipes.expanded_counts({'travel_boots_2': 1}) == Counter(
        boots=1, recipe_travel_boots=2)


def test_consumables_charges_and_unknown_items_stay_as_supplied():
    counts = Counter(tango=2, ward_dispenser=1, unrecognized_item=3)
    assert item_recipes.expanded_counts(counts) == counts
    assert item_recipes.assemble_counts(counts) == counts
    assert item_recipes.component_counts('ward_dispenser') == Counter()
    assert item_recipes.component_counts('unrecognized_item') == Counter()


def test_alternate_attribute_parts_do_not_become_exact_evidence():
    assert item_recipes.component_counts('power_treads') == Counter()
    assert item_recipes.expanded_counts({'power_treads': 1}) == {'power_treads': 1}


@pytest.mark.parametrize('parts,cost,recipe_cost', [
    (['part'], 120, None),  # Missing recipe information.
    (['part'], 120, 25),  # Stale/mismatching scroll cost.
    (['part'], 100, 25),  # Never silently omit a known paid recipe.
    (['missing'], 100, None),
    (['part', ''], 100, None),
    ([['part', 'alternative']], 100, None),
])
def test_uncertain_catalog_recipes_are_not_used(monkeypatch, parts, cost, recipe_cost):
    catalog = {'item': {'cost': cost, 'components': parts}, 'part': {'cost': 100}}
    if recipe_cost is not None:
        catalog['recipe_item'] = {'cost': recipe_cost}
    monkeypatch.setattr(item_recipes, 'ITEMS', catalog)
    assert item_recipes.component_counts('item') == Counter()
    assert item_recipes.expanded_counts({'item': 1}) == {'item': 1}


def test_cycles_are_rejected_without_recursing_forever(monkeypatch):
    monkeypatch.setattr(item_recipes, 'ITEMS', {
        'one': {'cost': 100, 'components': ['two']},
        'two': {'cost': 100, 'components': ['one']},
        'self': {'cost': 100, 'components': ['self']},
    })
    counts = {'one': 1, 'two': 1, 'self': 1}
    for key in counts:
        assert item_recipes.component_counts(key) == Counter()
    assert item_recipes.expanded_counts(counts, include_roots=True) == counts
    assert item_recipes.assemble_counts(counts) == counts


def test_competing_assemblies_do_not_choose_a_build(monkeypatch):
    monkeypatch.setattr(item_recipes, 'ITEMS', {
        'left': {'cost': 200, 'components': ['part', 'left_part']},
        'right': {'cost': 200, 'components': ['part', 'right_part']},
        'part': {'cost': 100}, 'left_part': {'cost': 100}, 'right_part': {'cost': 100},
    })
    counts = {'part': 1, 'left_part': 1, 'right_part': 1}
    assert item_recipes.assemble_counts(counts) == counts
    assert item_recipes.assemble_counts({**counts, 'part': 2}) == {'left': 1, 'right': 1}


def test_nonpositive_or_charge_metadata_values_are_not_inventory_units():
    counts = {'branches': 2, 'tango': 0, 'magic_stick': -1, 'charges': True, 'unknown': '3'}
    assert item_recipes.expanded_counts(counts) == {'branches': 2}
    assert item_recipes.assemble_counts(counts) == {'branches': 2}
