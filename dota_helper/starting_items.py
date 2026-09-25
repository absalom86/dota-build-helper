"""Starting quantities with explicit corrections and a labelled branch fallback."""
import json
from collections import Counter
from functools import lru_cache
import threading
import uuid
from .paths import user_data_dir

# User-verified screenshot: Juggernaut, match 8946414154. Tango is one pack.
VERIFIED = {'8946414154:8': {'tango': 1, 'magic_stick': 1, 'branches': 2,
                            'quelling_blade': 1, 'faerie_fire': 1}}
_WRITE_LOCK = threading.Lock()

def key(route):
    return f'{route.match_ids[0]}:{route.hero_id}' if route.match_ids and not route.demo else route.id

@lru_cache(maxsize=4)
def load(path):
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):
        return {}

def _correction_record(route):
    path=user_data_dir() / 'starting-items.json'
    value=load(path).get(key(route), VERIFIED.get(key(route)))
    if not isinstance(value,dict):
        return None
    if isinstance(value.get('counts'), dict):
        return {'counts': _clean_counts(value['counts']),
                'source': str(value.get('source') or 'User correction'),
                'note': str(value.get('note') or '')}
    return {'counts': _clean_counts(value),
            'source': ('Screenshot correction' if key(route) not in load(path) and key(route) in VERIFIED
                       else 'User correction'), 'note': ''}


def _clean_counts(values):
    return {k:n for k,n in values.items() if isinstance(k,str) and type(n) is int and 0<n<=30}


def correction(route):
    record = _correction_record(route)
    return record['counts'] if record is not None else None


def recorded_counts(route):
    """Count purchase events, not inventory slots or consumable charges."""
    return dict(Counter(p.key for p in route.purchases if p.time < 0))

def counts(route):
    corrected=correction(route)
    if corrected is not None:
        return corrected
    values=recorded_counts(route)
    if estimated_branches(route):
        values['branches']=2
    return values

def estimated_branches(route):
    if route.demo or route.source != 'STRATZ' or correction(route) is not None:
        return False
    values=Counter(p.key for p in route.purchases if p.time<0)
    return (values['branches']==1 and
            sum(n for k,n in values.items() if k not in ('ward_observer','ward_sentry','ward_dispenser'))<6)

def details(route):
    """Per-item quantity evidence for preview, editing, and native-guide notes.

    A second purchase log can corroborate or disagree with the original log; it
    never replaces the selected game's recorded counts without an explicit edit.
    """
    recorded = recorded_counts(route)
    corrected = _correction_record(route)
    values = counts(route)
    inferred = estimated_branches(route)
    from .quantity_evidence import get_saved
    comparison = get_saved(route)
    result = []
    for item, count in values.items():
        if corrected is not None:
            provenance, source = 'corrected', corrected['source']
            note = corrected['note'] or 'Explicit quantities override the original purchase log.'
        elif item == 'branches' and inferred:
            provenance, source = 'estimated', 'STRATZ branch fallback'
            note = 'Two branches assumed from one recorded branch and fewer than six non-ward purchases.'
        else:
            provenance, source = 'recorded', route.source
            note = ('Recorded purchase events; STRATZ may omit starting quantities.'
                    if route.source == 'STRATZ' else 'Recorded purchase events, not an inventory snapshot.')
        if corrected is None and comparison:
            if item in comparison.get('differences', {}):
                alternate = comparison['differences'][item]['opendota']
                note += f' OpenDota records {alternate}; review before applying.'
            elif comparison.get('status') in ('verified', 'conflict'):
                note += ' OpenDota agrees with the recorded count.'
        if item == 'tango':
            note += ' Quantity counts purchased packs, not remaining charges.'
        result.append({'key': item, 'count': count, 'recorded_count': recorded.get(item, 0),
                       'provenance': provenance, 'source': source,
                       'unit': 'packs' if item == 'tango' else 'items', 'note': note})
    return result


def _write(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(f'.{uuid.uuid4().hex}.tmp')
    try:
        temp.write_text(json.dumps(data),encoding='utf-8')
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    load.cache_clear()


def save(route, values, source='User correction', note=''):
    """Save an explicit override; legacy plain-count records still load."""
    path=user_data_dir() / 'starting-items.json'
    with _WRITE_LOCK:
        data=dict(load(path))
        data[key(route)]={'counts': _clean_counts(values), 'source': str(source), 'note': str(note)}
        _write(path, data)


def reset(route):
    """Return to recorded counts and the usual labelled STRATZ-only estimate."""
    path=user_data_dir() / 'starting-items.json'
    with _WRITE_LOCK:
        data=dict(load(path))
        if key(route) in VERIFIED:
            # A null override explicitly opts out of the bundled screenshot fix.
            data[key(route)] = None
        else:
            data.pop(key(route), None)
        _write(path, data)
