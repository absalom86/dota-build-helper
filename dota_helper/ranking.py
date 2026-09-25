"""Patch evidence precedes observed source preferences in every route list."""
import re

from .catalog import PATCHES


RANKING_DESCRIPTION = ('verified current patch → unknown patch → older patch; '
                       'premier events → other tournaments → pro players → pubs within each group')


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
    return patch_group(route), tier, route.start_time


def ranked(routes, limit=10):
    """Use metadata we have; no inferred team strength or numeric pub ranking."""
    unique = {route.id: route for route in routes}
    return sorted(unique.values(), key=route_key, reverse=True)[:limit]
