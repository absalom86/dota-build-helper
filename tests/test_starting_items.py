import pytest

from dota_helper import starting_items
from dota_helper.models import Purchase
from dota_helper.providers import Demo

def test_verified_correction_is_match_and_hero_specific(tmp_path,monkeypatch):
    monkeypatch.setattr(starting_items,'user_data_dir',lambda:tmp_path)
    r=Demo().routes(1,1,0)[0][0]
    r.demo=False
    r.match_ids=[8946414154]
    r.hero_id=8
    assert starting_items.counts(r)['branches']==2
    r.hero_id=19
    assert starting_items.correction(r) is None

def test_saved_counts_survive_reload_and_do_not_mutate_purchase_log(tmp_path,monkeypatch):
    monkeypatch.setattr(starting_items,'user_data_dir',lambda:tmp_path)
    r=Demo().routes(1,1,0)[0][0]
    original=list(r.purchases)
    starting_items.save(r,{'branches':5,'tango':1})
    starting_items.load.cache_clear()
    assert starting_items.counts(r)=={'branches':5,'tango':1}
    assert r.purchases==original

def test_missing_branch_quantity_is_not_guessed_from_spare_inventory_space(tmp_path,monkeypatch):
    from dota_helper.builds import starting_buy_text
    monkeypatch.setattr(starting_items,'user_data_dir',lambda:tmp_path)
    r=Demo().routes(1,1,0)[0][0]
    r.demo=False
    r.match_ids=[123]
    r.source='STRATZ'
    r.purchases=[Purchase(k,-60) for k in ['branches','tango','magic_stick','quelling_blade','faerie_fire','ward_observer','ward_sentry']]
    original=list(r.purchases)
    assert starting_items.counts(r)['branches']==1
    assert starting_items.summary(r)['unverified']
    assert '(estimated)' not in starting_buy_text(r)
    assert '×1+' in starting_buy_text(r)
    assert r.purchases==original
    r.purchases.append(Purchase('circlet',-60))
    assert starting_items.counts(r)['branches']==1
    r.purchases.pop()
    starting_items.save(r,{'branches':1})
    assert starting_items.counts(r)['branches']==1
    assert not starting_items.summary(r)['unverified']


@pytest.mark.parametrize('branch_count,expected', [(2, {'magic_wand': 1}),
                                                  (3, {'magic_wand': 1, 'branches': 1})])
def test_starting_parts_combine_into_wand_and_preserve_spare_branches(
        tmp_path, monkeypatch, branch_count, expected):
    monkeypatch.setattr(starting_items, 'user_data_dir', lambda: tmp_path)
    r = Demo().routes(1, 1, 0)[0][0]
    r.purchases = [Purchase('branches', -60, index + 1) for index in range(branch_count)]
    r.purchases += [Purchase('magic_stick', -60), Purchase('recipe_magic_wand', -60)]
    original = [vars(p).copy() for p in r.purchases]
    assert starting_items.counts(r) == expected
    assert starting_items.recorded_counts(r) == {
        'branches': branch_count, 'magic_stick': 1, 'recipe_magic_wand': 1}
    assert 'Components combined' in starting_items.summary(r)['note']
    assert [vars(p) for p in r.purchases] == original


@pytest.mark.parametrize('keys', [
    ('branches', 'branches', 'magic_stick'),
    ('branches', 'magic_stick', 'recipe_magic_wand'),
    ('branches', 'branches', 'recipe_magic_wand'),
])
def test_incomplete_starting_recipe_remains_recorded_parts(tmp_path, monkeypatch, keys):
    monkeypatch.setattr(starting_items, 'user_data_dir', lambda: tmp_path)
    r = Demo().routes(1, 1, 0)[0][0]
    r.purchases = [Purchase(key, -60) for key in keys]
    assert starting_items.counts(r) == starting_items.recorded_counts(r)
    assert 'magic_wand' not in starting_items.counts(r)


def test_corrected_parts_also_combine_without_mutating_the_saved_override(tmp_path, monkeypatch):
    monkeypatch.setattr(starting_items, 'user_data_dir', lambda: tmp_path)
    r = Demo().routes(1, 1, 0)[0][0]
    saved = {'branches': 3, 'magic_stick': 1, 'recipe_magic_wand': 1}
    starting_items.save(r, saved)
    assert starting_items.counts(r) == {'magic_wand': 1, 'branches': 1}
    assert starting_items.correction(r) == saved
    assert starting_items.summary(r)['provenance'] == 'corrected'
