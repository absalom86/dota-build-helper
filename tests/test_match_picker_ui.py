import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from dota_helper.app import MainWindow
from dota_helper.builds import normalize
from test_fast_lookup import match


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
    assert "123" in window.match_table.item(0, 1).text()
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
