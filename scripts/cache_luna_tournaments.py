"""Seed tournament cache from already verified STRATZ responses, with no API calls."""
import json
import os
from dataclasses import asdict
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dota_helper.stratz import normalize_stratz

ids=[8973859403,8972773416,8958950792,8946860406,8944752572]
records={}
for file in (ROOT/'.local/luna-ui/cache').glob('stratz-*.json'):
    data=json.loads(file.read_text(encoding='utf-8'))['data']
    for match in data.values():
        if not isinstance(match,dict) or match.get('id') not in ids:
            continue
        for player in match.get('players') or []:
            if player.get('heroId')==48 and player.get('stats') and player.get('abilities'):
                records[match['id']]=normalize_stratz(match,player,{182:'7.40b'})
routes=[records[mid] for mid in ids]
assert all(r and r.tournament and r.role==1 for r in routes)
for route in routes:
    route.evidence='TOURNAMENT · saved comparison game · no pub MMR'
    route.warnings.insert(0,'Cached from the previously verified Luna tournament comparison; live refresh pending.')
roots=[ROOT/'.local/cache',ROOT/'.local/luna-ui/cache',Path(os.environ['LOCALAPPDATA'])/'DotaBuildHelper/cache']
for root in roots:
    root.mkdir(parents=True,exist_ok=True)
    (root/'tournaments-v1-48-1.json').write_text(json.dumps({'at':time.time(),'routes':[asdict(r) for r in routes]}),encoding='utf-8')
print('Cached five verified Luna tournament builds in source, test and desktop profiles.')
