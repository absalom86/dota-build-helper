"""Exercise the real Qt Find builds button and every result row for all 635 pairs.

First-page discovery is seeded from the live census to conserve API quota.
Additional pages and match details use the normal live provider. No demo data.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import argparse

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--retry-shortages',action='store_true')
parser.add_argument('--reuse-audit-cache',action='store_true',help='Reuse same-day raw responses; new discovery still uses the live API')
args=parser.parse_args()
sys.path.insert(0,str(ROOT))
profile=ROOT/'.local/manual-coverage'
profile.mkdir(parents=True,exist_ok=True)
shutil.copyfile(ROOT/'.local/stratz-key.bin',profile/'stratz-key.bin')
os.environ['DOTA_HELPER_HOME']=str(profile)
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from dota_helper.app import MainWindow
from dota_helper.catalog import HEROES
from dota_helper.stratz import Stratz, guide_query, SUMMARY
import dota_helper.stratz as stratz_module

remaining_hour = [1500]
original_urlopen = stratz_module.urlopen
def observed_urlopen(*a, **kw):
    response = original_urlopen(*a, **kw)
    remaining_hour[0] = int(response.headers.get('x-ratelimit-remaining-hour', remaining_hour[0]))
    return response
stratz_module.urlopen = observed_urlopen
if args.reuse_audit_cache:
    original_query = Stratz.query
    def same_day_query(self, query, variables=None, ttl=300):
        return original_query(self, query, variables, ttl=86400)
    Stratz.query = same_day_query

client=Stratz(ROOT/'.local/coverage/cache')
versions=client.query('{constants {gameVersions {id name asOfDateTime}}}',ttl=86400)['constants']
cache=profile/'cache'
cache.mkdir(exist_ok=True)
app=QApplication([])
window=MainWindow(start_services=False)
window.source.setCurrentIndex(4)  # This historical audit measures ranked-pub coverage.
window.resize(1280,1000)
window.show()
previous=json.loads((profile/'results.json').read_text()) if args.retry_shortages else []
if previous and not (profile/'baseline.json').exists():
    (profile/'baseline.json').write_text(json.dumps(previous,indent=2))
rows_by_key={(r['hero_id'],r['role']):r for r in previous}
results=list(previous)
checked=0
for hero_id,hero in sorted(HEROES.items(),key=lambda p:int(p[0])):
    if remaining_hour[0] < 25:
        break
    hero_id=int(hero_id)
    census_query='{heroStats {'+' '.join(f'p{role}:guide(heroId:{hero_id},positionId:POSITION_{role}){{matchCount guides(take:50){{matchId heroId steamAccountId match{{{SUMMARY}}}}}}}' for role in range(1,6))+'}}'
    census=client.query(census_query,ttl=86400)['heroStats']
    for role in range(1,6):
        if remaining_hour[0] < 25:
            break
        if args.retry_shortages and rows_by_key.get((hero_id,role),{}).get('builds',0)>=10:
            continue
        variables={'hero':hero_id,'position':f'POSITION_{role}','skip':0}
        body=json.dumps({'query':guide_query(),'variables':variables},sort_keys=True).encode()
        key=hashlib.sha256(body).hexdigest()
        (cache/f'stratz-{key}.json').write_text(json.dumps({'at':time.time(),'data':{'constants':versions,'heroStats':{'guide':census[f'p{role}']}}}))
        window.hero.setCurrentIndex(window.hero.findData(hero_id))
        window.role.setCurrentIndex(window.role.findData(role))
        window.new_match()
        started=time.monotonic()
        window.find_button.click()
        while window.fetching and time.monotonic()-started<12:
            app.processEvents()
            time.sleep(.01)
        if window.fetching:
            raise RuntimeError('UI did not respect lookup deadline')
        seconds=time.monotonic()-started
        routes=list(window.routes)
        selection_ok=True
        for i,route in enumerate(routes):
            item=window.match_table.item(i,0)
            window.match_table.scrollToItem(item)
            app.processEvents()
            rect=window.match_table.visualItemRect(item)
            QTest.mouseClick(window.match_table.viewport(),Qt.MouseButton.LeftButton,pos=rect.center())
            app.processEvents()
            selection_ok &= window.current_route().id==route.id and window.purchases.rowCount()==len(route.purchases)
        unique=len({(tuple(p.key for p in r.purchases),tuple(r.skills)) for r in routes})
        row={'hero_id':hero_id,'hero':hero['localized_name'],'role':role,'builds':len(routes),
             'distinct_sequences':unique,'selection_ok':bool(selection_ok),'seconds':round(seconds,3),
             'match_ids':[r.match_ids[0] for r in routes],'status':window.status.text()}
        rows_by_key[(hero_id,role)]=row
        results=[rows_by_key[k] for k in sorted(rows_by_key)]
        checked+=1
        (profile/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        if checked%25==0:
            print(json.dumps({'checked_this_pass':checked,'total':len(results),'ten_distinct':sum(r['distinct_sequences']>=10 for r in results),
                              'zero':sum(r['builds']==0 for r in results),'selection_failures':sum(not r['selection_ok'] for r in results)}),flush=True)
        time.sleep(.6)
window.close()
app.processEvents()
print(json.dumps({'complete':len(results),'ten_distinct':sum(r['distinct_sequences']>=10 for r in results),
                  'zero':sum(r['builds']==0 for r in results),'selection_failures':sum(not r['selection_ok'] for r in results),
                  'checked_this_pass':checked,'remaining_hour':remaining_hour[0],
                  'stopped_for_quota':remaining_hour[0]<25}),flush=True)
