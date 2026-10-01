"""Local saved searches; timestamps distinguish refreshes from reopening a build."""
from dataclasses import asdict
import json
import time
import uuid
from .catalog import PATCHES
from .models import Route, Purchase
from .ranking import ranked
from .endgame import endgame_examples
from .recency import neutral_patch_label, presentation_warnings

SEARCH_TTL = 1800
DISCOVERY_VERSION = 12


def patch_key():
    p=PATCHES[-1]
    return f"{p['id']}:{p['name']}:{p['date']}"


def _decode_records(entry, records):
    result=[]
    if not isinstance(records, list):
        return result
    for data in records:
        try:
            record=dict(data)
            record['purchases']=[Purchase(**p) for p in record['purchases']]
            route=Route(**record)
            if route.hero_id==entry['hero'] and route.role==entry['role'] and not route.demo:
                route.warnings = presentation_warnings(route)
                route.patch_label = neutral_patch_label(route)
                result.append(route)
        except (KeyError,TypeError,ValueError):
            continue
    return result


def decode(entry):
    preferred = entry.get('selected') if entry.get('selected_explicit', True) else None
    return ranked(_decode_records(entry, entry.get('routes', [])), preferred_id=preferred)


def decode_examples(entry):
    # Old saved searches can supply examples without a network migration.
    routes = _decode_records(entry, entry.get('endgame_routes', [])) + _decode_records(entry, entry.get('routes', []))
    return endgame_examples(routes, entry['hero'], entry['role'])


class SearchHistory:
    def __init__(self, root):
        self.path=root/'search-history.json'
        try:
            entries=json.loads(self.path.read_text(encoding='utf-8'))
            self.entries=[e for e in entries if isinstance(e,dict) and all(k in e for k in
                          ('key','hero','role','source','patch','updated','used')) and decode(e)]
        except (OSError,ValueError,TypeError):
            self.entries=[]
        if not self.path.exists():
            for file in (root/'cache').glob('tournaments-v1-*.json'):
                try:
                    saved=json.loads(file.read_text(encoding='utf-8'))
                    first=saved['routes'][0]
                    hero,role=first['hero_id'],first['role']
                    entry=dict(key=f'{hero}:{role}:0:{patch_key()}',hero=hero,role=role,source=0,
                               patch=patch_key(),patch_name=PATCHES[-1]['name'],updated=saved['at'],used=saved['at'],
                               cached_origin=True,selected=first['id'],status='Imported existing tournament cache',routes=saved['routes'])
                    if decode(entry):
                        self.entries.append(entry)
                except (OSError,ValueError,TypeError,KeyError,IndexError):
                    continue
            if self.entries:
                self.write()

    def write(self):
        self.entries=sorted(self.entries,key=lambda e:e['used'],reverse=True)[:50]
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix(f'.{uuid.uuid4().hex}.tmp')
        temp.write_text(json.dumps(self.entries,ensure_ascii=False),encoding='utf-8')
        temp.replace(self.path)

    def find(self, hero, role, source):
        matches=[e for e in self.entries if (e['hero'],e['role'],e['source'])==(hero,role,source)]
        return max(matches,key=lambda e:e['updated'],default=None)

    def save(self, hero, role, source, routes, selected, status, *, selected_explicit=True):
        routes=[r for r in routes if r.hero_id==hero and r.role==role and not r.demo]
        if source==1 or not routes:
            return
        key=f'{hero}:{role}:{source}:{patch_key()}'
        old=next((e for e in self.entries if e['key']==key),None) or self.find(hero, role, source)
        cached='cached' in status.lower()
        now=time.time()
        examples=endgame_examples((decode_examples(old) if old else []) + list(routes), hero, role)
        preferred = selected if selected_explicit else None
        routes=ranked((decode(old) if old else []) + routes, preferred_id=preferred)
        entry=dict(key=key,hero=hero,role=role,source=source,patch=patch_key(),patch_name=PATCHES[-1]['name'],
                   updated=old['updated'] if old and cached else now,used=now,
                   cached_origin=cached,discovery_version=DISCOVERY_VERSION,selected=selected,status=status,
                   selected_explicit=bool(selected_explicit),
                   routes=[asdict(r) for r in ranked(routes, preferred_id=preferred)],endgame_routes=[asdict(r) for r in examples])
        self.entries=[e for e in self.entries if e['key']!=key]+[entry]
        self.write()

    def choose(self, key, selected):
        for entry in self.entries:
            if entry['key']==key:
                entry.update(selected=selected,selected_explicit=True,used=time.time())
                self.write()
                return

    def save_recovered_skills(self, route, original_skills):
        """Persist exact-player enrichment without altering selection or search age."""
        changed = False
        for entry in self.entries:
            for field in ('routes', 'endgame_routes'):
                for record in entry.get(field, []):
                    if (record.get('id') == route.id and record.get('hero_id') == route.hero_id
                            and record.get('account_id') == route.account_id
                            and record.get('player_slot') == route.player_slot
                            and tuple(record.get('skills', [])) == tuple(original_skills)):
                        record['skills'] = list(route.skills)
                        record['warnings'] = list(route.warnings)
                        changed = True
        if changed:
            self.write()
