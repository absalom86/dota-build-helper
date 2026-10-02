"""Recorded talent choices placed on the bundled current hero tree."""
from .catalog import HEROES, read

TREES = read('talent_tree')['heroes']


def talent_branches(hero_id, keys):
    hero = HEROES.get(str(hero_id), {})
    tree = TREES.get(hero.get('name'), [])
    picked = set(keys)
    # The first choice at each tier describes the build. Opposite-side picks
    # learned after level 25 remain in the full sequence, not both gold branches.
    by_key = {t['key']: t for t in tree}
    first = {}
    for key in keys:
        if key in by_key:
            t = by_key[key]
            first.setdefault(t['level'], t['side'])
    branches = set(first.items())
    unknown = picked - {t['key'] for t in tree}
    return branches, unknown
