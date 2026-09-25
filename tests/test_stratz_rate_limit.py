import json
import time
from urllib.error import HTTPError
import pytest
from dota_helper.stratz import Stratz
from dota_helper.providers import DataError


def test_429_persists_cooldown_across_clients_and_queries(tmp_path,monkeypatch):
    calls=[]
    def limited(*a,**kw):
        calls.append(1)
        raise HTTPError('https://api.stratz.com/graphql',429,'limited',{'Retry-After':'300'},None)
    monkeypatch.setattr('dota_helper.stratz.urlopen',limited)
    for query in ['{first}','{second}']:
        with pytest.raises(DataError,match='New requests paused'):
            Stratz(tmp_path,token='test').query(query)
    assert len(calls)==1
    assert json.loads((tmp_path/'stratz-rate-limit.json').read_text())['until']>time.time()+290


def test_cached_response_is_usable_during_cooldown(tmp_path,monkeypatch):
    import hashlib
    q='{cached}'
    body=json.dumps({'query':q,'variables':{}},sort_keys=True).encode()
    file=tmp_path/('stratz-'+hashlib.sha256(body).hexdigest()+'.json')
    file.write_text(json.dumps({'at':time.time(),'data':{'ok':True}}))
    (tmp_path/'stratz-rate-limit.json').write_text(json.dumps({'until':time.time()+300}))
    monkeypatch.setattr('dota_helper.stratz.urlopen',lambda *a,**kw:pytest.fail('No network during cooldown'))
    assert Stratz(tmp_path,token='test').query(q)=={'ok':True}
