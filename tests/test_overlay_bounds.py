"""The click-through overlay must remain readable within scaled screen bounds."""
from html import unescape
from pathlib import Path

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QFont, QFontDatabase, QTextDocument
from PySide6.QtCore import QPoint

from dota_helper import invoker
from test_overlay_layout import assert_visible_geometry, crowded_overlay
from test_kez import crowded_kez_overlay


@pytest.fixture(autouse=True)
def readable_overlay_font(qt_application):
    # Windows offscreen Qt can otherwise substitute unreadable/mismeasured glyphs.
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


@pytest.mark.parametrize('bounds,font,saved_y', [
    (QRect(0, 0, 1280, 720), 16, 160),
    (QRect(0, 0, 1536, 864), 16, 400),
    (QRect(0, 0, 1024, 576), 13, 160),
], ids=['1080p-150-percent-large-font', '1080p-125-percent-low-position',
        '720p-125-percent'])
def test_crowded_overlay_stays_on_screen_without_losing_content(
        qt_application, bounds, font, saved_y):
    overlay = crowded_overlay(15)
    try:
        overlay.font_size = font
        overlay.move(bounds.right() - overlay.width() - 12, saved_y)
        preferred_width = overlay.preferred_width
        item_lines = list(overlay.item_lines)
        talent_text = overlay.talents.text()
        starting_text = overlay.initial_buy.text()
        overlay.show()
        qt_application.processEvents()
        overlay.fit_content(bounds)
        qt_application.processEvents()

        assert_visible_geometry(overlay, bounds)
        assert overlay.font_size == font
        assert overlay.preferred_width == preferred_width
        assert 11 <= overlay.items.font().pixelSize() <= font
        assert overlay.item_lines == item_lines
        assert all(text in unescape(overlay.items.text()) for text, _ in item_lines)
        assert not overlay.talents.isHidden()
        assert overlay.talents.text() == talent_text
        assert not overlay.initial_buy.isHidden()
        assert overlay.initial_buy.text() == starting_text
        assert not overlay.invoker_spells.isHidden()
        spells = QTextDocument()
        spells.setHtml(overlay.invoker_spells.text())
        for name, recipe in invoker.SPELLS:
            assert name in spells.toPlainText()
            assert recipe in spells.toPlainText()
    finally:
        overlay.close()
        qt_application.processEvents()


def long_draft_overlay(font):
    overlay = crowded_overlay(0)
    overlay.font_size = font
    for label in (overlay.initial_buy, overlay.components, overlay.supplies, overlay.talents):
        label.hide()
    overlay.show_invoker(False)
    overlay.title.setText('DRAFT HELPER')
    overlay.title.show()
    overlay.hero.setText('Picks to consider')
    overlay.route_label.setText('Soft support')
    overlay.clock.setText('Position 4')
    heroes = ['Keeper of the Light', 'Outworld Destroyer', 'Ancient Apparition',
              'Centaur Warrunner', 'Treant Protector']
    rows = '\n'.join(f'{name} · 55.8% · 13,434 games' for name in heroes)
    overlay.set_message('TOP WIN RATE · 100+ games\n' + rows + '\n\nMOST PLAYED\n' + rows)
    overlay.skill.setText('Choose a hero in Dota; confirmed picks load builds.')
    overlay.note.setText('Recent 7 days · Immortal · patch unverified')
    return overlay


@pytest.mark.parametrize('bounds,font', [
    (QRect(0, 0, 853, 480), 13),
    (QRect(0, 0, 1024, 576), 16),
], ids=['720p-150-percent-draft', 'short-draft-large-font'])
def test_long_draft_keeps_all_recommendations_and_avoids_tall_fallback(
        qt_application, bounds, font):
    overlay = long_draft_overlay(font)
    try:
        overlay.move(bounds.right() - overlay.width() - 12, 160)
        preferred_width = overlay.preferred_width
        recommendations = overlay.items.text()
        overlay.show()
        qt_application.processEvents()
        # At font16 the previous last-candidate fallback made this draft 745px
        # tall, although one 390px column needed only 491px. Preserve that useful
        # upper bound rather than allowing empty columns to narrow its text.
        overlay._style_labels()
        _, single_column_height = overlay._arrange(390, False)
        overlay.fit_content(bounds)
        qt_application.processEvents()

        assert_visible_geometry(overlay, bounds)
        assert overlay.font_size == font
        assert overlay.preferred_width == preferred_width
        assert 11 <= overlay.items.font().pixelSize() <= font
        assert overlay.items.text() == recommendations
        assert overlay.items.text().count('13,434 games') == 10
        if font == 16:
            assert overlay.height() <= single_column_height
    finally:
        overlay.close()
        qt_application.processEvents()


def test_font_recovers_when_screen_has_room(qt_application):
    overlay = crowded_overlay(15)
    try:
        overlay.font_size = 16
        overlay.fit_content(QRect(0, 0, 1280, 720))
        assert overlay.effective_font_size < 16
        overlay.fit_content(QRect(0, 0, 2560, 1440))
        assert overlay.effective_font_size == overlay.font_size == 16
        assert overlay.preferred_width == 270
    finally:
        overlay.close()


def test_temporary_upward_fit_restores_saved_position(qt_application):
    overlay = long_draft_overlay(13)
    try:
        overlay.move(563, 160)
        overlay.fit_content(QRect(0, 0, 853, 480))
        assert overlay.y() < 160
        assert overlay.preferred_y == 160
        overlay.fit_content(QRect(0, 0, 1920, 1080))
        assert overlay.y() == overlay.preferred_y == 160
    finally:
        overlay.close()


def test_extreme_content_is_bounded_and_scrollable_in_preview(qt_application):
    overlay = crowded_overlay(15)
    try:
        overlay.set_locked(False)
        rows = [(f'{index}:00  Very long item name {index}', False) for index in range(100)]
        overlay.set_item_lines(rows)
        overlay.lane_timers.setText('Last section: lane timers')
        overlay.show()
        qt_application.processEvents()
        bounds = QRect(0, 0, 853, 480)
        overlay.fit_content(bounds)
        qt_application.processEvents()
        assert bounds.contains(overlay.geometry())
        assert not overlay.fit_ok
        assert not overlay.overflow_bar.isHidden()
        assert not overlay.overflow_hint.isHidden()
        assert overlay.overflow_bar.maximum() > 0
        assert 'Preview' in overlay.fit_message
        assert overlay.item_lines == rows
        overlay.overflow_bar.setValue(overlay.overflow_bar.maximum())
        qt_application.processEvents()
        tail = overlay.lane_timers.mapTo(overlay.viewport, QPoint(0, 0))
        assert tail.y() >= 0
        assert tail.y() + overlay.lane_timers.height() <= overlay.viewport.height()
        assert overlay.preferred_width == 270 and overlay.font_size == 13
        overlay.set_locked(True)
        overlay.fit_content(bounds)
        assert overlay.overflow_bar.value() == 0
        assert overlay.content.pos() == QPoint(0, 0)
        # Returning to normal data must also reset clipping and scroll offset.
        overlay.set_item_lines(rows[:3])
        overlay.fit_content(QRect(0, 0, 2560, 1440))
        assert overlay.fit_ok
        assert overlay.overflow_bar.isHidden() and overlay.overflow_hint.isHidden()
        assert overlay.content.pos() == QPoint(0, 0)
    finally:
        overlay.close()


@pytest.mark.parametrize('hero', ['invoker', 'kez', 'shaman'])
@pytest.mark.parametrize('show_reference', [True, False])
@pytest.mark.parametrize('bounds,font', [
    (QRect(0, 0, 1920, 1040), 13),
    (QRect(0, 0, 1536, 824), 16),
    (QRect(0, 0, 1280, 680), 16),
    (QRect(0, 0, 1024, 536), 13),
], ids=['1080p-taskbar', '1080p-125-percent', '1080p-150-percent', 'small-scaled'])
def test_hero_cards_and_full_build_fit_scaled_work_area(qt_application, hero, show_reference, bounds, font):
    overlay = crowded_overlay() if hero == 'invoker' else crowded_kez_overlay(font)
    try:
        overlay.font_size = font
        if hero == 'shaman':
            overlay.show_shadow_shaman(True)
        if not show_reference:
            overlay.show_invoker(False)
            overlay.show_kez(False)
            overlay.show_shadow_shaman(False)
        overlay.move(bounds.right()-overlay.width()-12, 160)
        overlay.fit_content(bounds)
        assert_visible_geometry(overlay, bounds)
        assert len(overlay.item_lines) == 15
        assert not overlay.initial_buy.isHidden() and not overlay.talents.isHidden()
        assert overlay.font_size == font and overlay.preferred_width == 270
        assert sum(not label.isHidden() for label in overlay.references) == int(show_reference)
        if bounds.height() >= 680:
            assert overlay.y() == 160
    finally:
        overlay.close()


def test_shorter_reference_column_is_selected_at_same_width(qt_application):
    overlay = crowded_kez_overlay(13)
    try:
        overlay.fit_content(QRect(0, 0, 1920, 1040))
        _, old_height = overlay._arrange(overlay.width(), True)
        _, separate_height = overlay._arrange(overlay.width(), 2)
        assert separate_height < old_height
        assert overlay.height() == separate_height
    finally:
        overlay.close()
