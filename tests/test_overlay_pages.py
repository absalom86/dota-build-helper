"""Compact pages constrain footprint rather than shrinking every section to fit."""
from itertools import combinations

import pytest
from PySide6.QtCore import QRect, Qt

from test_kez import crowded_kez_overlay
from test_overlay_bounds import readable_overlay_font


@pytest.mark.parametrize('bounds', [QRect(0, 0, 1920, 1040), QRect(0, 0, 1536, 824),
                                   QRect(0, 0, 1280, 680), QRect(0, 0, 1024, 536)])
@pytest.mark.parametrize('font', [13, 16])
def test_compact_pages_keep_readable_width_and_pinned_controls(qt_application, bounds, font):
    overlay = crowded_kez_overlay(font)
    try:
        overlay.set_compact(True)
        overlay.lane_timers.setText('Pull: 16s · ~2:45–2:47\nStack: 24s · ~2:53–2:55')
        overlay.show()
        for reference in (False, True):
            overlay.set_reference_page(reference)
            overlay.fit_content(bounds)
            qt_application.processEvents()
            assert overlay.width() == 270
            assert overlay.height() <= min(560, int(bounds.height() * .62))
            assert bounds.contains(overlay.geometry())
            assert overlay.effective_font_size == font
            assert overlay.kez_combos.isVisible() == reference
            assert overlay.items.isVisible() != reference
            assert overlay.hero.isVisible() and overlay.lane_timers.isVisible()
            assert overlay.viewport.geometry().top() >= overlay.header.geometry().bottom()
            assert overlay.lane_timers.y() >= overlay.viewport.geometry().bottom()
            assert overlay.reference_tab.y() >= overlay.lane_timers.geometry().bottom()
            assert overlay.overflow_hint.y() >= overlay.reference_tab.geometry().bottom()
            page = overlay.reference_content if reference else overlay.content
            labels = [label for label in overlay.labels if label.parentWidget() is page
                      and not label.isHidden() and label.text()]
            for label in labels:
                assert page.rect().contains(label.geometry())
                assert label.height() >= label.heightForWidth(label.width())
            for first, second in combinations(labels, 2):
                assert not first.geometry().intersects(second.geometry())
            pinned = (overlay.header.pos(), overlay.lane_timers.pos(), overlay.reference_tab.pos())
            if overlay.overflow_bar.maximum():
                overlay.scroll_page(1)
                offset = overlay.overflow_bar.value()
                assert offset > 0
                overlay.clock.setText('02:30 · Game clock')
                overlay.fit_content(bounds)
                assert overlay.overflow_bar.value() == offset
                assert page.y() == -offset
                assert pinned == (overlay.header.pos(), overlay.lane_timers.pos(), overlay.reference_tab.pos())
                overlay.overflow_bar.setValue(overlay.overflow_bar.maximum())
                assert page.y() + page.height() == overlay.viewport.height()
        assert overlay.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    finally:
        overlay.close()


def test_reference_off_and_expanded_mode_restore_build(qt_application):
    overlay = crowded_kez_overlay(13)
    try:
        overlay.initial_buy.hide()
        overlay.set_compact(True)
        overlay.set_reference_page(True)
        assert overlay.reference_page
        overlay.show_kez(False)
        overlay.fit_content(QRect(0, 0, 1280, 680))
        assert not overlay.reference_page and not overlay.content.isHidden()
        assert overlay.reference_tab.isHidden()
        overlay.show_kez(True)
        overlay.set_compact(False)
        overlay.fit_content(QRect(0, 0, 1920, 1040))
        assert overlay.kez_combos.parentWidget() is overlay.content
        assert overlay.hero.parentWidget() is overlay.content
        assert overlay.initial_buy.isHidden()
        assert overlay.header.isHidden() and overlay.reference_content.isHidden()
    finally:
        overlay.close()
