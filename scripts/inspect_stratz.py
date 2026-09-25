"""Authenticated schema/reference inspection; never logs credentials or bodies on errors."""
import argparse
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dota_helper.credentials import load_token

parser = argparse.ArgumentParser()
parser.add_argument('--type', default='')
parser.add_argument('--query-file')
args = parser.parse_args()
query = '{ __schema { queryType { name } } }'
if args.type:
    query = 'query($name:String!) { __type(name:$name) { name kind fields { name args { name type { kind name ofType { kind name ofType { kind name } } } } type { kind name ofType { kind name ofType { kind name } } } } inputFields {name type {kind name ofType {kind name ofType {kind name}}}} enumValues {name} } }'
if args.query_file:
    query = Path(args.query_file).read_text(encoding='utf-8')
started = time.monotonic()
request = Request('https://api.stratz.com/graphql', data=json.dumps({'query': query, 'variables': {'name': args.type}}).encode(),
                  headers={'Authorization': 'Bearer ' + load_token(), 'Content-Type': 'application/json', 'User-Agent': 'STRATZ_API'})
try:
    with urlopen(request, timeout=8) as response:
        result = json.load(response)
    output = Path('.local/stratz-inspection')
    output.mkdir(parents=True, exist_ok=True)
    name = args.type or (Path(args.query_file).stem if args.query_file else 'root')
    (output / f'{name}.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    def type_name(t):
        return (t.get('name') or type_name(t['ofType'])) if t else ''
    if args.type and result.get('data', {}).get('__type'):
        obj = result['data']['__type']
        compact = {f['name']: {'type': type_name(f['type']), 'args': {a['name']: type_name(a['type']) for a in f.get('args', [])}} for f in (obj.get('fields') or obj.get('inputFields') or [])}
        print(json.dumps({'seconds': round(time.monotonic()-started, 2), 'type': args.type, 'fields': compact, 'enums': obj.get('enumValues')}))
    else:
        print(json.dumps({'seconds': round(time.monotonic()-started, 2), 'result': result}, indent=2))
except HTTPError as exc:
    print(json.dumps({'seconds': round(time.monotonic()-started, 2), 'http': exc.code,
                      'content_type': exc.headers.get('Content-Type')}))
except Exception as exc:
    print(json.dumps({'seconds': round(time.monotonic()-started, 2), 'error': type(exc).__name__}))
