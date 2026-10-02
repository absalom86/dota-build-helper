"""Starting inventory with source evidence, recipe assembly and explicit corrections."""
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

def summary(route):
    """Use exact-player evidence only when it explains every recorded component.

    STRATZ can omit duplicate starting purchases. Spare inventory space cannot
    tell us whether the player bought one, two or five branches, so never guess.
    """
    from .item_recipes import assemble_counts
    from .quantity_evidence import recoverable_counts
    corrected = _correction_record(route)
    if corrected is not None:
        values = corrected['counts']
        provenance, source = 'corrected', corrected['source']
        note = corrected['note'] or 'Explicit quantities override the original purchase log.'
    else:
        recovered = recoverable_counts(route)
        if recovered is not None:
            values = recovered
            provenance, source = 'recovered', 'OpenDota same-player starting log'
            note = ('Starting quantities recovered from the same match and player. '
                    'Recipe-expanded items agree with STRATZ; OpenDota preserves repeated copies. '
                    'This is recorded starting-item evidence, not a complete purchase history.')
        else:
            values = recorded_counts(route)
            provenance, source = 'recorded', route.source
            note = ('Minimum recorded quantities; STRATZ may omit repeated starting purchases. '
                    'Exact quantities are unavailable until a matching source or correction supplies them.'
                    if route.source == 'STRATZ' and not route.demo else
                    'Starting stack quantity is ambiguous; only minimum recorded copies are shown.'
                    if route.starting_items_incomplete else
                    'Recorded starting entries, not a complete purchase history.')
    assembled = dict(assemble_counts(values))
    if assembled != values:
        from .catalog import item_name
        parts = ', '.join(f'{item_name(key)} ×{count}' for key, count in values.items())
        note += f' Components combined using the bundled item recipes. Before combining: {parts}.'
    return {'counts': assembled, 'provenance': provenance, 'source': source, 'note': note,
            'unverified': provenance == 'recorded' and not route.demo
                          and (route.source == 'STRATZ' or route.starting_items_incomplete)}


def counts(route):
    return summary(route)['counts']

def details(route):
    """Per-item quantity evidence for preview, editing, and native-guide notes.

    Raw events stay intact. Safe quantity recovery and recipe assembly are
    derived views; contradictions still need an explicit correction.
    """
    recorded = recorded_counts(route)
    evidence = summary(route)
    values = evidence['counts']
    from .quantity_evidence import get_saved
    comparison = get_saved(route)
    result = []
    for item, count in values.items():
        provenance, source, note = (evidence[key] for key in ('provenance', 'source', 'note'))
        if provenance == 'recorded' and comparison:
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
    """Return to source evidence, including safe exact-player quantity recovery."""
    path=user_data_dir() / 'starting-items.json'
    with _WRITE_LOCK:
        data=dict(load(path))
        if key(route) in VERIFIED:
            # A null override explicitly opts out of the bundled screenshot fix.
            data[key(route)] = None
        else:
            data.pop(key(route), None)
        _write(path, data)
