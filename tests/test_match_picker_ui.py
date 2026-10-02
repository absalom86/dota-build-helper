import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from dota_helper.app import MainWindow
from dota_helper.builds import normalize
from test_fast_lookup import match


def test_mmr_reordering_preserves_selected_match_and_keyboard_mapping(tmp_path, monkeypatch):
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_services=False)
    routes = []
    for mid, mmr in ((1, 9000), (2, 11000), (3, None)):
        data = match(mid)
        data['avg_mmr'] = mmr
        routes.append(normalize(data, data['players'][0], 'fixture'))
    window.routes = routes
    window.session.choose(routes[0].id)
    window.render_routes()
    assert [r.match_ids[0] for r in window.routes] == [2, 1, 3]
    assert window.match_table.currentRow() == 1
    assert window.current_route().match_ids == [1]
    assert window.match_table.item(0, 0).text() == '11,000'
    assert window.match_table.item(2, 0).text() == '—'
    QTest.keyClick(window.match_table, Qt.Key.Key_Up)
    assert window.current_route().match_ids == [2]
    window.close()
    app.processEvents()


def test_default_source_dispatches_stratz(tmp_path, monkeypatch):
    monkeypatch.setattr("dota_helper.app.LOCAL", tmp_path)
    calls = []
    monkeypatch.setattr("dota_helper.recommendations.recommended_routes", lambda client, hero, role, *args: (calls.append((hero, role)), ([], "checked"))[1])
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_services=False)
    jobs = []
    window.launch_worker = lambda *args, **kw: jobs.append(args)
    window.fetch()
    result = jobs[0][0](lambda _: None, lambda _: None)
    jobs[0][1](result)
    assert calls == [(1, 1)]
    assert window.source.currentText() == "Recommended builds"
    assert all(window.source.view().isRowHidden(i) for i in (2,3,4))
    window.close()
    app.processEvents()


def test_rank_brackets_show_in_sorted_list_and_selected_overlay(tmp_path, monkeypatch):
    from test_stratz import match as stratz_match
    from dota_helper.stratz import normalize_stratz
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_services=False)
    window.draft.meta_active = False
    rows = []
    for mid, rank in ((1, 75), (2, 80)):
        data = stratz_match(mid)
        data['rank'] = rank
        rows.append(normalize_stratz(data, data['players'][0], {}))
    window.routes = rows
    window.session.choose(rows[0].id)
    window.render_routes()
    assert window.match_table.item(0, 0).text() == '—'
    assert window.match_table.item(0, 1).text() == 'Immortal (bracket)'
    assert window.match_table.item(1, 1).text() == 'Divine 5 (bracket)'
    assert window.match_table.currentRow() == 1
    window.match_table.setCurrentCell(0, 0)
    window.tick()
    assert 'Immortal' in window.overlay.route_label.text()
    assert window.current_route().match_ids == [2]
    window.close()
    app.processEvents()


def test_import_selects_exact_game_and_stale_response_is_ignored(tmp_path, monkeypatch):
    import json
    (tmp_path / "settings.json").write_text(json.dumps({"hero_id": 1, "role": 1, "lane": 2}))
    monkeypatch.setattr("dota_helper.app.LOCAL", tmp_path)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_services=False)
    assert not hasattr(window, "lane")
    window.source.setCurrentIndex(4)
    assert "lane" not in json.loads((tmp_path / "settings.json").read_text())
    jobs = []
    window.launch_worker = lambda *args, **kw: jobs.append(args)
    window.hero.setCurrentIndex(window.hero.findData(1))
    window.role.setCurrentIndex(window.role.findData(1))
    window.match_input.setText("123")
    window.import_match()
    data = match(123)
    route = normalize(data, data["players"][0], "User-selected game · Match MMR UNVERIFIED")
    jobs[0][1](route)
    assert window.session.selected == route.id and window.session.explicit_choice
    assert window.match_table.rowCount() == 1
    assert "123" in window.match_table.item(0, 2).text()
    assert window.purchases.rowCount() == 2
    assert window.purchases.item(0, 3).text() == "Observed purchase"
    assert not window.fetching and window.import_button.isEnabled()
    window.match_input.setText("124")
    window.import_match()
    window.hero.setCurrentIndex(window.hero.findData(2))
    jobs[1][1](route)
    assert not window.routes and not window.fetching
    window.close()
    app.processEvents()


def test_pro_pub_shows_mmr_and_match_average_rank_alongside_player(tmp_path, monkeypatch):
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    window = MainWindow(start_services=False)
    try:
        data = match(123)
        data.update(avg_mmr=11550, avg_rank_tier=75)
        route = normalize(data, data['players'][0], 'fixture')
        route.pro_player = True
        route.player = 'Professional player'
        window.routes = [route]
        window.session.accept_routes(window.routes)
        window.render_routes()
        table = window.match_table
        assert table.columnCount() == 6
        assert table.horizontalHeaderItem(0).text() == 'Avg. MMR'
        assert table.horizontalHeaderItem(1).text() == 'Avg. rank'
        assert table.item(0, 0).text() == '11,550'
        # The fixture player's individual rank is Immortal; the match average
        # must still be Divine 5, and the pro marker must not hide either value.
        assert table.item(0, 1).text() == 'Divine 5'
        assert 'PRO · Professional player' in table.item(0, 2).text()
        assert '123' in table.item(0, 2).text()
        assert 'OpenDota' in table.item(0, 0).toolTip()
        assert 'average rank tier 75' in table.item(0, 1).toolTip()
        assert 'Tango' in table.item(0, 4).text()
        assert 'Battle Fury' in table.item(0, 5).text()
        route.tournament = True
        window.render_routes()
        assert table.item(0, 0).text() == table.item(0, 1).text() == '—'
        assert 'PRO · Professional player' in table.item(0, 2).text()
    finally:
        window.close()
        QApplication.instance().processEvents()
