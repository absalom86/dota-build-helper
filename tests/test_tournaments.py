import json
import time
from dataclasses import asdict
import pytest
from dota_helper.tournaments import tournament_routes, tournament_index as REAL_INDEX
from dota_helper.stratz import Stratz, normalize_stratz
from dota_helper.providers import DataError
from test_stratz import match
from dota_helper.catalog import ITEMS, PATCHES


@pytest.fixture(autouse=True)
def no_live_index(monkeypatch):
    monkeypatch.setattr('dota_helper.tournaments.tournament_index',lambda *a:[])


def test_missing_stratz_league_is_discovered_and_role_checked(tmp_path,monkeypatch):
    good=match(42)
    good.update(lobbyType='PRACTICE',leagueId=19719,league=None)
    wrong=match(43)
    wrong.update(lobbyType='PRACTICE',leagueId=19719)
    wrong['players'][0]['position']='POSITION_4'
    monkeypatch.setattr('dota_helper.tournaments.tournament_index',lambda *a:[
        dict(match_id=n,leagueid=19719,account_id=42,tier='premium',name='The International 2026') for n in (42,43)])
    client=Stratz(tmp_path,token='test')
    def query(q,variables=None):
        assert 'leagues(' not in q
        if 'itemPurchases' in q:
            return {'m0':good,'m1':wrong}
        return {'constants':{'gameVersions':[]}}
    monkeypatch.setattr(client,'query',query)
    routes,status=tournament_routes(client,1,1,reference_ids=[])
    assert [r.match_ids[0] for r in routes]==[42]
    assert 'PREMIER' in routes[0].evidence
    assert 'OpenDota match index' in status


def test_index_prioritizes_premier_and_excludes_amateur(tmp_path,monkeypatch):
    # Retrieve the real function despite the per-test network guard.
    import importlib
    module=importlib.import_module('dota_helper.tournaments')
    monkeypatch.setattr(module.OpenDota,'get',lambda *a,**kw:{'rows':[
        dict(match_id=1,tier='professional',start_time=300),
        dict(match_id=2,tier='premium',start_time=100),
        dict(match_id=3,tier='premium',start_time=200),
        dict(match_id=4,tier='amateur',start_time=400)]})
    import threading
    assert [r['match_id'] for r in REAL_INDEX(Stratz(tmp_path,token='test'),83,0,threading.Event())]==[3,2,1]




def test_tournament_default_never_recommends_pub_even_pro_player(tmp_path,monkeypatch):
    client=Stratz(tmp_path,token='test')
    pub=match(1)
    tourney=match(2)
    tourney.update(lobbyType='PRACTICE',leagueId=123,rank=64)
    tourney['players'][0]['steamAccount']['seasonRank']=64
    def query(q,variables=None):
        if 'leagues(request' in q:
            assert 'skip:0' in q
            return {'constants':{'gameVersions':[]},'m0':pub,'leagues':[
                {'id':123,'tier':'PROFESSIONAL','matches':[pub,tourney]}]}
        return {'m0':tourney}
    monkeypatch.setattr(client,'query',query)
    routes,status=tournament_routes(client,1,1,reference_ids=[1])
    assert len(routes)==1 and routes[0].match_ids==[2] and routes[0].tournament
    assert 'ranked pubs excluded' in status


def test_empty_tournaments_do_not_use_ranked_guide_fallback(tmp_path,monkeypatch):
    client=Stratz(tmp_path,token='test')
    monkeypatch.setattr(client,'query',lambda *a,**kw:{'leagues':[]})
    routes,status=tournament_routes(client,1,1,reference_ids=[])
    assert routes==[] and 'No usable tournament' in status


def test_tournament_discovery_continues_past_ten_in_bounded_batches(tmp_path, monkeypatch):
    import re
    from dota_helper.endgame import six_slot_items
    from test_endgame import FINAL
    client = Stratz(tmp_path, token='test')
    games = {}
    for mid in range(1, 31):
        m = match(mid)
        m.update(lobbyType='PRACTICE', leagueId=123)
        m['players'][0]['stats']['itemPurchases'] += [
            {'time':900+j, 'itemId':ITEMS['branches']['id']} for j in range(mid)]
        games[mid] = m
    games[15]['players'][0].update({f'item{i}Id':ITEMS[key]['id'] for i,key in enumerate(FINAL)})
    monkeypatch.setattr('dota_helper.tournaments.tournament_index', lambda *a:[
        dict(match_id=mid, leagueid=123, account_id=42, tier='premium', name='Recorded event') for mid in games])
    calls = []
    def query(q, variables=None):
        if 'itemPurchases' not in q:
            return {'constants':{'gameVersions':[{'id':182,'name':PATCHES[-1]['name']}]}}
        ids = [int(n) for n in re.findall(r'match\(id:(\d+)\)', q)]
        calls.append(ids)
        return {f'm{i}':games[mid] for i,mid in enumerate(ids)}
    monkeypatch.setattr(client, 'query', query)
    routes, status = tournament_routes(client, 1, 1, reference_ids=[])
    assert len(routes) == 30 and calls == [list(range(1, 11)), list(range(11, 21)), list(range(21, 31))]
    assert any(six_slot_items(r) for r in routes)


def test_rate_limit_retains_only_matching_cached_tournaments(tmp_path,monkeypatch):
    m=match(2)
    m.update(lobbyType='PRACTICE',leagueId=123)
    route=normalize_stratz(m,m['players'][0],{})
    pub=normalize_stratz(match(3),match(3)['players'][0],{})
    (tmp_path/'tournaments-v1-1-1.json').write_text(json.dumps({'routes':[asdict(route),asdict(pub)]}))
    client=Stratz(tmp_path,token='test')
    monkeypatch.setattr(client,'query',lambda *a,**kw:(_ for _ in ()).throw(DataError('STRATZ HTTP 429')))
    routes,status=tournament_routes(client,1,1,reference_ids=[])
    assert [r.match_ids[0] for r in routes]==[2]
    assert 'Cached tournament' in status and '429' in status


def test_tournament_cache_prefers_premier_status_across_patches(tmp_path,monkeypatch):
    current_match,unknown_match=match(1),match(2)
    for m in (current_match,unknown_match):
        m.update(lobbyType='PRACTICE',leagueId=123)
    current=normalize_stratz(current_match,current_match['players'][0],{182:PATCHES[-1]['name']})
    unknown=normalize_stratz(unknown_match,unknown_match['players'][0],{})
    unknown.evidence='TOURNAMENT PREMIER'
    (tmp_path/'tournaments-v1-1-1.json').write_text(json.dumps({'routes':[asdict(unknown),asdict(current)]}))
    client=Stratz(tmp_path,token='test')
    monkeypatch.setattr(client,'query',lambda *a,**kw:(_ for _ in ()).throw(DataError('STRATZ HTTP 429')))
    updates=[]
    routes,status=tournament_routes(client,1,1,reference_ids=[],on_update=updates.append)
    assert [r.match_ids[0] for r in routes]==[2,1]
    assert [r.match_ids[0] for r in updates[0][0]]==[2,1]


def test_tournament_discovery_keeps_games_across_patches_after_ten_results(tmp_path,monkeypatch):
    client=Stratz(tmp_path,token='test')
    games={}
    for mid in range(1,12):
        m=match(mid)
        m.update(lobbyType='PRACTICE',leagueId=123,gameVersionId=183 if mid==11 else 182,
                 startDateTime=int(time.time())-mid*86400)
        m['players'][0]['stats']['itemPurchases'] += [{'time':900+j,'itemId':ITEMS['branches']['id']} for j in range(mid)]
        games[mid]=m
    monkeypatch.setattr('dota_helper.tournaments.tournament_index',lambda *a:[
        dict(match_id=mid,leagueid=123,account_id=42,tier='premium',name='Recorded event') for mid in games])
    requested=[]
    def query(q,variables=None):
        if 'itemPurchases' not in q:
            return {'constants':{'gameVersions':[{'id':182,'name':'7.40b'},{'id':183,'name':PATCHES[-1]['name']}]}}
        import re
        ids=[int(n) for n in re.findall(r'match\(id:(\d+)\)',q)]
        requested.extend(ids)
        return {f'm{i}':games[mid] for i,mid in enumerate(ids)}
    monkeypatch.setattr(client,'query',query)
    routes,status=tournament_routes(client,1,1,reference_ids=[])
    assert requested==list(range(1,12))
    assert len(routes)==11 and [r.match_ids[0] for r in routes]==list(range(1,12))


def test_tournament_window_includes_sixty_days_rejects_ninety_one_and_queries_cutoff(tmp_path,monkeypatch):
    recent,expired=match(60),match(91)
    for days,m in ((60,recent),(91,expired)):
        m.update(lobbyType='PRACTICE',leagueId=123,startDateTime=int(time.time())-days*86400)
    index_since=[]
    def index(client,hero,since,cancel):
        index_since.append(since)
        return []
    monkeypatch.setattr('dota_helper.tournaments.tournament_index',index)
    client=Stratz(tmp_path,token='test')
    def query(q,variables=None):
        if 'leagues(request' in q:
            assert f'startDateTime:{index_since[0]}' in q
            return {'constants':{'gameVersions':[{'id':182,'name':'7.40b'}]},
                    'leagues':[{'id':123,'tier':'PROFESSIONAL','matches':[recent,expired]}]}
        assert 'match(id:91)' not in q
        return {'m0':recent}
    monkeypatch.setattr(client,'query',query)
    routes,_=tournament_routes(client,1,1,reference_ids=[])
    assert 0<=time.time()-90*86400-index_since[0]<3601
    assert index_since[0]%3600==0
    assert [r.match_ids for r in routes]==[[60]]
    assert routes[0].patch_label=='7.40b'
    assert not any('OLDER EXAMPLE' in w or 'PATCH UNVERIFIED' in w for w in routes[0].warnings)


def test_tournament_snapshot_uses_ninety_days_not_patch_boundary(tmp_path,monkeypatch):
    saved=[]
    for days in (60,91):
        m=match(days)
        m.update(lobbyType='PRACTICE',leagueId=123,startDateTime=int(time.time())-days*86400)
        saved.append(asdict(normalize_stratz(m,m['players'][0],{182:'7.40b'})))
    (tmp_path/'tournaments-v1-1-1.json').write_text(json.dumps({'routes':saved}))
    client=Stratz(tmp_path,token='test')
    monkeypatch.setattr(client,'query',lambda *a,**kw:(_ for _ in ()).throw(DataError('STRATZ HTTP 429')))
    routes,_=tournament_routes(client,1,1,reference_ids=[])
    assert [r.match_ids for r in routes]==[[60]]


def test_tournament_refresh_keeps_cache_and_separate_identical_build_games(tmp_path, monkeypatch):
    import re
    client = Stratz(tmp_path, token='test')
    cached_game = match(100)
    cached_game.update(lobbyType='PRACTICE', leagueId=123)
    cached = normalize_stratz(cached_game, cached_game['players'][0], {})
    wrong_hero = asdict(cached)
    wrong_hero.update(id='wrong-hero', hero_id=2, match_ids=[101])
    wrong_role = asdict(cached)
    wrong_role.update(id='wrong-role', role=4, match_ids=[102])
    pub = asdict(cached)
    pub.update(id='pub', tournament=False, match_ids=[103])
    snapshot = tmp_path / 'tournaments-v1-1-1.json'
    snapshot.write_text(json.dumps({'routes':[asdict(cached), wrong_hero, wrong_role, pub]}))
    games = {}
    for mid in range(1, 12):
        game = match(mid)
        game.update(lobbyType='PRACTICE', leagueId=123)
        # IDs 1 and 2 deliberately follow the same build; both remain selectable.
        game['players'][0]['stats']['itemPurchases'] += [
            {'time':900+j, 'itemId':ITEMS['branches']['id']} for j in range(max(0, mid-2))]
        games[mid] = game
    monkeypatch.setattr('dota_helper.tournaments.tournament_index', lambda *a:[
        dict(match_id=mid, leagueid=123, account_id=42, tier='premium', name='Recorded event') for mid in games])
    calls = []
    def query(q, variables=None):
        if 'itemPurchases' not in q:
            return {'constants':{'gameVersions':[{'id':182, 'name':PATCHES[-1]['name']}]}}
        ids = [int(n) for n in re.findall(r'match\(id:(\d+)\)', q)]
        calls.append(ids)
        return {f'm{i}':games[mid] for i,mid in enumerate(ids)}
    monkeypatch.setattr(client, 'query', query)
    updates = []
    routes, _ = tournament_routes(client, 1, 1, reference_ids=[], on_update=updates.append)
    assert calls == [list(range(1, 11)), [11]]
    assert {r.match_ids[0] for r in routes} == set(range(1, 12)) | {100}
    assert routes[-1].match_ids == [100]
    assert all(any(r.match_ids == [100] for r in rows) for rows, _ in updates)
    assert len(json.loads(snapshot.read_text())['routes']) == 12


def test_empty_fresh_tournament_index_preserves_valid_cache(tmp_path, monkeypatch):
    cached_game = match(100)
    cached_game.update(lobbyType='PRACTICE', leagueId=123)
    cached = normalize_stratz(cached_game, cached_game['players'][0], {})
    snapshot = tmp_path / 'tournaments-v1-1-1.json'
    snapshot.write_text(json.dumps({'routes':[asdict(cached)]}))
    client = Stratz(tmp_path, token='test')
    monkeypatch.setattr(client, 'query', lambda *a, **kw:{'leagues':[]})
    routes, _ = tournament_routes(client, 1, 1, reference_ids=[])
    assert [r.match_ids for r in routes] == [[100]]
    assert len(json.loads(snapshot.read_text())['routes']) == 1


def test_tournament_deadline_retains_first_batch_and_reports_remaining_candidates(tmp_path, monkeypatch):
    import re
    import time
    client = Stratz(tmp_path, token='test')
    games = {mid:match(mid) for mid in range(1, 24)}
    for game in games.values():
        game.update(lobbyType='PRACTICE', leagueId=123)
    monkeypatch.setattr('dota_helper.tournaments.tournament_index', lambda *a:[
        dict(match_id=mid, leagueid=123, account_id=42, tier='premium', name='Recorded event') for mid in games])
    calls = []
    def bounded(jobs, q, variables=None):
        if 'itemPurchases' not in q:
            return {'constants':{'gameVersions':[{'id':182, 'name':PATCHES[-1]['name']}]}}
        mids = [int(n) for n in re.findall(r'match\(id:(\d+)\)', q)]
        calls.append(mids)
        jobs.deadline = time.monotonic() - 1
        return {f'm{i}':games[mid] for i,mid in enumerate(mids)}
    monkeypatch.setattr(client, 'bounded', bounded)
    routes, status = tournament_routes(client, 1, 1, reference_ids=[])
    assert len(routes) == 10 and calls == [list(range(1, 11))]
    assert 'deadline' in status
