"""Census of every hero/position guide list; one bounded API request per hero."""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dota_helper.catalog import HEROES
from dota_helper.stratz import Stratz, eligible, SUMMARY, PLAYER

out=ROOT/'.local/coverage'
out.mkdir(parents=True,exist_ok=True)
client=Stratz(out/'cache')
results=[]
for hero_id,hero in sorted(HEROES.items(),key=lambda p:int(p[0])):
    hero_id=int(hero_id)
    query='{heroStats {'+' '.join(f'p{role}:guide(heroId:{hero_id},positionId:POSITION_{role}){{matchCount guides(take:50){{matchId heroId steamAccountId match{{{SUMMARY}}}}}}}' for role in range(1,6))+'}}'
    try:
        data=client.query(query,ttl=86400)['heroStats']
        for role in range(1,6):
            groups=data.get(f'p{role}') or []
            guides=[g for group in groups for g in group.get('guides') or []]
            rows=[g for g in guides if g.get('match') and eligible(g['match'],{'heroId':g.get('heroId'),'steamAccountId':g.get('steamAccountId'),'position':f'POSITION_{role}'},hero_id,role)]
            results.append({'hero_id':hero_id,'hero':hero['localized_name'],'role':role,
                            'reported_matches':sum(g.get('matchCount') or 0 for g in groups),
                            'guides':len(guides),'eligible':len({g['matchId'] for g in rows})})
    except Exception as exc:
        results.extend({'hero_id':hero_id,'hero':hero['localized_name'],'role':role,'error':str(exc)} for role in range(1,6))
    (out/'census.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    if len(results)%50==0:
        print(json.dumps({'checked':len(results),'ten_candidates':sum(r.get('eligible',0)>=10 for r in results),'zero':sum(r.get('eligible')==0 for r in results),'errors':sum('error' in r for r in results)}),flush=True)
    time.sleep(1.05)
print(json.dumps({'complete':len(results),'ten_candidates':sum(r.get('eligible',0)>=10 for r in results),'zero':sum(r.get('eligible')==0 for r in results),'errors':sum('error' in r for r in results)}),flush=True)
