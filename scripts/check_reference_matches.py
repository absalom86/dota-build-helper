"""Read-only independent source verification for user-supplied reference IDs."""
import json
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dota_helper.pub_lookup import discovery_query

output = Path('.local/reference-check')
output.mkdir(parents=True, exist_ok=True)
ids = [8987805727, 8987753263, 8987688490]
paths = [(str(mid), f'matches/{mid}') for mid in ids]
paths.append(('discovery', 'explorer?' + urlencode({'sql': discovery_query(1)})))
results = []
for name, path in paths:
    started = time.monotonic()
    try:
        with urlopen(Request('https://api.opendota.com/api/' + path,
                             headers={'User-Agent': 'DotaBuildHelper/0.3'}), timeout=4) as response:
            data = json.load(response)
        (output / f'{name}.json').write_text(json.dumps(data), encoding='utf-8')
        info = {'match_ids': [r['match_id'] for r in data.get('rows', [])]} if name == 'discovery' else {
            'patch': data.get('patch'), 'start_time': data.get('start_time'),
            'players': [{k: p.get(k) for k in ('hero_id', 'position_est', 'rank_tier')}
                        | {'purchases': len(p.get('purchase_log') or []), 'skills': len(p.get('ability_upgrades_arr') or [])}
                        for p in data.get('players', []) if p.get('hero_id') == 1]}
        results.append({'name': name, 'seconds': round(time.monotonic() - started, 2), 'result': info})
    except Exception as exc:
        results.append({'name': name, 'seconds': round(time.monotonic() - started, 2),
                        'error': type(exc).__name__, 'http': getattr(exc, 'code', None)})
    time.sleep(1.05)
print(json.dumps(results, indent=2))
(output / 'report.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
