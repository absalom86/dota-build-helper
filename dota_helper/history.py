"""Local saved searches; timestamps distinguish refreshes from reopening a build."""
from dataclasses import asdict
import json
import time
import uuid
from .catalog import PATCHES
from .models import Route, Purchase
from .ranking import ranked

SEARCH_TTL = 1800
DISCOVERY_VERSION = 5


def patch_key():
    p=PATCHES[-1]
    return f"{p['id']}:{p['name']}:{p['date']}"


def decode(entry):
    result=[]
    for data in entry.get('routes',[]):
        try:
            record=dict(data)
            record['purchases']=[Purchase(**p) for p in record['purchases']]
            route=Route(**record)
            if route.hero_id==entry['hero'] and route.role==entry['role'] and not route.demo:
                result.append(route)
        except (KeyError,TypeError,ValueError):
            continue
    return ranked(result)


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
        return max(matches,key=lambda e:(e['patch']==patch_key(),e['updated']),default=None)

    def save(self, hero, role, source, routes, selected, status):
        if source==1 or not routes:
            return
        key=f'{hero}:{role}:{source}:{patch_key()}'
        old=next((e for e in self.entries if e['key']==key),None)
        cached='cached' in status.lower()
        now=time.time()
        entry=dict(key=key,hero=hero,role=role,source=source,patch=patch_key(),patch_name=PATCHES[-1]['name'],
                   updated=old['updated'] if old and cached else now,used=now,
                   cached_origin=cached,discovery_version=DISCOVERY_VERSION,selected=selected,status=status,routes=[asdict(r) for r in ranked(routes)])
        self.entries=[e for e in self.entries if e['key']!=key]+[entry]
        self.write()

    def choose(self, key, selected):
        for entry in self.entries:
            if entry['key']==key:
                entry.update(selected=selected,used=time.time())
                self.write()
                return
