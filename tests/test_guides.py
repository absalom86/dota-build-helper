from pathlib import Path
import re

import pytest

from dota_helper import guides, starting_items
from dota_helper.models import Purchase
from dota_helper.providers import Demo


def parse_kv(text):
    """Independent small KeyValues reader retaining repeated keys like 'item'."""
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[{}]', text)
    position = 0

    def string():
        nonlocal position
        token = tokens[position]
        position += 1
        assert token.startswith('"') and token.endswith('"')
        return re.sub(r'\\(.)', r'\1', token[1:-1])

    def block():
        nonlocal position
        result = []
        assert tokens[position] == '{'
        position += 1
        while tokens[position] != '}':
            key = string()
            value = block() if tokens[position] == '{' else string()
            result.append((key, value))
        position += 1
        return result

    assert string() == 'guidedata'
    result = dict(block())
    assert position == len(tokens)
    return result


@pytest.fixture
def route(tmp_path, monkeypatch):
    monkeypatch.setattr(starting_items, 'user_data_dir', lambda: tmp_path)
    route = Demo().routes(1, 1, 0)[0][0]
    route.demo = False
    route.match_ids = [12345678]
    route.patch_label = '7.40b'
    return route


def test_native_guide_preserves_quantities_order_timings_and_skill_notes(route):
    route.purchases.extend([Purchase('flask', 200), Purchase('flask', 1000), Purchase('ward_sentry', 1200)])
    route.skills.append('special_bonus_unique_antimage')
    result = parse_kv(guides.build_text(route, now=1780000000))
    assert result['Hero'] == 'antimage'
    assert result['GuideFormatVersion'] == '2'
    assert result['GameplayVersion'] == '7.40b'
    assert result['TimeUpdated'] == '0x000000006A18A500'
    item_build = dict(result['ItemBuild'])
    sections = dict(item_build['Items'])
    assert sections['Starting items'].count(('item', 'item_branches')) == 2
    assert sections['Laning supplies · 0–10 min'] == [('item', 'item_flask')]
    flattened = [value for key, items in item_build['Items']
                 if key not in ('Starting items', 'Laning supplies · 0–10 min') for _, value in items]
    assert flattened == ['item_boots', 'item_power_treads', 'item_bfury', 'item_manta', 'item_basher']
    assert '15:00' in dict(item_build['ItemTooltips'])['item_bfury']
    assert 'Recorded skill/talent' in result['Overview']
    assert 'AbilityBuild' not in result  # Upgrade sequence must not be exported as hero levels.


def test_guide_retains_laning_supplies_with_repeated_quantities_and_timings(route):
    route.purchases = [
        Purchase('tango', -60), Purchase('boots', 100), Purchase('circlet', 299),
        Purchase('flask', 299), Purchase('flask', 301, 2), Purchase('flask', 301, 3),
        Purchase('ward_observer', 350), Purchase('ward_dispenser', 360),
        Purchase('tpscroll', 400), Purchase('smoke_of_deceit', 450), Purchase('dust', 500),
        Purchase('infused_raindrop', 599), Purchase('clarity', 600),
        Purchase('gauntlets', 700), Purchase('recipe_manta', 800), Purchase('manta', 1200),
    ]
    original = [vars(p).copy() for p in route.purchases]
    result = parse_kv(guides.build_text(route))
    item_build = dict(result['ItemBuild'])
    sections = dict(item_build['Items'])
    assert sections['Starting items'] == [('item', 'item_tango')]
    assert sections['Laning supplies · 0–10 min'] == [
        ('item', 'item_flask'), ('item', 'item_flask'), ('item', 'item_flask'),
        ('item', 'item_infused_raindrop'),
    ]
    assert sections['First 5 minutes'] == [('item', 'item_boots'), ('item', 'item_circlet')]
    assert sections['Mid game · 15–30 min'] == [('item', 'item_manta')]
    assert len(sections) == 4
    tooltips = dict(item_build['ItemTooltips'])
    assert tooltips['item_flask'] == (
        'Reference purchase: 04:59. Reference purchase: 05:01. Reference purchase: 05:01.')
    assert tooltips['item_infused_raindrop'] == 'Reference purchase: 09:59.'
    assert [vars(p) for p in route.purchases] == original


def test_corrections_and_estimates_export_consistently(route):
    route.purchases = [Purchase('branches', -30), Purchase('boots', 100)]
    route.source = 'STRATZ'
    estimated = parse_kv(guides.build_text(route))
    assert dict(dict(estimated['ItemBuild'])['Items'])['Starting items'].count(('item', 'item_branches')) == 2
    assert 'estimated' in estimated['Overview'] and 'incomplete' in estimated['Overview']
    starting_items.save(route, {'branches': 5, 'ward_observer': 1})
    corrected = parse_kv(guides.build_text(route))
    initial = dict(dict(corrected['ItemBuild'])['Items'])['Starting items']
    assert initial.count(('item', 'item_branches')) == 5
    assert ('item', 'item_ward_observer') in initial
    assert 'incomplete' not in corrected['Overview'] and 'estimated' not in corrected['Overview']


def test_names_are_escaped_and_files_stay_distinct(route):
    route.pro_player = True
    route.player = 'Player "Quoted" \\ } {\n"Hero" "doom_bringer"'
    parsed = parse_kv(guides.build_text(route))
    assert parsed['Hero'] == 'antimage'
    assert route.player in parsed['Title']
    first_name = guides.filename(route)
    assert re.fullmatch(r'antimage_\d+\.build', first_name)
    assert 0 < int(first_name.split('_')[-1].split('.')[0]) <= 0x7FFFFFFF
    assert guides.filename(route) == first_name
    route.id = 'other-match'
    assert guides.filename(route) != first_name


def test_unknown_and_demo_patch_are_not_stamped_as_a_real_patch(route):
    route.patch_label = ''
    route.patch = 0
    assert parse_kv(guides.build_text(route))['GameplayVersion'] == ''
    route.demo = True
    route.patch_label = '7.40b'
    assert parse_kv(guides.build_text(route))['GameplayVersion'] == ''


def test_atomic_export_keeps_existing_guide_on_failure(route, tmp_path, monkeypatch):
    path = tmp_path / guides.filename(route)
    guides.write_guide(route, path)
    original = path.read_bytes()
    assert parse_kv(original.decode('utf-8'))['Hero'] == 'antimage'
    def fail(*args):
        raise PermissionError('blocked')
    monkeypatch.setattr(Path, 'replace', fail)
    with pytest.raises(PermissionError):
        guides.write_guide(route, path)
    assert path.read_bytes() == original
    assert list(tmp_path.glob('*.tmp')) == []
    with pytest.raises(ValueError):
        guides.write_guide(route, tmp_path / 'wrong.txt')


def test_discovery_includes_all_dota_accounts_only(tmp_path):
    for name in ['123', '456', 'not-an-account']:
        (tmp_path / 'userdata' / name / '570').mkdir(parents=True)
    (tmp_path / 'userdata' / '789').mkdir()
    expected = [tmp_path / 'userdata' / number / '570' / 'remote' / 'guides' for number in ['123', '456']]
    assert guides.guide_directories([tmp_path, tmp_path]) == expected


def test_ui_exports_selected_route_and_cancel_writes_nothing(tmp_path, monkeypatch):
    from dota_helper.app import MainWindow, QFileDialog, QMessageBox
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    monkeypatch.setattr(guides, 'guide_directories', lambda: [])
    window = MainWindow(start_services=False)
    window.routes = Demo().routes(1, 1, 0)[0]
    window.session.accept_routes(window.routes)
    window.session.choose(window.routes[1].id)
    window.tick()
    assert window.export_guide_button.isEnabled()
    path = tmp_path / guides.filename(window.current_route())
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(path), ''))
    messages = []
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: messages.append(args[-1]))
    window.export_shop_guide()
    exported = parse_kv(path.read_text(encoding='utf-8'))
    items = dict(exported['ItemBuild'])['Items']
    assert ('item', 'item_black_king_bar') in [item for _, section in items for item in section]
    assert 'Restart Dota' in messages[0]
    assert 'SYNTHETIC OFFLINE DEMO' in exported['Overview']
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: ('', ''))
    window.export_shop_guide()
    assert len(messages) == 1
    window.close()
