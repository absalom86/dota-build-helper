"""Actual Qt geometry checks for the click-through overlay, with no screenshot guessing."""
from itertools import combinations
from pathlib import Path
import time

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QAbstractScrollArea

from dota_helper.app import MainWindow, STYLE
from dota_helper import invoker, starting_items
from dota_helper.models import Purchase
from dota_helper.overlay import Overlay
from dota_helper.providers import Demo
from dota_helper.catalog import PATCHES


@pytest.fixture(autouse=True)
def readable_font(qt_application):
    # Qt's Windows offscreen backend does not always discover system fonts.
    added = []
    for name in ('segoeui.ttf', 'segoeuib.ttf'):
        path = Path('C:/Windows/Fonts') / name
        if path.exists():
            added.append(QFontDatabase.addApplicationFont(str(path)))
    original = qt_application.font()
    qt_application.setFont(QFont('Segoe UI', 10))
    yield
    qt_application.setFont(original)
    for font_id in added:
        if font_id >= 0:
            QFontDatabase.removeApplicationFont(font_id)


def crowded_overlay(milestones=15):
    overlay = Overlay({'overlay_layout_version': 3, 'overlay_w': 270,
                       'overlay_h': 600, 'overlay_x': 1060, 'overlay_y': 160}, STYLE)
    overlay.set_locked(True)
    overlay.hero.setText('Invoker · Mid')
    overlay.route_label.setText('PRO · Example player · 2d ago\nPatch unverified')
    overlay.clock.setText('00:00 · Game clock')
    overlay.initial_buy.setText(
        'STARTING BUY · counts unverified\nTango ×2, Iron Branch ×2 (estimated), '
        'Faerie Fire ×1, Circlet ×1, Observer Ward ×1, Sentry Ward ×1')
    overlay.initial_buy.show()
    overlay.components.setText(
        'EARLY PARTS · until 5:00\n00:45 Circlet · 01:30 Gauntlets of Strength · '
        '02:20 Mantle of Intelligence · 03:15 Ring of Protection')
    overlay.components.show()
    overlay.supplies.setText(
        'LANING SUPPLIES · until 10:00\n01:30 Tango ×2 · 02:20 Healing Salve · '
        '03:20 Clarity ×2 · 04:30 Enchanted Mango · 05:10 Faerie Fire · '
        '06:30 Infused Raindrops · 07:20 Blood Grenade')
    overlay.supplies.show()
    items = ['Magic Wand', 'Power Treads', 'Hand of Midas', 'Witch Blade',
             'Dragon Lance', 'Hurricane Pike', 'Black King Bar', "Aghanim's Scepter",
             'Octarine Core', 'Scythe of Vyse', "Shiva's Guard", 'Refresher Orb',
             'Boots of Travel (Level 2)', 'Arcane Blink', 'Moon Shard']
    overlay.set_item_lines([(f'{3 + index * 3:02}:00  {name}', index < 2)
                            for index, name in enumerate(items[:milestones])])
    overlay.skill.setText('Next upgrade: Quas')
    overlay.talents.setText('Talent picks · recorded order\n+50 Ice Wall DPS\n'
                           '+50 Forged Spirit Attack Speed\n+2 Chaos Meteors\n'
                           '+2.5s Tornado Lift Duration')
    overlay.talents.show()
    overlay.note.setText('Cached / stale')
    overlay.show_invoker(True)
    return overlay


def assert_visible_geometry(overlay, bounds):
    assert not overlay.findChildren(QAbstractScrollArea)
    assert overlay.fit_ok, f'{overlay.fit_message}; actual={overlay.geometry()}, bounds={bounds}'
    assert bounds.contains(overlay.geometry())
    labels = [widget for widget in overlay.labels if not widget.isHidden() and widget.text()]
    assert labels
    for widget in labels:
        assert overlay.rect().contains(widget.geometry()), widget.text()
        assert widget.height() >= widget.heightForWidth(widget.width()), widget.text()
    for first, second in combinations(labels, 2):
        assert not first.geometry().intersects(second.geometry()), (first.text(), second.text())


@pytest.mark.parametrize('bounds', [QRect(0, 0, 2560, 1440), QRect(0, 0, 1366, 768),
                                  QRect(0, 0, 1280, 720)],
                         ids=['tall', 'short', '720p'])
@pytest.mark.parametrize('milestones', [10, 15])
def test_crowded_invoker_all_sections_fit_below_game_stats(qt_application, bounds, milestones):
    overlay = crowded_overlay(milestones)
    try:
        overlay.show()
        qt_application.processEvents()
        overlay.fit_content(bounds)
        qt_application.processEvents()
        assert overlay.y() == 160
        assert len(overlay.item_lines) == milestones
        assert all(name in overlay.invoker_spells.text() for name, _ in invoker.SPELLS)
        assert_visible_geometry(overlay, bounds)
    finally:
        overlay.close()


def test_auto_fit_preserves_preferred_width_across_hidden_resize_and_show(qt_application):
    overlay = crowded_overlay(10)
    short = QRect(0, 0, 1366, 768)
    tall = QRect(0, 0, 2560, 1440)
    try:
        overlay.show()
        qt_application.processEvents()
        preferred = overlay.preferred_width
        overlay.fit_content(short)
        qt_application.processEvents()
        assert overlay.width() > preferred
        assert overlay.preferred_width == preferred
        overlay.hide()
        overlay.fit_content(tall)
        overlay.show()
        qt_application.processEvents()
        assert overlay.preferred_width == preferred
        overlay.hide()
        overlay.fit_content(short)
        overlay.show()
        qt_application.processEvents()
        assert overlay.preferred_width == preferred
        # A real user width change is retained, unlike an automatic fit.
        manual_width = 450 if overlay.width() != 450 else 390
        overlay.resize(manual_width, overlay.height())
        qt_application.processEvents()
        assert overlay.preferred_width == manual_width
    finally:
        overlay.close()


def test_height_only_resize_is_repaired_without_waiting_for_clock_change(qt_application):
    overlay = crowded_overlay(10)
    bounds = QRect(0, 0, 2560, 1440)
    try:
        overlay.show()
        qt_application.processEvents()
        overlay.fit_content(bounds)
        original_height = overlay.height()
        original_preferred = overlay.preferred_width
        overlay.resize(overlay.width(), original_height // 2)
        qt_application.processEvents()
        # Text and game clock deliberately remain unchanged, as in a paused game.
        overlay.fit_content(bounds)
        qt_application.processEvents()
        assert overlay.height() == original_height
        assert overlay.preferred_width == original_preferred
        assert_visible_geometry(overlay, bounds)
    finally:
        overlay.close()


def test_large_font_keeps_user_size_and_reports_any_screen_limit(qt_application):
    overlay = crowded_overlay(15)
    bounds = QRect(0, 0, 1280, 720)
    try:
        overlay.font_size = 16
        overlay.show()
        qt_application.processEvents()
        overlay.fit_content(bounds)
        assert overlay.font_size == 16
        assert overlay.items.font().pixelSize() == 16
        assert len(overlay.item_lines) == 15
        assert all(name in overlay.invoker_spells.text() for name, _ in invoker.SPELLS)
        if overlay.fit_ok:
            assert_visible_geometry(overlay, bounds)
        else:
            # Oversized content must be disclosed, never silently hidden or shrunk.
            assert not bounds.contains(overlay.geometry())
            assert 'More room needed' in overlay.fit_message
            for widget in overlay.labels:
                if not widget.isHidden() and widget.text():
                    assert overlay.rect().contains(widget.geometry())
    finally:
        overlay.close()


def test_preview_width_control_tracks_manual_resize_without_saving_auto_fit(tmp_path, monkeypatch,
                                                                          qt_application):
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    monkeypatch.setattr('dota_helper.app.dota_active', lambda: False)
    window = MainWindow(start_services=False)
    try:
        window.timer.stop()
        window.capture_timer.stop()
        window.draft.meta_active = False
        window.preview.setChecked(True)
        window.tick()
        qt_application.processEvents()
        manual_width = 450 if window.overlay.width() != 450 else 390
        window.overlay.resize(manual_width, window.overlay.height())
        qt_application.processEvents()
        window.tick()
        assert window.overlay_width.value() == manual_width
        assert window.overlay.preferred_width == manual_width
        window.preview.setChecked(False)
        window.tick()
        window.preview.setChecked(True)
        window.tick()
        qt_application.processEvents()
        assert window.overlay_width.value() == manual_width
        assert window.overlay.preferred_width == manual_width
    finally:
        window.close()


def test_selected_route_identity_and_expiring_sections_reach_overlay(tmp_path, monkeypatch):
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    monkeypatch.setattr(starting_items, 'user_data_dir', lambda: tmp_path)
    monkeypatch.setattr('dota_helper.app.dota_active', lambda: False)
    window = MainWindow(start_services=False)
    try:
        window.timer.stop()
        window.capture_timer.stop()
        window.draft.meta_active = False
        window.hero.setCurrentIndex(window.hero.findData(74))
        window.role.setCurrentIndex(window.role.findData(2))
        route = Demo().routes(1, 1, 0)[0][0]
        route.hero_id = 74
        route.role = 2
        route.demo = False
        route.average_mmr = 8123
        route.player = 'Private pub player'
        route.start_time = int(time.time()) - 2 * 86400
        route.patch_label = 'unverified (source mismatch)'
        route.purchases = [Purchase('tango', -60), Purchase('circlet', 120),
                           Purchase('flask', 420), Purchase('flask', 450, 2),
                           Purchase('manta', 1200)]
        window.routes = [route]
        window.session.accept_routes([route])
        window.tick()
        identity = window.overlay.route_label.text()
        assert '8,123 MMR' in identity and '2d ago' in identity
        assert 'Patch unverified' in identity and route.player not in identity
        assert not window.overlay.initial_buy.isHidden()
        assert not window.overlay.components.isHidden()
        assert 'Healing Salve ×2' in window.overlay.supplies.text()
        assert not window.overlay.invoker_spells.isHidden()
        route.pro_player = True
        route.player = 'Professional player'
        route.patch = PATCHES[-1]['id']
        route.patch_label = PATCHES[-1]['name']
        route.warnings = []
        window.manual_second = 420
        window.tick()
        assert 'PRO · Professional player' in window.overlay.route_label.text()
        assert '8,123 MMR' not in window.overlay.route_label.text()
        assert f"Patch {PATCHES[-1]['name']}" in window.overlay.route_label.text()
        assert window.overlay.initial_buy.isHidden() and window.overlay.components.isHidden()
        assert not window.overlay.supplies.isHidden()
        window.manual_second = 600
        window.tick()
        assert window.overlay.supplies.isHidden()
        assert 'Manta Style' in window.overlay.items.text()
    finally:
        window.close()
