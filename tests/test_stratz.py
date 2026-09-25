import json
import os
import threading
import time
from urllib.error import HTTPError

import pytest

from dota_helper.catalog import ITEMS, PATCHES
from dota_helper.credentials import save_token, _crypt
from dota_helper.providers import DataError
from dota_helper.stratz import Stratz, eligible, normalize_stratz


def match(mid=123):
    return {'id':mid, 'startDateTime':int(time.time())-100,'gameVersionId':182,'rank':80,'lobbyType':'RANKED',
            'didRadiantWin':False,'players':[{'heroId':1,'steamAccountId':42,'position':'POSITION_1',
            'playerSlot':5,'isRadiant':False,'steamAccount':{'name':'Test player','seasonRank':80,'seasonLeaderboardRank':710},
            'stats':{'itemPurchases':[{'time':-89,'itemId':ITEMS['tango']['id']}, {'time':800,'itemId':ITEMS['bfury']['id']}]},
            'abilities':[{'abilityId':5003,'time':-89,'level':0},{'abilityId':5003,'time':200,'level':1}]}]}


def test_stratz_keeps_exact_sequences_and_discloses_patch_conflict():
    m=match()
    route=normalize_stratz(m,m['players'][0],{182:'7.40b'})
    assert route.source=='STRATZ' and route.result=='Won'
    assert route.purchases[0].time==-89 and route.purchases[1].time==800
    assert route.skills==['antimage_mana_break','antimage_mana_break']
    assert route.patch==0 and 'unverified' in route.patch_label
    assert '#710 (profile)' in route.evidence and 'numeric MMR unavailable' in route.evidence
    assert route.id=='stratz:123:133'


def test_stratz_persists_only_explicit_consistent_player_identity():
    m=match()
    p=m['players'][0]
    p['playerSlot']=130
    route=normalize_stratz(m,p,{182:PATCHES[-1]['name']})
    assert (route.account_id,route.player_slot)==(42,130)
    p.pop('playerSlot')
    assert normalize_stratz(m,p,{}).player_slot is None
    p['playerSlot']=None
    assert normalize_stratz(m,p,{}).player_slot is None
    p['playerSlot']=2
    assert normalize_stratz(m,p,{}).player_slot is None
    p['isRadiant']=True
    assert normalize_stratz(m,p,{}).player_slot==2
    p.pop('steamAccountId')
    p.pop('isRadiant')
    route=normalize_stratz(m,p,{})
    assert route.account_id is None and route.player_slot is None


def test_stratz_prioritizes_current_patch_summaries_and_sorts_streamed_results(tmp_path,monkeypatch):
    client=Stratz(tmp_path,token='test-only')
    unknown,current=match(123),match(456)
    unknown['gameVersionId']=182
    unknown['startDateTime']+=10
    current['gameVersionId']=183
    current['players'][0]['stats']['itemPurchases'].append({'time':900,'itemId':ITEMS['branches']['id']})
    details=[]
    def query(q,variables=None):
        if 'heroStats' in q:
            return {'constants':{'gameVersions':[{'id':182,'name':'7.40b'},{'id':183,'name':PATCHES[-1]['name']}]},
                    'heroStats':{'guide':[{'matchCount':2,'guides':[{'match':m,'matchPlayer':m['players'][0]} for m in (unknown,current)]}]}}
        if 'itemPurchases' in q:
            import re
            ids=[int(n) for n in re.findall(r'match\(id:(\d+)\)',q)]
            details.extend(ids)
            by_id={m['id']:m for m in (unknown,current)}
            return {f'm{i}':by_id[mid] for i,mid in enumerate(ids)}
        return {}
    monkeypatch.setattr(client,'query',query)
    updates=[]
    routes,status=client.routes(1,1,reference_ids=[],on_update=updates.append)
    assert details==[456,123]
    assert [r.match_ids[0] for r in routes]==[456,123]
    assert all(update[0][0].match_ids==[456] for update in updates)


def test_stratz_rejects_divine_wrong_role_and_old_match():
    m=match()
    assert eligible(m,m['players'][0],1,1)
    assert not eligible(m,m['players'][0],1,2)
    m['rank']=75
    assert not eligible(m,m['players'][0],1,1)
    m['rank']=80
    m['startDateTime']=time.time()-8*86400
    assert not eligible(m,m['players'][0],1,1)


def test_reference_games_and_guides_use_lightweight_queries(tmp_path,monkeypatch):
    client=Stratz(tmp_path,token='test-only')
    first, second=match(123), match(456)
    second['players'][0]['stats']['itemPurchases'].append({'time':900,'itemId':ITEMS['branches']['id']})
    calls=[]
    def query(q,variables=None):
        calls.append(q)
        if 'heroStats' in q:
            return {'constants':{'gameVersions':[{'id':182,'name':'7.40b'}]},'m0':first,'m1':None,
                    'heroStats':{'guide':[{'guides':[{'match':second,'matchPlayer':second['players'][0]}]}]}}
        return {'m0':first,'m1':second}
    monkeypatch.setattr(client,'query',query)
    routes,status=client.routes(1,1,reference_ids=[123,999])
    assert [r.match_ids[0] for r in routes]==[123,456]
    assert '1/2 reference games loaded' in status
    assert len(calls)==4 and 'playbackData' not in ''.join(calls)
    assert 'leaderboard' in calls[2]
    assert 'players(steamAccountId:42)' in calls[1]


def test_graphql_error_does_not_cache_partial_data_or_expose_token(tmp_path,monkeypatch):
    client=Stratz(tmp_path,token='private-test-token')
    class Response:
        def __enter__(self):
            import io
            return io.StringIO(json.dumps({'errors':[{'message':'private-test-token'}],'data':{'match':None}}))
        def __exit__(self,*a): pass
    monkeypatch.setattr('dota_helper.stratz.urlopen',lambda *a,**kw:Response())
    with pytest.raises(DataError) as exc:
        client.query('{match(id:1){id}}')
    assert 'private-test-token' not in str(exc.value)
    assert not list(tmp_path.glob('*.json'))


def test_auth_failure_clear_and_no_secret(tmp_path,monkeypatch):
    client=Stratz(tmp_path,token='private-test-token')
    monkeypatch.setattr('dota_helper.stratz.urlopen',lambda *a,**kw: (_ for _ in ()).throw(HTTPError('https://api.stratz.com/graphql',403,'private-test-token',{},None)))
    with pytest.raises(DataError,match='STRATZ HTTP 403') as exc:
        client.query('{__typename}')
    assert 'private-test-token' not in str(exc.value)


@pytest.mark.skipif(os.name!='nt',reason='Windows DPAPI')
def test_credential_is_user_encrypted(tmp_path):
    file=tmp_path/'key.bin'
    save_token('test-credential',file)
    assert b'test-credential' not in file.read_bytes()
    assert _crypt(file.read_bytes(),True)==b'test-credential'


def test_cancellation_prevents_stratz_request(tmp_path,monkeypatch):
    client=Stratz(tmp_path,token='test-only')
    monkeypatch.setattr(client,'query',lambda *a:pytest.fail('No request expected'))
    cancel=threading.Event()
    cancel.set()
    with pytest.raises(DataError):
        client.routes(1,1,cancel=cancel,reference_ids=[])


def test_missing_nested_player_and_inner_pagination_find_ten(tmp_path,monkeypatch):
    client=Stratz(tmp_path,token='test-only')
    calls=[]
    def guide(mid, rank=80):
        m=match(mid)
        m['rank']=rank
        return {'matchId':mid,'heroId':1,'steamAccountId':42,'match':m,'matchPlayer':None}
    def query(q,variables=None):
        calls.append((q,variables))
        if 'heroStats' in q:
            offset=variables['skip']
            rows=[guide(i,75) for i in range(1,51)] if offset==0 else [guide(i) for i in range(51,61)]
            return {'constants':{'gameVersions':[{'id':182,'name':'7.40b'}]},'heroStats':{'guide':[{'matchCount':60,'guides':rows}]}}
        result={}
        for i,mid in enumerate(range(51,61)):
            m=match(mid)
            m['players'][0]['stats']['itemPurchases'] += [{'time':900+j,'itemId':ITEMS['branches']['id']} for j in range(i)]
            result[f'm{i}']=m
        return result
    monkeypatch.setattr(client,'query',query)
    routes,status=client.routes(1,1,reference_ids=[])
    assert len(routes)==10
    assert [v['skip'] for q,v in calls if v]==[0,50]
    assert 'guides(take:50,skip:$skip)' in calls[0][0]
    assert 'guide(heroId:$hero,positionId:$position)' in calls[0][0]
    assert all(r.role==1 for r in routes)


def test_backfill_replaces_duplicates_and_missing_skills(tmp_path,monkeypatch):
    client=Stratz(tmp_path,token='test-only')
    detail_calls=[]
    def query(q,variables=None):
        if 'heroStats' in q:
            return {'constants':{'gameVersions':[{'id':182,'name':'7.40b'}]},'heroStats':{'guide':[{'matchCount':12,
                    'guides':[{'matchId':i,'heroId':1,'steamAccountId':42,'match':match(i)} for i in range(1,13)]}]}}
        import re
        ids=[int(n) for n in re.findall(r'match\(id:(\d+)\)',q)]
        detail_calls.append(ids)
        result={}
        for index,mid in enumerate(ids):
            m=match(mid)
            if mid==1:
                m['players'][0]['abilities']=[]
            if mid>3:
                m['players'][0]['stats']['itemPurchases'] += [{'time':900+j,'itemId':ITEMS['branches']['id']} for j in range(mid-3)]
            result[f'm{index}']=m
        return result
    monkeypatch.setattr(client,'query',query)
    routes,status=client.routes(1,1,reference_ids=[])
    assert len(routes)==10
    assert detail_calls==[list(range(1,11)),[11,12]]
    assert 'duplicate purchase and skill sequence' in status
    assert 'purchase or skill history unavailable' in status


def test_true_empty_source_does_not_invent_fallback(tmp_path,monkeypatch):
    client=Stratz(tmp_path,token='test-only')
    monkeypatch.setattr(client,'query',lambda *a,**kw:{'constants':{'gameVersions':[]},'heroStats':{'guide':[{'matchCount':0,'guides':[]}]}})
    routes,status=client.routes(1,4,reference_ids=[])
    assert not routes and 'Available guide list and sampled player histories exhausted' in status and '(0 reported)' in status


def test_player_history_fallback_recovers_ten_without_guides(tmp_path,monkeypatch):
    client=Stratz(tmp_path,token='test-only')
    games=[]
    for i in range(10):
        m=match(i+1)
        m['startDateTime']=int(time.time())-10*86400
        m['players'][0]['stats']['itemPurchases'] += [{'time':900+j,'itemId':ITEMS['branches']['id']} for j in range(i)]
        games.append(m)
    def query(q,variables=None):
        if 'heroStats' in q:
            return {'constants':{'gameVersions':[{'id':182,'name':'7.40b'}]},'heroStats':{'guide':[]}}
        if 'leaderboard' in q:
            return {'leaderboard':{'season':{'players':[{'steamAccountId':42,'rank':100}]}}}
        if 'p0:player' in q:
            return {'p0':{'matches':games}}
        return {f'm{i}':m for i,m in enumerate(games)}
    monkeypatch.setattr(client,'query',query)
    routes,status=client.routes(1,1,reference_ids=[])
    assert len(routes)==10
    assert all(any('player history' in w for w in r.warnings) for r in routes)
    assert all(any('OLDER EXAMPLE' in w for w in r.warnings) for r in routes)


def test_broader_player_discovery_still_requires_requested_match_role(tmp_path,monkeypatch):
    client=Stratz(tmp_path,token='test-only')
    valid=match(123)
    wrong=match(456)
    wrong['players'][0]['position']='POSITION_4'
    calls=[]
    def query(q,variables=None):
        calls.append(q)
        if 'heroStats' in q:
            return {'constants':{'gameVersions':[]},'heroStats':{'guide':[]}}
        if 'leaderboard' in q:
            players=[] if 'position:$position' in q else [{'steamAccountId':42,'rank':100}]
            return {'leaderboard':{'season':{'players':players}}}
        if 'p0:player' in q:
            assert 'positionIds:[POSITION_1]' in q and 'rankIds:[80]' in q
            return {'p0':{'matches':[valid,wrong]}}
        assert 'match(id:456)' not in q
        return {'m0':valid}
    monkeypatch.setattr(client,'query',query)
    routes,status=client.routes(1,1,reference_ids=[])
    assert [r.match_ids[0] for r in routes]==[123]
    assert '1 player histories checked (2 match records)' in status
    assert len([q for q in calls if 'leaderboard' in q])==2


def test_reference_league_match_accepts_patch_window_but_not_unlinked_practice():
    m=match()
    m.update(lobbyType='PRACTICE',leagueId=20142,startDateTime=int(time.time())-9*86400)
    p=m['players'][0]
    p['steamAccount']['proSteamAccount']={'name':'WoE'}
    assert not eligible(m,p,1,1,recent=False)
    assert eligible(m,p,1,1,recent=False,allow_league=True)
    assert not eligible(m,p,1,2,recent=False,allow_league=True)
    route=normalize_stratz(m,p,{182:'7.40b'})
    assert route.player=='WoE' and 'League match #20142' in route.evidence
    m['leagueId']=0
    assert not eligible(m,p,1,1,recent=False,allow_league=True)
