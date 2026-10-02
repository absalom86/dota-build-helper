"""Recent games are compared by professional status and observed match rating."""
import re
from dataclasses import replace

from .catalog import PATCHES
from .ratings import numeric_mmr, match_rank, rank_tier
from .recency import in_recent_window


RANKING_DESCRIPTION = ('last 90 days across patches; '
                       'premier events → other tournaments → pro players → pubs; rated pubs by MMR, then rank brackets high to low, unknown last')


def patch_group(route):
    """2=current, 1=unknown/conflicting, 0=verified older bundled patch.

    A recent date, a professional player, or a source version label alone never
    certifies a patch. Explicit provider conflicts override the numeric ID.
    """
    # The app uses zero as its unavailable-patch sentinel, despite the historical
    # constants catalogue also assigning zero to the now-ancient 6.70 patch.
    if not route.patch:
        return 1
    label = route.patch_label.lower()
    if 'unverified' in label or any('PATCH UNVERIFIED' in warning.upper() for warning in route.warnings):
        return 1
    known = next((patch for patch in PATCHES if patch['id'] == route.patch), None)
    if known is None:
        return 1
    named = re.fullmatch(r'(\d+\.\d+)[a-z]?', label.strip()) if label else None
    if label and (named is None or named[1] != known['name']):
        return 1
    return 2 if route.patch == PATCHES[-1]['id'] else 0


def route_key(route):
    tier = (3 if route.tournament and 'PREMIER' in route.evidence else
            2 if route.tournament else 1 if route.pro_player else 0)
    mmr = numeric_mmr(route.average_mmr) if tier == 0 and not route.demo else None
    rank = match_rank(route) if tier == 0 and not route.demo else None
    # Keep incomparable measurement types separate; never equate a medal to MMR.
    rating_group = 2 if mmr is not None else 1 if rank is not None else 0
    return int(in_recent_window(route.start_time)), tier, rating_group, mmr if mmr is not None else rank or 0, route.start_time


def build_signature(route):
    """Count build variety without removing separately recorded games."""
    slots = route.final_items
    final_items = tuple(slots) if isinstance(slots, list) and all(isinstance(key, str) for key in slots) else ()
    return tuple(p.key for p in route.purchases), tuple(route.skills), final_items


def game_identity(route):
    """Match providers without relying on their sometimes-missing player slots."""
    ids = route.match_ids
    if not route.demo and isinstance(ids, (list, tuple)) and len(ids) == 1:
        mid = ids[0]
        if isinstance(mid, str) and re.fullmatch(r'[1-9][0-9]{0,19}', mid):
            mid = int(mid)
        if (type(mid) is int and 0 < mid < 2 ** 64
                and type(route.hero_id) is int and route.hero_id > 0
                and type(route.role) is int and 1 <= route.role <= 5):
            return ('game', mid, route.hero_id, route.role)
    # Demo and aggregated routes describe something other than one exact game.
    return ('route', route.id)


def _retain_averages(route, observations):
    """Keep exact-game measurements when replacing build details or providers.

    Selecting a source chooses its purchases and skills, not which separately
    observed match averages survive. Conflicting measurements are never guessed.
    """
    if route.demo or route.tournament or game_identity(route)[0] != 'game':
        return route
    donors = [other for other in observations if not other.demo and not other.tournament]
    accounts = {other.account_id for other in donors
                if type(other.account_id) is int and other.account_id > 0}
    if type(route.account_id) is int and route.account_id > 0:
        donors = [other for other in donors if other.account_id is None or other.account_id == route.account_id]
    elif len(accounts) > 1:
        return route
    updates = {}
    for field, validate, fallback in (
        ('average_mmr', numeric_mmr, 'supplied match average MMR'),
        ('average_rank', lambda value: rank_tier(value, average=True), 'supplied match average rank'),
    ):
        if validate(getattr(route, field)) is not None:
            continue
        available = [(other, validate(getattr(other, field))) for other in donors]
        available = [(other, value) for other, value in available if value is not None]
        if len({value for _, value in available}) != 1:
            continue
        donor, value = available[-1]
        updates[field] = value
        updates[field + '_source'] = getattr(donor, field + '_source') or f'{donor.source} {fallback}'
    return replace(route, **updates) if updates else route


def ranked(routes, limit=None, *, preferred_id=None):
    """Keep one source per game, preserving an explicitly chosen source and ID."""
    routes = list(routes)
    observations = {}
    for route in routes:
        observations.setdefault(game_identity(route), []).append(route)
    # Replace old details for the same source ID before resolving provider overlap.
    latest = {route.id: (index, route) for index, route in enumerate(routes)}
    unique = {}
    for index, route in latest.values():
        identity = game_identity(route)
        priority = (route.id == preferred_id, route_key(route), index)
        if identity not in unique or priority > unique[identity][0]:
            unique[identity] = (priority, route)
    ordered = sorted((_retain_averages(value[1], observations[identity])
                      for identity, value in unique.items()), key=route_key, reverse=True)
    return ordered[:limit]
