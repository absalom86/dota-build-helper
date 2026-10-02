from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

from PySide6.QtCore import QEventLoop, QTimer

from dota_helper.ability_icons import AbilityIcons, icon_url
from dota_helper.catalog import DATA
from dota_helper.models import Session
from dota_helper.skill_strip import SkillStrip
from test_core import route_fixture


def test_strip_shows_repeated_picks_and_advances_window(tmp_path, qt_application):
    icons = AbilityIcons(tmp_path, online=False)
    strip = SkillStrip()
    strip.setWordWrap(True)
    strip.set_icon_cache(icons)
    route = route_fixture()
    route.skills = ['antimage_mana_break', 'antimage_blink', 'antimage_counterspell'] * 5
    session = Session()
    strip.set_route(session, route)
    strip.resize(254, strip.heightForWidth(254))
    strip.show()
    qt_application.processEvents()
    assert strip.window_indices(254) == (0, 9)
    assert strip.next_index == 0
    assert len(strip.hitboxes) == 10  # Nine upgrades leave room for the circular talent badge.
    assert all(strip.rect().contains(rect) for rect, _ in strip.hitboxes)
    session.learned = Counter(route.skills[:10])
    strip.set_route(session, route)
    qt_application.processEvents()
    assert strip.next_index == 10
    assert strip.window_indices(254) == (9, 15)
    assert strip.progress == session.skill_progress(route)
    assert strip.heightForWidth(254) == 48
    strip.setText('Draft suggestions')
    assert strip.progress is None  # A prior route must not paint over draft guidance.
    strip.close()
    icons.close()


def test_conflicts_unknown_icons_and_talents_keep_evidence(tmp_path, qt_application):
    strip = SkillStrip()
    strip.set_icon_cache(AbilityIcons(tmp_path, online=False))
    route = route_fixture()
    route.skills = ['missing_skill', 'special_bonus_attributes', 'special_bonus_unique_antimage_5']
    session = Session()
    session.learned['special_bonus_different_talent'] = 1
    strip.set_route(session, route)
    strip.resize(254, strip.heightForWidth(254))
    strip.show()
    qt_application.processEvents()
    assert strip.next_index is None
    assert 'differ' in strip.warning
    assert any('Missing Skill' in tip for _, tip in strip.hitboxes)
    talent_tip = strip.hitboxes[-1][1]
    assert 'Recorded talent picks' in talent_tip and 'Gold = first recorded pick' in talent_tip
    assert 'Attributes' not in talent_tip
    route.skills = []
    strip.set_route(session, route)
    strip.grab()
    assert strip.hitboxes == []
    strip.close()


def test_four_tier_tree_fills_recorded_sides_and_marks_missing(qt_application):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QImage, QPainter
    from dota_helper.talents import talent_branches
    keys = ['special_bonus_unique_kez_raptor_dance_radius', 'special_bonus_unique_kez_falcon_rush_duration']
    branches, unknown = talent_branches(145, keys)
    assert branches == {(10, 'left'), (15, 'right')} and not unknown
    assert talent_branches(145, ['special_bonus_removed_talent'])[1] == {'special_bonus_removed_talent'}
    image = QImage(40, 40, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    SkillStrip._tree(painter, QRect(0, 0, 40, 40), branches)
    painter.end()
    assert image.pixelColor(11, 31).red() > image.pixelColor(11, 31).blue() * 1.5  # Level 10 left branch.
    assert image.pixelColor(32, 24).red() > image.pixelColor(32, 24).blue() * 1.5  # Level 15 right branch.
    assert image.pixelColor(8, 7).red() < image.pixelColor(8, 7).blue() * 1.5  # No invented level 25 choice.
    route = route_fixture()
    route.hero_id = 145
    route.skills = ['kez_echo_slash', 'dota_base_ability']
    strip = SkillStrip()
    strip.set_route(Session(), route)
    strip.resize(254, 48)
    strip.grab()
    assert 'Not available from this source' in strip.hitboxes[-1][1]
    strip.close()


def test_safe_icon_names_and_bundled_offline_image(tmp_path):
    icons = AbilityIcons(tmp_path, online=False)
    for key in ('../secret', 'http://example.com/a', 'a/b', 'x?token=secret', 'special_bonus_attributes'):
        assert icon_url(key) is None
        assert icons.get(key).isNull()
    assert not icons.get('antimage_blink').isNull()
    assert not icons.pending and not icons.queue
    icons.close()


def test_async_image_download_is_cached_and_reused_offline(tmp_path, monkeypatch, qt_application):
    data = (DATA / 'ability_icons' / 'antimage_blink.png').read_bytes()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(data)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr('dota_helper.ability_icons.icon_url', lambda key: f'http://127.0.0.1:{server.server_port}/{key}.png')
    icons = AbilityIcons(tmp_path)
    try:
        loop = QEventLoop()
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        icons.changed.connect(loop.quit)
        assert icons.get('test_ability').isNull()  # Caller is not blocked on HTTP.
        timeout.start(3000)
        loop.exec()
        timeout.stop()
        assert not icons.get('test_ability').isNull()
        assert (tmp_path / 'test_ability.png').read_bytes() == data
        offline = AbilityIcons(tmp_path, online=False)
        assert not offline.get('test_ability').isNull()
        offline.close()
    finally:
        icons.close()
        server.shutdown()
        server.server_close()
        thread.join()
