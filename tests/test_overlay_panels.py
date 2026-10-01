import json

import pytest
from PySide6.QtCore import QRect

from dota_helper.app import MainWindow
from test_overlay_bounds import readable_overlay_font


@pytest.fixture
def panels(tmp_path, monkeypatch):
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    monkeypatch.setenv('DOTA_HELPER_HOME', str(tmp_path))
    monkeypatch.setattr('dota_helper.app.dota_active', lambda: False)
    window = MainWindow(start_services=False)
    window.timer.stop()
    window.capture_timer.stop()
    window.draft.meta_active = False
    window.preview.setChecked(True)
    window.hero.setCurrentIndex(window.hero.findData(145))
    window.tick()
    yield window
    window.close()


@pytest.mark.parametrize('hero,field', [(145,'kez_combos'), (74,'invoker_spells'), (27,'shadow_shaman_tips')])
def test_hero_panel_is_independent_and_optional(panels, hero, field):
    window = panels
    window.hero.setCurrentIndex(window.hero.findData(hero))
    window.tick()
    main, reference = window.overlay, window.hero_overlay
    assert main.isVisible() and reference.isVisible()
    assert main.isWindow() and reference.isWindow()
    assert getattr(reference, field).isVisible()
    assert reference.clock.isHidden() and reference.route_label.isHidden()
    assert not getattr(main, field).isVisible()
    assert main.build_tab.isHidden() and main.reference_tab.isHidden()
    note = main.note.text()
    main.note.setText('')
    main.fit_content()
    assert main.note.geometry().isEmpty()  # Empty labels must not overpaint the skill card.
    main.note.setText(note)
    main.fit_content()
    main_geometry = main.geometry()
    window.toggle_hero_overlay()
    assert not reference.isVisible() and main.isVisible()
    assert main.geometry() == main_geometry
    assert json.loads(window.settings_file.read_text())['hero_references'] is False
    window.toggle_hero_overlay()
    assert reference.isVisible()
    window.hero.setCurrentIndex(window.hero.findData(1))
    window.tick()
    assert main.isVisible() and not reference.isVisible()


@pytest.mark.parametrize('bounds', [QRect(0,0,1920,1040), QRect(0,0,1536,824), QRect(0,0,1280,680)])
def test_panels_fit_and_scroll_independently(panels, bounds):
    main, reference = panels.overlay, panels.hero_overlay
    main.move(bounds.right()-main.width()-12, 160)
    reference.move(main.x()-reference.width()-12,160)
    main.set_item_lines([(f'{i}:00 Item {i}',False) for i in range(100)])
    reference.font_size = 16  # Force overflow even at 100% scaling.
    main.fit_content(bounds)
    reference.fit_content(bounds)
    for panel in (main,reference):
        assert bounds.contains(panel.geometry())
        assert panel.width() == 270
        assert panel.height() <= min(560,int(bounds.height()*.62))
    assert not main.geometry().intersects(reference.geometry())
    main.set_locked(True)
    reference.set_locked(True)
    main.show()
    reference.show()
    panels.scroll_overlay(1)
    build_offset = main.overflow_bar.value()
    assert build_offset > 0
    assert reference.overflow_bar.value() == 0
    panels.scroll_hero_overlay(1)
    assert reference.overflow_bar.value() > 0
    assert main.overflow_bar.value() == build_offset
    panels.scroll_hero_overlay(0)
    assert reference.overflow_bar.value() == 0
    assert main.overflow_bar.value() == build_offset


def test_panel_settings_and_shared_visibility(panels, monkeypatch):
    window = panels
    window.hero_overlay.move(70,110)
    window.hero_overlay.preferred_y = 110
    window.hero_overlay.preferred_width = 330
    window.save_settings()
    saved = json.loads(window.settings_file.read_text())
    assert (saved['hero_overlay_x'],saved['hero_overlay_y'],saved['hero_overlay_w']) == (70,110,330)
    window.overlay_enabled.setChecked(False)
    window.tick()
    assert not window.overlay.isVisible() and not window.hero_overlay.isVisible()
    window.overlay_enabled.setChecked(True)
    window.preview.setChecked(False)
    window.tick()
    assert not window.overlay.isVisible() and not window.hero_overlay.isVisible()
    monkeypatch.setattr('dota_helper.app.dota_active',lambda:True)
    window.tick()
    assert window.overlay.isVisible() and window.hero_overlay.isVisible()
    assert window.overlay.locked and window.hero_overlay.locked
    window.close()
    assert not window.overlay.isVisible() and not window.hero_overlay.isVisible()
