from dota_helper import starting_items
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

def test_branch_fallback_ignores_wards_and_respects_six_items_and_override(tmp_path,monkeypatch):
    from dota_helper.models import Purchase
    from dota_helper.builds import starting_buy_text
    monkeypatch.setattr(starting_items,'user_data_dir',lambda:tmp_path)
    r=Demo().routes(1,1,0)[0][0]
    r.demo=False
    r.match_ids=[123]
    r.source='STRATZ'
    r.purchases=[Purchase(k,-60) for k in ['branches','tango','magic_stick','quelling_blade','faerie_fire','ward_observer','ward_sentry']]
    original=list(r.purchases)
    assert starting_items.counts(r)['branches']==2
    assert '(estimated)' in starting_buy_text(r)
    assert r.purchases==original
    r.purchases.append(Purchase('circlet',-60))
    assert starting_items.counts(r)['branches']==1
    r.purchases.pop()
    starting_items.save(r,{'branches':1})
    assert starting_items.counts(r)['branches']==1
    assert not starting_items.estimated_branches(r)
