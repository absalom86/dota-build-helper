"""Recent cached builds remain useful when patches change frequently."""
from dataclasses import asdict
import time

import pytest

from dota_helper.history import decode
from dota_helper.overlay import route_identity
from dota_helper.recency import RECENT_SECONDS, cutoff, in_recent_window
from test_core import route_fixture


@pytest.mark.parametrize('age, expected', [(0, True), (60 * 86400, True),
    (RECENT_SECONDS, True), (RECENT_SECONDS + 1, False), (-1, False)])
def test_shared_window_includes_ninety_days_without_future_games(age, expected):
    now = 1_800_000_000
    assert cutoff(now) == now - RECENT_SECONDS
    assert in_recent_window(now - age, now) is expected


@pytest.mark.parametrize('timestamp', [None, True, '1790000000', 0, float('nan'), float('inf')])
def test_missing_or_invalid_dates_are_not_treated_as_recent(timestamp):
    assert not in_recent_window(timestamp, 1_800_000_000)


def test_saved_sixty_day_build_cleans_old_patch_warnings_without_losing_evidence():
    route = route_fixture()
    route.start_time = time.time() - 60 * 86400
    route.source = 'STRATZ'
    route.patch = 0
    route.patch_label = 'unverified (STRATZ 7.40b; bundled 7.41)'
    route.warnings = [
        'OLDER EXAMPLE: 60 days old. Included from the bundled patch-date window.',
        'PATCH UNVERIFIED: STRATZ version metadata conflicts with bundled metadata.',
        'Starting quantities may be incomplete.']
    restored = decode({'hero': route.hero_id, 'role': route.role, 'routes': [asdict(route)]})[0]
    assert restored.patch_label == '7.40b'
    assert restored.warnings == ['Starting quantities may be incomplete.']
    assert restored.match_ids == route.match_ids and restored.purchases == route.purchases
    identity = route_identity(restored)
    assert '60d ago' in identity and 'Patch 7.40b' in identity
    assert 'older' not in identity.lower() and 'unverified' not in identity.lower()
