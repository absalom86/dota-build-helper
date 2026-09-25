import time
import pytest
from dota_helper.draft_meta import role_meta,leaders
from dota_helper.providers import DataError
from dota_helper.app import MainWindow


def test_recent_role_data_filters_stale_and_small_winrate_samples():
    class Client:
        def query(self,q,ttl):
            assert 'POSITION_2' in q and 'IMMORTAL' in q
            return {'heroStats':{'winDay':[
                dict(heroId=1,day=int(time.time())-86400,winCount=60,matchCount=100),
                dict(heroId=2,day=int(time.time())-86400,winCount=2,matchCount=2),
                dict(heroId=3,day=int(time.time())-30*86400,winCount=100,matchCount=100)]}}
    rows,status=role_meta(2,Client())
    wins,played=leaders(rows)
    assert [r['hero_id'] for r in wins]==[1]
    assert [r['hero_id'] for r in played]==[1,2]
    assert 'patch unverified' in status
    assert leaders(rows,{1})[0]==[]


def test_overlay_draft_works_without_hero_or_enemy_picks(tmp_path,monkeypatch):
    monkeypatch.setattr('dota_helper.app.LOCAL',tmp_path)
    w=MainWindow(start_services=False)
    w.draft.meta_provider=lambda role:([dict(hero_id=1,games=100,wins=60,rate=.6)],'Fixture stats')
    w.draft.launch_worker=lambda fn,done,failed:done(fn(None))
    w.draft.refresh_meta()
    w.on_gsi({'map':{'game_state':'DOTA_GAMERULES_STATE_HERO_SELECTION'}})
    w.tick()
    assert w.overlay.title.text()=='DRAFT HELPER'
    assert 'Anti-Mage' in w.overlay.items.text() and 'MOST PLAYED' in w.overlay.items.text()
    w.fetch=lambda:None
    w.on_gsi({'hero':{'id':1},'player':{'steamid':'x'},'map':{'game_state':'DOTA_GAMERULES_STATE_STRATEGY_TIME','clock_time':-50}})
    assert not w.draft.meta_active
    w.close()

def test_game_draft_sync_and_missing_data_preserves_picks(tmp_path,monkeypatch):
    monkeypatch.setattr('dota_helper.app.LOCAL',tmp_path)
    w=MainWindow(start_services=False)
    w.draft.auto.setChecked(False)
    payload={'player':{'team_name':'radiant'},'draft':{'team2':{'pick0_id':1,'ban0_id':2},'team3':{'pick0_id':22}}}
    w.draft.ingest_draft(payload)
    assert w.draft.enemies[0].currentData()==22
    assert w.draft.blocked=={1,2}
    revision=w.draft.revision
    w.draft.ingest_draft(payload)
    assert w.draft.revision==revision
    w.draft.ingest_draft({})
    assert w.draft.enemies[0].currentData()==22
    assert 'unavailable' in w.draft.sync_status.text()
    w.close()
