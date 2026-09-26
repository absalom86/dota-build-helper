from dota_helper.recommendations import recommended_routes, ranked
from dota_helper.providers import Demo
from dota_helper.stratz import Stratz
from dota_helper.catalog import PATCHES
from dota_helper.ranking import build_signature, patch_group
from zlib import crc32
import time

NOW = int(time.time())


def sample(key,tournament=False,pro=False,premier=False):
    r=Demo().routes(1,1,0)[0][0]
    r.id=key
    r.match_ids=[crc32(key.encode()) + 1]
    r.demo=False
    r.start_time=NOW - 86400
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


def test_pub_mmr_numeric_descending_unknown_last_and_recency_breaks_ties():
    rows = [sample(name) for name in ('unknown', 'low', 'high-old', 'high-new')]
    for route, mmr, date in zip(rows, (None, 9500, 11200, 11200), (999, 800, 100, 200)):
        route.average_mmr, route.start_time = mmr, date
    pro = sample('pro', pro=True)
    assert [r.id for r in ranked(rows + [pro])] == ['pro', 'high-new', 'high-old', 'low', 'unknown']
    # Patch differences no longer override match rating.
    rows[0].patch = PATCHES[-1]['id']
    rows[2].patch = PATCHES[-2]['id']
    assert ranked([rows[2], rows[0]])[0] is rows[2]


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


def test_recent_games_across_patches_prefer_premier_then_pro_then_rating():
    current_pub=sample('current-pub')
    current_pub.patch=PATCHES[-1]['id']
    older_premier=sample('older-premier',True,True,True)
    older_premier.patch=PATCHES[-2]['id']
    older_premier.start_time=NOW - 60 * 86400
    unknown_pro=sample('unknown-pro',pro=True)
    unknown_pro.start_time=NOW - 20 * 86400
    unknown_pub=sample('unknown-pub')
    unknown_pub.start_time=NOW - 10 * 86400
    current_tournament=sample('current-tournament',True)
    current_tournament.patch=PATCHES[-1]['id']
    assert [r.id for r in ranked([older_premier,unknown_pub,current_pub,unknown_pro,current_tournament])] == [
        'older-premier','current-tournament','unknown-pro','current-pub','unknown-pub']
    newer_pub=sample('newer-current-pub')
    newer_pub.patch=PATCHES[-1]['id']
    newer_pub.start_time=NOW - 100
    assert ranked([current_pub,newer_pub])[0] is newer_pub


def test_recent_window_precedes_archived_games_without_a_patch_requirement():
    recent = sample('recent')
    recent.start_time = NOW - 89 * 86400
    recent.patch = PATCHES[-2]['id']
    archived = sample('archived', True, True, True)
    archived.start_time = NOW - 91 * 86400
    archived.patch = PATCHES[-1]['id']
    assert ranked([archived, recent]) == [recent, archived]


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
    assert len(deadlines)==1 and routes == older + [current]
    assert updates[-1][0] == routes
    assert '90 days across patches' in status and 'team strength is not ranked' in status


def test_ranking_keeps_all_games_unless_consumer_requests_explicit_limit():
    rows = [sample(f'pub-{i}') for i in range(20)]
    for i, route in enumerate(rows):
        route.average_mmr = 8000 + i * 100
    pro = sample('pro', pro=True)
    ordered = ranked(rows + [pro, rows[0]])
    assert len(ordered) == 21
    assert ordered[0] is pro
    assert [r.average_mmr for r in ordered[1:]] == list(range(9900, 7900, -100))
    assert ranked(rows + [pro], limit=3) == ordered[:3]


def test_build_signature_ignores_malformed_legacy_final_inventory():
    route = sample('cached')
    route.final_items = []
    expected = build_signature(route)
    for value in (None, 'bfury', {'key':'bfury'}, ['bfury', {}], ['bfury', 2]):
        route.final_items = value
        assert build_signature(route) == expected
        assert len({build_signature(route)}) == 1


def test_stream_retains_cached_tournaments_after_ten_current_pubs(tmp_path, monkeypatch):
    tournaments = [sample('unknown-tournament', True), sample('older-tournament', True)]
    tournaments[1].patch = PATCHES[-2]['id']
    pubs = [sample(f'pub-{i}') for i in range(10)]
    for i, route in enumerate(pubs):
        route.patch = PATCHES[-1]['id']
        route.average_mmr = 8000 + i * 100
    client = Stratz(tmp_path, token='test')
    def tournament_lookup(*args, **kwargs):
        args[5]((tournaments, 'Cached tournament builds'))
        return tournaments, 'Tournament builds'
    def pub_lookup(*args, **kwargs):
        args[4]((pubs[:4], 'First pubs'))
        args[4]((pubs, 'All pubs'))
        return pubs, 'Pub builds'
    monkeypatch.setattr('dota_helper.recommendations.tournament_routes', tournament_lookup)
    monkeypatch.setattr(client, 'routes', pub_lookup)
    updates = []
    routes, _ = recommended_routes(client, 1, 1, on_update=updates.append)
    assert len(routes) == 12
    assert routes[:2] == tournaments
    assert routes[2].average_mmr == 8900
    for update, _ in updates:
        assert {r.id for r in tournaments}.issubset({r.id for r in update})
