from dataclasses import asdict
import json
import time
from PySide6.QtWidgets import QApplication
from dota_helper.app import MainWindow
from dota_helper.history import SearchHistory, decode
from dota_helper.stratz import Stratz, normalize_stratz
from test_stratz import match
from dota_helper.catalog import PATCHES


def route(mid=123):
    m=match(mid)
    m.update(lobbyType='PRACTICE',leagueId=7)
    return normalize_stratz(m,m['players'][0],{})


def test_history_survives_restart_and_preserves_update_time_on_selection(tmp_path):
    history=SearchHistory(tmp_path)
    history.save(1,1,0,[route(1),route(2)],'stratz:1:133','Live tournament results')
    entry=history.find(1,1,0)
    updated=entry['updated']
    history.choose(entry['key'],'stratz:2:133')
    restored=SearchHistory(tmp_path).find(1,1,0)
    assert restored['updated']==updated and restored['selected']=='stratz:2:133'
    assert len(decode(restored))==2
    assert history.find(1,2,0) is None and history.find(1,1,4) is None


def test_history_reranks_old_saved_order_but_retains_explicit_selection(tmp_path):
    old,unknown,current=route(1),route(2),route(3)
    old.patch=PATCHES[-2]['id']
    old.patch_label=PATCHES[-2]['name']
    old.warnings=[]
    current.patch=PATCHES[-1]['id']
    current.patch_label=PATCHES[-1]['name']
    current.warnings=[]
    entry={'hero':1,'role':1,'routes':[asdict(r) for r in (old,unknown,current)]}
    assert [r.id for r in decode(entry)]==[current.id,unknown.id,old.id]
    history=SearchHistory(tmp_path)
    history.save(1,1,0,[old,unknown,current],old.id,'Live results')
    saved=SearchHistory(tmp_path).find(1,1,0)
    assert saved['selected']==old.id
    assert [r['id'] for r in saved['routes']]==[current.id,unknown.id,old.id]


def test_recent_saved_search_and_open_history_do_not_launch_network(tmp_path,monkeypatch):
    history=SearchHistory(tmp_path)
    history.save(1,1,0,[route(1),route(2)],'stratz:2:133','Tournament results')
    monkeypatch.setattr('dota_helper.app.LOCAL',tmp_path)
    window=MainWindow(start_services=False)
    jobs=[]
    window.launch_worker=lambda *a,**kw:jobs.append(a)
    window.fetch()
    assert jobs==[] and window.current_route().id=='stratz:2:133'
    window.route_choice.setCurrentIndex(0)
    assert SearchHistory(tmp_path).find(1,1,0)['selected']=='stratz:1:133'
    window.history_choice.activated.emit(window.history_choice.currentIndex())
    assert jobs==[] and window.current_route().id=='stratz:1:133'
    assert window.more_options.isHidden()
    window.more_button.click()
    assert not window.more_options.isHidden()
    window.more_button.click()
    assert window.more_options.isHidden()
    window.find_button.click()
    assert len(jobs)==1
    assert window.find_button.text()=='Cancel' and window.find_button.isEnabled()
    window.find_button.click()
    assert window.cancel.is_set() and len(jobs)==1
    jobs[0][2]('Rate limited')
    assert window.find_button.text()=='Find builds' and window.find_button.isEnabled()
    assert len(window.routes)==2 and 'retained' in window.status.text()
    window.close()
    QApplication.instance().processEvents()


def test_older_patch_history_is_visible_but_requests_refresh(tmp_path,monkeypatch):
    history=SearchHistory(tmp_path)
    history.save(1,1,0,[route()],None,'Tournament results')
    history.entries[0]['patch']='older'
    history.write()
    monkeypatch.setattr('dota_helper.app.LOCAL',tmp_path)
    window=MainWindow(start_services=False)
    jobs=[]
    window.launch_worker=lambda *a,**kw:jobs.append(a)
    window.fetch()
    assert len(jobs)==1 and 'Older bundled patch' in window.status.text()
    jobs[0][2]('Offline')
    window.close()
    QApplication.instance().processEvents()


def test_completed_match_cache_survives_forced_discovery_refresh(tmp_path,monkeypatch):
    import hashlib
    q='{m0:match(id:123){players{stats {itemPurchases {time itemId}} abilities{abilityId}}}}'
    body=json.dumps({'query':q,'variables':{}},sort_keys=True).encode()
    f=tmp_path/('stratz-'+hashlib.sha256(body).hexdigest()+'.json')
    f.write_text(json.dumps({'at':time.time()-86400,'data':{'m0':match()}}))
    monkeypatch.setattr('dota_helper.stratz.urlopen',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('No network')))
    assert Stratz(tmp_path,token='test',refresh=True).query(q)['m0']['id']==123
