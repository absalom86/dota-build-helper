from dota_helper.recommendations import recommended_routes, ranked
from dota_helper.providers import Demo
from dota_helper.stratz import Stratz
from dota_helper.catalog import PATCHES
from dota_helper.ranking import patch_group


def sample(key,tournament=False,pro=False,premier=False):
    r=Demo().routes(1,1,0)[0][0]
    r.id=key
    r.demo=False
    r.tournament=tournament
    r.pro_player=pro
    r.evidence='TOURNAMENT PREMIER' if premier else ''
    return r


def test_combined_ranking_prefers_premier_then_pro_then_pub():
    ti=sample('ti',True,True,True)
    league=sample('league',True)
    pro=sample('pro',pro=True)
    pub=sample('pub')
    pub.start_time=9999999999
    assert [r.id for r in ranked([pub,pro,league,ti,ti])]==['ti','league','pro','pub']


def test_short_tournament_list_fills_from_ranked_with_shared_deadline(tmp_path,monkeypatch):
    ti=sample('ti',True,True,True)
    pro=sample('pro',pro=True)
    client=Stratz(tmp_path,token='test')
    deadlines=[]
    def tournaments(*args,**kwargs):
        deadlines.append(kwargs['deadline'])
        return [ti],'Tournament builds ready'
    def pubs(*args,**kwargs):
        deadlines.append(kwargs['deadline'])
        return [sample('pub'),pro],'Pub builds ready'
    monkeypatch.setattr('dota_helper.recommendations.tournament_routes',tournaments)
    monkeypatch.setattr(client,'routes',pubs)
    routes,status=recommended_routes(client,1,1)
    assert [r.id for r in routes]==['ti','pro','pub']
    assert 0<deadlines[1]-deadlines[0]<=3.01
    assert 'unavailable' not in status


def test_patch_confidence_precedes_source_preference_and_newness():
    current_pub=sample('current-pub')
    current_pub.patch=PATCHES[-1]['id']
    older_premier=sample('older-premier',True,True,True)
    older_premier.patch=PATCHES[-2]['id']
    older_premier.start_time=300
    unknown_pro=sample('unknown-pro',pro=True)
    unknown_pro.start_time=200
    unknown_pub=sample('unknown-pub')
    unknown_pub.start_time=400
    current_tournament=sample('current-tournament',True)
    current_tournament.patch=PATCHES[-1]['id']
    assert [r.id for r in ranked([older_premier,unknown_pub,current_pub,unknown_pro,current_tournament])] == [
        'current-tournament','current-pub','unknown-pro','unknown-pub','older-premier']
    newer_pub=sample('newer-current-pub')
    newer_pub.patch=PATCHES[-1]['id']
    newer_pub.start_time=100
    assert ranked([current_pub,newer_pub])[0] is newer_pub


def test_conflicting_or_unrecognized_patch_evidence_stays_unknown():
    route=sample('conflict',True,True,True)
    route.patch=PATCHES[-1]['id']
    route.warnings=['PATCH UNVERIFIED: conflicting source metadata']
    assert patch_group(route)==1
    route.warnings=[]
    route.patch_label=PATCHES[-2]['name']
    assert patch_group(route)==1
    route.patch_label=PATCHES[-1]['name']+'b'
    assert patch_group(route)==2
    route.patch=999999
    route.patch_label=''
    assert patch_group(route)==1


def test_full_older_tournament_list_still_discovers_current_pubs(tmp_path,monkeypatch):
    older=[sample(f'older-{i}',True,True,True) for i in range(10)]
    for route in older:
        route.patch=PATCHES[-2]['id']
    current=sample('current-pub')
    current.patch=PATCHES[-1]['id']
    client=Stratz(tmp_path,token='test')
    deadlines=[]
    monkeypatch.setattr('dota_helper.recommendations.tournament_routes',lambda *a,**kw:(older,'Tournament builds ready'))
    def pubs(*args,**kwargs):
        deadlines.append(kwargs['deadline'])
        assert kwargs['reference_ids']==[]
        return [current],'Pub builds ready'
    monkeypatch.setattr(client,'routes',pubs)
    updates=[]
    routes,status=recommended_routes(client,1,1,on_update=updates.append)
    assert len(deadlines)==1 and routes[0] is current and len(routes)==10
    assert updates[-1][0][0] is current
    assert 'verified current patch' in status and 'team strength is not ranked' in status
