"""Shared build-search window, independent of frequent game patches."""
import math
import re
import time


RECENT_DAYS = 90
RECENT_SECONDS = RECENT_DAYS * 86400


def cutoff(now=None):
    return (time.time() if now is None else now) - RECENT_SECONDS


def in_recent_window(timestamp, now=None):
    if type(timestamp) not in (int, float):
        return False
    try:
        valid = math.isfinite(timestamp)
    except OverflowError:
        return False
    now = time.time() if now is None else now
    return valid and timestamp > 0 and cutoff(now) <= timestamp <= now


def neutral_patch_label(route):
    """Show the source's version without comparing it to bundled constants."""
    label = str(route.patch_label or '').strip()
    if re.fullmatch(r'\d+\.\d+[a-z]?', label, re.IGNORECASE):
        return label.lower()
    # Older saved searches wrapped a valid provider version in a mismatch note.
    provider = re.match(r'^unverified\s*\(\s*STRATZ\s+(\d+\.\d+[a-z]?)(?=\s*[;)])',
                        label, re.IGNORECASE)
    if provider:
        return provider[1].lower()
    if any(word in label.lower() for word in ('unverified', 'conflict', 'mismatch')):
        return 'unknown'
    from .catalog import PATCHES
    if route.patch:
        known = next((patch['name'] for patch in PATCHES if patch['id'] == route.patch), None)
        if known:
            return known
    return 'unknown'


def presentation_warnings(route, now=None):
    """Keep data caveats while retiring obsolete patch-age notices for recent games."""
    recent = in_recent_window(route.start_time, now)
    result = []
    for warning in route.warnings:
        folded = warning.strip().lower()
        if folded.startswith(('patch unverified', 'patch unknown')):
            if neutral_patch_label(route) == 'unknown' and 'Patch unknown.' not in result:
                result.append('Patch unknown.')
            continue
        if recent and (folded.startswith(('older patch', 'older example:', 'expanded to a 60-day'))
                       or folded.startswith('current-patch compatibility')
                       or (folded.startswith('endgame reference patch')
                           and ('compatibility is unverified' in folded
                                or 'differs from selected build patch' in folded))):
            continue
        result.append(warning)
    return result
