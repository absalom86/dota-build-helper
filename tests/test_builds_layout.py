"""Keep comparison and selected purchase details visible in a compact window."""
from copy import deepcopy
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QTabWidget

from dota_helper.app import MainWindow
from dota_helper.models import Purchase
from dota_helper.providers import Demo
from dota_helper.ranking import RANKING_DESCRIPTION


@pytest.fixture
def builds_window(tmp_path, monkeypatch, qt_application):
    font_ids = []
    for name in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf'):
        path = Path('C:/Windows/Fonts') / name
        if path.exists():
            font_ids.append(QFontDatabase.addApplicationFont(str(path)))
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    monkeypatch.setenv('DOTA_HELPER_HOME', str(tmp_path))
    window = MainWindow(start_services=False)
    window.draft.meta_active = False
    template = Demo().routes(1, 1, 0)[0][0]
    template.purchases = [Purchase(key, -60) for key in
                          ('tango', 'branches', 'quelling_blade', 'magic_stick', 'faerie_fire', 'ward_observer')] + template.purchases[4:]
    routes = []
    for index in range(10):
        route = deepcopy(template)
        route.id = f'layout:{index}'
        route.demo = False
        route.source = 'STRATZ'
        route.match_ids = [9000000000 + index]
        route.patch_label = 'unverified (synthetic layout fixture)'
        route.evidence = 'Synthetic layout fixture · numeric MMR unavailable'
        routes.append(route)
    window.routes = routes
    window.session.accept_routes(routes)
    window.render_routes()
    window.status.setText('10 builds ready · ' + RANKING_DESCRIPTION + '. Newest games within each preference.')
    window.show()
    yield window
    window.close()
    qt_application.processEvents()
    for font_id in font_ids:
        if font_id >= 0:
            QFontDatabase.removeApplicationFont(font_id)


def bounds_in(widget, ancestor):
    return QRect(widget.mapTo(ancestor, QPoint()), widget.size())


@pytest.mark.parametrize('size', [(900, 700), (1280, 900)])
def test_build_comparison_and_selected_details_fit_without_horizontal_scroll(builds_window, qt_application, size):
    window = builds_window
    window.resize(*size)
    qt_application.processEvents()
    scroll = window.tabs.widget(0)
    viewport = scroll.viewport()
    assert scroll.horizontalScrollBar().maximum() == 0
    assert scroll.verticalScrollBar().maximum() == 0
    for table in (window.match_table, window.purchases):
        assert viewport.rect().contains(bounds_in(table, viewport))
        assert table.horizontalScrollBar().maximum() == 0
        assert table.viewport().height() >= table.rowHeight(0) * 3
    assert viewport.rect().contains(bounds_in(window.quantity_preview, viewport))
    assert window.quantity_preview.height() >= window.quantity_preview.heightForWidth(window.quantity_preview.width())
    assert 'Observer Ward' in window.quantity_preview.text()
    assert viewport.rect().contains(bounds_in(window.skills, viewport))
    tabs = window.builds_page.findChild(QTabWidget)
    tabs.setCurrentWidget(window.route_notes)
    qt_application.processEvents()
    assert window.route_notes.isVisible()
    assert viewport.rect().contains(bounds_in(window.route_notes, viewport))


def test_long_quantity_preview_scrolls_page_without_collapsing_purchase_details(builds_window, qt_application):
    window = builds_window
    window.resize(900, 700)
    window.quantity_preview.setText('STARTING BUY\n' + ' · '.join(
        f'Long starting item {index} ×1 (recorded)' for index in range(50)))
    qt_application.processEvents()
    scroll = window.tabs.widget(0)
    assert scroll.verticalScrollBar().maximum() > 0
    assert scroll.horizontalScrollBar().maximum() == 0
    assert window.quantity_preview.height() >= window.quantity_preview.heightForWidth(window.quantity_preview.width())
    assert window.builds_page.rect().contains(bounds_in(window.purchases, window.builds_page))
    assert window.purchases.viewport().height() >= window.purchases.rowHeight(0) * 2
    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
    qt_application.processEvents()
    assert scroll.viewport().rect().contains(bounds_in(window.purchases, scroll.viewport()))
