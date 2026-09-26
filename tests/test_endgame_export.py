from dataclasses import asdict, replace
import time

import pytest

from dota_helper import guides, starting_items
from dota_helper.models import Purchase
from test_core import route_fixture
from test_guides import parse_kv


FINAL = ['butterfly', 'basher', 'manta', 'bfury', 'skadi', 'power_treads']


@pytest.fixture
def examples(tmp_path, monkeypatch):
    monkeypatch.setattr(starting_items, 'user_data_dir', lambda: tmp_path)
    selected = route_fixture()
    selected.patch_label = '7.40b'
    selected.start_time = int(time.time()) - 86400
    selected.final_items = []
    reference = replace(selected, id='other', match_ids=[987654321], patch_label='7.39',
                        final_items=FINAL.copy(), average_mmr=10000, source='STRATZ',
                        purchases=[Purchase('skadi', 3100)], skills=['antimage_blink'],
                        start_time=int(time.time()) - 60 * 86400,
                        warnings=['Older patch; item balance may differ.', 'Purchase times use recorded observations.'])
    return selected, reference


def test_separate_target_preserves_selected_purchases_skills_and_patch(examples):
    selected, reference = examples
    original = [asdict(route) for route in examples]
    baseline = parse_kv(guides.build_text(selected, now=0))
    exported = parse_kv(guides.build_text(selected, now=0, endgame_route=reference))
    build = dict(exported['ItemBuild'])
    categories = build['Items']
    assert categories[:-1] == dict(baseline['ItemBuild'])['Items']
    assert categories[-1] == ('Optional six-slot target · other match',
                              [('item', 'item_' + key) for key in FINAL])
    assert exported['Hero'] == baseline['Hero']
    assert exported['GameplayVersion'] == '7.40b'
    assert exported['Title'] == baseline['Title']
    overview = exported['Overview']
    assert "not the selected game's purchase order or timings" in overview
    assert '10,000 MMR' in overview and '987654321' in overview
    assert 'Patch: 7.39.' in overview
    assert 'Selected build patch: 7.40b.' in overview
    assert 'Endgame reference: Purchase times use recorded observations.' in overview
    assert not any(word in overview.lower() for word in ('older patch', 'differs from selected', 'compatibility'))
    sequence = 'Recorded skill/talent upgrade sequence'
    assert overview[overview.index(sequence):] == baseline['Overview'][baseline['Overview'].index(sequence):]
    tooltips = dict(build['ItemTooltips'])
    assert 'Reference purchase: 15:00.' in tooltips['item_bfury']
    assert 'Reference purchase:' not in tooltips['item_skadi']
    assert '987654321' in tooltips['item_skadi'] and 'Patch: 7.39.' in tooltips['item_skadi']
    assert [asdict(route) for route in examples] == original


@pytest.mark.parametrize('changes', [
    {'hero_id': 2}, {'role': 2}, {'demo': True}, {'final_items': FINAL[:5]},
    {'final_items': FINAL[:5] + ['tango']},
])
def test_invalid_reference_is_ignored_without_wrong_hero_or_role_content(examples, changes):
    selected, reference = examples
    reference = replace(reference, **changes)
    baseline = guides.build_text(selected, now=0)
    assert guides.build_text(selected, now=0, endgame_route=reference) == baseline
    assert guides.fingerprint(selected, endgame_route=reference) == guides.fingerprint(selected)
    # Ignoring an invalid separate reference also retains a valid same-game finish.
    selected.final_items = FINAL.copy()
    assert guides.build_text(selected, now=0, endgame_route=reference) == guides.build_text(selected, now=0)


def test_pro_reference_and_unknown_patch_are_identified_in_notes(examples):
    selected, reference = examples
    reference.pro_player = True
    reference.player = 'Player "Quoted"'
    reference.patch_label = ''
    reference.patch = 0
    exported = parse_kv(guides.build_text(selected, endgame_route=reference))
    assert 'PRO · Player "Quoted"' in exported['Overview']
    assert 'Patch: unknown.' in exported['Overview']
    assert 'compatibility' not in exported['Overview']
    assert 'PRO · Player "Quoted"' in dict(dict(exported['ItemBuild'])['ItemTooltips'])['item_skadi']


def test_endgame_reference_changes_fingerprint_and_atomic_export(examples, tmp_path):
    selected, reference = examples
    without = guides.fingerprint(selected)
    first = guides.fingerprint(selected, endgame_route=reference)
    assert first != without
    assert first == guides.fingerprint(selected, endgame_route=reference)
    reference.match_ids = [987654322]
    assert guides.fingerprint(selected, endgame_route=reference) != first
    path = tmp_path / guides.filename(selected)
    assert guides.write_guide(selected, path, endgame_route=reference) == path
    exported = parse_kv(path.read_text(encoding='utf-8'))
    assert '987654322' in exported['Overview']
    assert ('item', 'item_skadi') in dict(dict(exported['ItemBuild'])['Items'])['Optional six-slot target · other match']


def test_default_same_game_finish_remains_supported(examples):
    selected, _ = examples
    selected.final_items = FINAL.copy()
    exported = parse_kv(guides.build_text(selected, now=0))
    assert guides.build_text(selected, now=0, endgame_route=selected) == guides.build_text(selected, now=0)
    assert 'Six-slot finish · recorded inventory' in dict(dict(exported['ItemBuild'])['Items'])
    assert 'Optional endgame reference' in exported['Overview']
    assert 'this same game, not six additional purchases' in exported['Overview']


def test_legacy_patch_notices_do_not_follow_recent_build_into_export(examples):
    selected, _ = examples
    selected.patch_label = 'unverified (STRATZ 7.40b; bundled 7.39)'
    selected.warnings = ['OLDER PATCH: balance may differ.', 'OLDER EXAMPLE: balance may differ.',
                         'Expanded to a 60-day search.',
                         'PATCH UNVERIFIED: provider disagrees with bundled constants.',
                         'Starting inventory is unavailable.']
    exported = parse_kv(guides.build_text(selected, now=0))
    assert exported['GameplayVersion'] == '7.40b'
    assert 'Selected build patch: 7.40b.' in exported['Overview']
    assert 'Starting inventory is unavailable.' in exported['Overview']
    assert not any(word in exported['Overview'].lower() for word in ('older patch', 'older example', 'unverified', 'bundled', '60-day'))


def test_unknown_patch_notice_is_neutral_and_old_game_data_warnings_survive(examples):
    selected, _ = examples
    selected.patch_label = 'unverified (source mismatch)'
    selected.warnings = ['PATCH UNVERIFIED: source mismatch.', 'Item history is incomplete.']
    exported = parse_kv(guides.build_text(selected, now=0))
    assert exported['GameplayVersion'] == ''
    assert 'Patch unknown.' in exported['Overview']
    assert 'Item history is incomplete.' in exported['Overview']
    assert 'unverified' not in exported['Overview'].lower()
    selected.start_time = int(time.time()) - 120 * 86400
    selected.warnings.append('Older patch; item balance may differ.')
    exported = parse_kv(guides.build_text(selected, now=0))
    assert 'Older patch; item balance may differ.' in exported['Overview']
