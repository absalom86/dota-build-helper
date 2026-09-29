"""Hero-specific reference and real Qt geometry regressions for Kez."""
from itertools import combinations
from pathlib import Path

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QFont, QFontDatabase, QTextDocument

from dota_helper import invoker, kez, shadow_shaman
from dota_helper.app import MainWindow, STYLE
from dota_helper.overlay import Overlay


@pytest.fixture(autouse=True)
def readable_font(qt_application):
    added = []
    for name in ('segoeui.ttf', 'segoeuib.ttf'):
        path = Path('C:/Windows/Fonts') / name
        if path.exists():
            added.append(QFontDatabase.addApplicationFont(str(path)))
    previous = qt_application.font()
    qt_application.setFont(QFont('Segoe UI', 10))
    yield
    qt_application.setFont(previous)
    for font_id in added:
        if font_id >= 0:
            QFontDatabase.removeApplicationFont(font_id)


def plain_reference(columns):
    document = QTextDocument()
    document.setHtml(kez.reference_html(columns=columns))
    return document.toPlainText()


@pytest.mark.parametrize('columns', [1, 2])
def test_reference_explains_stages_stances_and_default_keys(columns):
    text = plain_reference(columns)
    for heading in ('EARLY GAME', 'MID GAME', 'AGHANIM', 'DEFENSE'):
        assert heading in text.upper()
    for instruction in ('Katana', 'Sai', 'Q Echo / Rush', 'W Claw / Toss',
                        'E Impale / Parry', 'R Dance / Veil'):
        assert instruction in text
    assert 'default' in text.lower()
    assert 'D' in text and 'Q' in text and 'W' in text and 'R' in text
    # Never present these static practice sequences as a live cooldown signal.
    assert 'ready' in text.lower()
    assert '3s' in text or '3 seconds' in text
    for _, combos in kez.STAGES:
        assert all(combo.keys in text for combo in combos)


def test_hero_reference_follows_selection_without_fetch_and_hides_during_draft(
        tmp_path, monkeypatch, qt_application):
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    monkeypatch.setattr('dota_helper.app.dota_active', lambda: False)
    window = MainWindow(start_services=False)
    try:
        window.timer.stop()
        window.capture_timer.stop()
        window.draft.meta_active = False
        window.hero.setCurrentIndex(window.hero.findData(kez.HERO_ID))
        window.tick()
        qt_application.processEvents()
        assert not window.routes
        assert window.overlay.kez_active and not window.overlay.kez_combos.isHidden()
        assert not window.overlay.invoker_active and window.overlay.invoker_spells.isHidden()
        assert 'AGHANIM' in window.overlay.kez_combos.text().upper()
        details = window.overlay.kez_combos.toolTip()
        for name in ('Echo Slash', 'Falcon Rush', 'Grappling Claw', 'Talon Toss',
                     'Kazurai Katana', 'Shodo Sai', 'Raptor Dance', 'Raven'):
            assert name in details
        assert 'cooldown' in details.lower()
        assert window.overlay.fit_ok

        monkeypatch.setattr(window.draft, 'overlay_text', lambda: ('Enemies', 'Suggestions', 'Note'))
        window.tick()
        assert not window.overlay.kez_active and window.overlay.kez_combos.isHidden()
        monkeypatch.setattr(window.draft, 'overlay_text', lambda: None)
        window.tick()
        assert window.overlay.kez_active and not window.overlay.kez_combos.isHidden()

        window.hero.setCurrentIndex(window.hero.findData(invoker.HERO_ID))
        window.tick()
        assert window.overlay.kez_combos.isHidden() and not window.overlay.kez_active
        assert window.overlay.invoker_active and not window.overlay.invoker_spells.isHidden()
        assert 'Sun Strike' in window.overlay.invoker_spells.text()
        window.hero.setCurrentIndex(window.hero.findData(1))
        window.tick()
        assert window.overlay.kez_combos.isHidden() and window.overlay.invoker_spells.isHidden()
    finally:
        window.close()


@pytest.mark.parametrize('hero_id', [kez.HERO_ID, invoker.HERO_ID, shadow_shaman.HERO_ID])
def test_manual_hero_choice_replaces_draft_before_lookup_finishes(
        tmp_path, monkeypatch, hero_id):
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    monkeypatch.setattr('dota_helper.app.dota_active', lambda: False)
    window = MainWindow(start_services=False)
    try:
        window.timer.stop()
        window.capture_timer.stop()
        window.draft.meta_active = True
        window.draft.overlay_enabled.setChecked(True)
        requests = []
        monkeypatch.setattr(window, 'request_selection_builds', lambda: requests.append(hero_id))
        index = window.hero.findData(hero_id)
        window.hero.setCurrentIndex(index)
        window.hero.activated.emit(index)  # The real dropdown selection signal.
        window.tick()
        assert requests == [hero_id] and not window.routes
        assert window.hero_manual and not window.draft.meta_active
        assert not window.draft.overlay_enabled.isChecked()
        reference = {kez.HERO_ID: window.overlay.kez_combos,
                     invoker.HERO_ID: window.overlay.invoker_spells,
                     shadow_shaman.HERO_ID: window.overlay.shadow_shaman_tips}[hero_id]
        assert not reference.isHidden() and reference.text()
    finally:
        window.close()


def crowded_kez_overlay(font_size):
    overlay = Overlay({'overlay_layout_version': 3, 'overlay_w': 270,
                       'overlay_h': 600, 'overlay_x': 1060, 'overlay_y': 160,
                       'overlay_font': font_size}, STYLE)
    overlay.set_locked(True)
    overlay.hero.setText('Kez · Carry')
    overlay.route_label.setText('PRO · Example player · 2d ago\nPatch unknown')
    overlay.clock.setText('00:00 · Game clock')
    overlay.initial_buy.setText(
        'STARTING BUY\nTango ×1, Iron Branch ×3, Quelling Blade ×1, '
        'Slippers of Agility ×1, Observer Ward ×1')
    overlay.initial_buy.show()
    overlay.components.setText(
        'EARLY PARTS · until 5:00\n00:45 Circlet · 01:30 Magic Stick · '
        '02:20 Boots of Speed · 03:15 Gloves of Haste')
    overlay.components.show()
    overlay.supplies.setText(
        'LANING SUPPLIES · until 10:00\n01:30 Tango ×2 · 02:20 Healing Salve · '
        '03:20 Clarity ×2 · 04:30 Enchanted Mango · 05:10 Faerie Fire · '
        '06:30 Infused Raindrops · 07:20 Blood Grenade')
    overlay.supplies.show()
    items = ['Wraith Band', 'Magic Wand', 'Power Treads', 'Battle Fury',
             'Sange and Yasha', 'Black King Bar', "Aghanim's Scepter",
             'Satanic', 'Butterfly', 'Abyssal Blade', 'Nullifier', 'Moon Shard',
             'Boots of Travel (Level 2)', 'Divine Rapier', 'Swift Blink']
    overlay.set_item_lines([(f'{3 + index * 3:02}:00  {name}', index < 2)
                            for index, name in enumerate(items)])
    overlay.skill.setText('NEXT SKILL\nEcho Slash / Falcon Rush\nThen: Grappling Claw → Switch Discipline')
    overlay.talents.setText('Talent picks · recorded order\n+2.0s Falcon Rush Duration\n'
                           '+4.0% Kazurai Katana Damage Per Second\n+1 Echo Slash Attack\n'
                           '+80% Shodo Sai Critical Strike')
    overlay.talents.show()
    overlay.note.setText('Synthetic layout fixture')
    overlay.show_kez(True)
    return overlay


@pytest.mark.parametrize('bounds', [QRect(0, 0, 2560, 1440), QRect(0, 0, 1366, 768),
                                  QRect(0, 0, 1280, 720), QRect(0, 0, 1024, 576)],
                         ids=['1440p', '768p', '720p', 'scaled-desktop'])
@pytest.mark.parametrize('font_size', [13, 16])
@pytest.mark.parametrize('hero_id', [kez.HERO_ID, shadow_shaman.HERO_ID])
def test_full_build_and_all_combo_stages_remain_visible(qt_application, bounds, font_size, hero_id):
    overlay = crowded_kez_overlay(font_size)
    if hero_id == shadow_shaman.HERO_ID:
        overlay.hero.setText('Shadow Shaman · Soft support')
        overlay.show_shadow_shaman(True)
    try:
        overlay.show()
        qt_application.processEvents()
        overlay.fit_content(bounds)
        qt_application.processEvents()
        assert overlay.fit_ok, f'{overlay.fit_message}; bounds={bounds}'
        assert bounds.contains(overlay.geometry())
        if bounds.height() >= 720:
            assert overlay.y() == 160, 'Keep the reference below the game statistics on normal displays'
        assert overlay.overflow_bar.isHidden()
        assert len(overlay.item_lines) == 15
        assert overlay.font_size == font_size
        reference = overlay.kez_combos if hero_id == kez.HERO_ID else overlay.shadow_shaman_tips
        assert not reference.isHidden()
        assert all(w.isHidden() for w in overlay.references if w is not reference)
        labels = [label for label in overlay.labels if not label.isHidden() and label.text()]
        for label in labels:
            assert overlay.rect().contains(label.geometry()), label.text()
            assert label.height() >= label.heightForWidth(label.width()), label.text()
        for first, second in combinations(labels, 2):
            assert not first.geometry().intersects(second.geometry()), (first.text(), second.text())
    finally:
        overlay.close()
