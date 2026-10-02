from collections import Counter

import pytest

from dota_helper.models import Session
from dota_helper.ratings import numeric_mmr, rating_text, rating_help
from dota_helper.skill_display import overlay_skill_text, skill_order_html
from test_core import match_fixture, route_fixture
from dota_helper.builds import normalize


@pytest.mark.parametrize('value', [None, '8000', True, -10, 30000, float('nan'), float('inf')])
def test_invalid_mmr_is_unknown(value):
    route = route_fixture()
    route.average_mmr = value
    assert numeric_mmr(value) is None
    assert rating_text(route) == 'Rank unknown'


def test_match_average_is_not_rank_tier_or_profile_mmr():
    data = match_fixture()
    data.update(avg_rank_tier=80, rank=80)
    data['players'][0]['mmr_estimate'] = {'estimate': 9000}
    assert normalize(data, data['players'][0], 'fixture').average_mmr is None
    data['avg_mmr'] = 8123.6
    route = normalize(data, data['players'][0], 'fixture')
    assert route.average_mmr == 8123
    assert rating_text(route) == '8,123 MMR'
    assert 'match average' in rating_help(route)


def test_repeated_skill_picks_progress_individually_and_preview_advances():
    route = route_fixture()
    route.skills = ['antimage_mana_break', 'antimage_blink', 'antimage_mana_break', 'antimage_counterspell']
    session = Session()
    session.learned = Counter(antimage_mana_break=1)
    assert session.skill_progress(route) == [(route.skills[0], True), (route.skills[1], False),
                                            (route.skills[2], False), (route.skills[3], False)]
    assert overlay_skill_text(session, route).startswith('NEXT SKILL\nBlink\nThen: Mana Break')
    html = skill_order_html(session, route)
    assert '✓ Mana Break' in html and '▶ Blink · next' in html
    assert 'not hero levels' in html
    session.learned['antimage_blink'] = 1
    assert overlay_skill_text(session, route).startswith('NEXT SKILL\nMana Break')
    session.learned = Counter(route.skills)
    assert overlay_skill_text(session, route) == 'Recorded upgrade sequence complete'


def test_talent_conflict_does_not_recommend_impossible_next_pick():
    route = route_fixture()
    session = Session()
    session.learned['special_bonus_conflicting_talent'] = 1
    assert 'differ' in overlay_skill_text(session, route)
    assert 'NEXT SKILL' not in skill_order_html(session, route)
