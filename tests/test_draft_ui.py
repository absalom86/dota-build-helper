import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from dota_helper.draft import rank_picks
from dota_helper.draft_ui import DraftPanel


@pytest.fixture
def panel():
    app = QApplication.instance() or QApplication([])
    jobs = []
    widget = DraftPanel(lambda *args: jobs.append(args))
    widget.auto.setChecked(False)
    yield widget, jobs
    widget.stop()
    widget.close()
    app.processEvents()


def result():
    return rank_picks([2], {2: [{"hero_id": 5, "games_played": 200, "wins": 70}]}), "Live fixture"


def choose_enemy(panel, hero_id=2):
    panel.enemies[0].setCurrentIndex(panel.enemies[0].findData(hero_id))


def test_changed_draft_rejects_inflight_response(panel):
    widget, jobs = panel
    choose_enemy(widget)
    widget.search()
    choose_enemy(widget, 14)
    jobs[0][1](result())
    assert not widget.picks and widget.table.rowCount() == 0
    assert not widget.choose.isEnabled()


def test_duplicate_enemies_do_not_request_data(panel):
    widget, jobs = panel
    choose_enemy(widget)
    widget.enemies[1].setCurrentIndex(widget.enemies[1].findData(2))
    widget.search()
    assert not jobs
    assert "twice" in widget.status.text()


def test_choose_suggestion_and_overlay_use_current_results(panel):
    widget, jobs = panel
    choose_enemy(widget)
    widget.search()
    jobs[0][1](result())
    selected = []
    widget.use_hero.connect(selected.append)
    widget.overlay_enabled.setChecked(True)
    assert "Crystal Maiden" in widget.overlay_text()[1]
    widget.choose_hero()
    assert selected == [5]
    assert widget.overlay_text() is None


def test_clear_draft_removes_picks_exclusions_and_pending_timer(panel):
    widget, jobs = panel
    choose_enemy(widget)
    widget.search()
    jobs[0][1](result())
    widget.exclude.setCurrentIndex(widget.exclude.findData(1))
    widget.add_excluded()
    widget.clear()
    assert not widget.picks and not widget.blocked
    assert not any(c.currentData() for c in widget.enemies)
    assert not widget.choose.isEnabled()


def test_failure_clears_current_results(panel):
    widget, jobs = panel
    choose_enemy(widget)
    widget.search()
    jobs[0][1](result())
    widget.search()
    jobs[1][2]("Unavailable")
    assert not widget.picks and not widget.choose.isEnabled()


def test_cancel_rejects_late_response(panel):
    widget, jobs = panel
    choose_enemy(widget)
    widget.search()
    widget.stop()
    jobs[0][1](result())
    assert not widget.picks


def test_role_refresh_retry_keeps_dates_and_uses_current_role(panel):
    widget,jobs=panel
    widget.meta_refresh.click()
    assert not widget.meta_refresh.isEnabled()
    jobs[-1][2]('Source unavailable')
    assert widget.meta_refresh.isEnabled()
    widget.meta_refresh.click()
    rows=[dict(hero_id=1,games=200,wins=110,rate=.55)]
    jobs[-1][1]((rows,'11 Sep–17 Sep 2026 UTC · DELAYED DATA'))
    assert 'Anti-Mage' in widget.meta_label.toPlainText()
    widget.meta_refresh.click()
    jobs[-1][2]('Request timed out')
    assert widget.meta_rows==rows
    assert '17 Sep 2026' in widget.meta_status and 'Refresh failed' in widget.meta_status
    widget.set_role(4)
    assert not widget.meta_rows
    assert not widget.meta_data_status
    assert widget.meta_requested_role==4
