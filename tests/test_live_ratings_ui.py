"""Late match-rating observations update comparisons without stealing a chosen build."""
from types import SimpleNamespace
from copy import deepcopy
from pathlib import Path
import time

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QFontDatabase

from dota_helper.app import MainWindow
from dota_helper.builds import normalize
from dota_helper.live_ratings import MAX_AGE, SOURCE
from test_fast_lookup import match


@pytest.fixture
def window(tmp_path, monkeypatch, qt_application):
    font_ids = []
    for name in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf'):
        path = Path('C:/Windows/Fonts') / name
        if path.exists():
            font_ids.append(QFontDatabase.addApplicationFont(str(path)))
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    monkeypatch.setenv('DOTA_HELPER_HOME', str(tmp_path))
    monkeypatch.setattr('dota_helper.live_ratings.urlopen',
                        lambda *args, **kwargs: pytest.fail('Unexpected live network request'))
    instance = MainWindow(start_services=False)
    instance.timer.stop()
    instance.capture_timer.stop()
    instance.live_ratings_timer.stop()
    instance.draft.meta_active = False
    yield instance
    instance.services_started = False
    instance.close()
    qt_application.processEvents()
    for font_id in font_ids:
        if font_id >= 0:
            QFontDatabase.removeApplicationFont(font_id)


def observation(mmr):
    return {'average_mmr': mmr, 'observed_at': time.time(), 'source': SOURCE}


def routes():
    games = []
    for mid in (501, 502):
        data = match(mid)
        data['start_time'] -= mid - 501
        data['avg_rank_tier'] = 80
        games.append(normalize(data, data['players'][0], 'fixture'))
    return games


def test_cached_observations_render_only_matching_games_without_fetch(window):
    window.routes = routes()
    window.live_ratings.records = {'502': observation(11250), '999': observation(20000)}
    window.render_routes()
    assert [route.match_ids[0] for route in window.routes] == [502, 501]
    assert window.match_table.item(0, 0).text() == '11,250'
    assert window.match_table.item(0, 1).text() == 'Immortal'
    assert SOURCE in window.match_table.item(0, 0).toolTip()
    assert window.match_table.item(1, 0).text() == '—'
    assert len(window.routes) == 2
    assert window.current_route().match_ids == [502]


@pytest.mark.parametrize('manual_choice', [False, True], ids=['automatic-default', 'manual-choice'])
def test_late_mmr_reorders_games_and_respects_selection(window, manual_choice):
    window.routes = routes()
    window.live_ratings.records = {'501': observation(9000)}
    window.render_routes()
    first_id = window.current_route().id
    if manual_choice:
        window.session.choose(first_id)
    window.session.completed.add(('bfury', 1))
    window.session.learned['antimage_mana_break'] = 1
    jobs = []
    window.launch_worker = lambda *args, **kwargs: jobs.append(args)
    window.services_started = True
    window.refresh_live_ratings()
    window.refresh_live_ratings()
    assert len(jobs) == 1 and window.live_ratings_busy
    # The independent sampler finishes after the build list has already rendered.
    window.live_ratings.records['502'] = observation(12000)
    jobs[0][1](SimpleNamespace(status='1 live match MMR observation recorded', error=None))
    assert not window.live_ratings_busy
    assert [route.match_ids[0] for route in window.routes] == [502, 501]
    assert window.match_table.item(0, 0).text() == '12,000'
    assert window.match_table.item(1, 0).text() == '9,000'
    assert window.current_route().match_ids == ([501] if manual_choice else [502])
    assert window.match_table.currentRow() == (1 if manual_choice else 0)
    assert window.session.explicit_choice is manual_choice
    assert ('bfury', 1) in window.session.completed
    assert window.session.learned['antimage_mana_break'] == 1


def test_offline_and_demo_modes_do_not_launch_live_sampler(window):
    jobs = []
    window.launch_worker = lambda *args, **kwargs: jobs.append(args)
    window.refresh_live_ratings()
    assert not jobs
    window.services_started = True
    window.source.setCurrentIndex(1)
    window.refresh_live_ratings()
    assert not jobs
    assert not window.live_ratings_busy


def test_visible_mmr_status_counts_pub_coverage_and_current_cache(window):
    window.routes = routes()
    window.routes[0].pro_player = True  # A pro's ranked pub is eligible for MMR.
    tournament = deepcopy(window.routes[0])
    tournament.id = 'tournament:503'
    tournament.match_ids = [503]
    tournament.tournament = True
    demo = deepcopy(window.routes[0])
    demo.id = 'demo:504'
    demo.match_ids = [504]
    demo.demo = True
    window.routes.extend([tournament, demo])
    stale = observation(15000)
    stale['observed_at'] -= MAX_AGE + 1
    window.live_ratings.records = {
        '502': observation(11250), '999': observation(20000), '777': stale}
    window.render_routes()
    status = window.mmr_status.text().lower()
    assert '1/2' in status
    assert '2 live readings saved' in status
    assert 'offline' in status
    assert window.mmr_status.wordWrap()
    assert not window.mmr_status.isHidden()
    assert window.match_table.rowCount() == 4


def test_healthy_feed_with_no_matching_games_explains_missing_mmr(window):
    window.routes = routes()
    window.render_routes()
    before = list(window.routes)
    jobs = []
    window.launch_worker = lambda *args, **kwargs: jobs.append(args)
    window.services_started = True
    window.refresh_live_ratings()
    window.live_ratings.records['999'] = observation(12000)
    window.live_ratings.last_success = time.time()
    jobs[0][1](SimpleNamespace(status='1 live match MMR observation recorded', error=None))
    # No displayed route changed, so the completion itself must refresh status.
    assert window.routes == before
    status = window.mmr_status.text().lower()
    assert '0/2' in status
    assert '1 live readings saved' in status
    assert 'no captured mmr for these games' in status
    assert '429' not in status and 'quota' not in status


def test_rate_limit_is_visible_even_when_no_route_changes(window, qt_application):
    window.routes = routes()
    window.live_ratings.records['501'] = observation(9000)
    window.render_routes()
    before = list(window.routes)
    jobs = []
    window.launch_worker = lambda *args, **kwargs: jobs.append(args)
    window.services_started = True
    window.refresh_live_ratings()
    window.live_ratings.next_refresh_at = time.time() + 300
    window.live_ratings.last_error = 'HTTP 429'
    jobs[0][1](SimpleNamespace(status=window.live_ratings.status_text(), error='HTTP 429'))
    assert window.routes == before
    assert window.match_table.item(0, 0).text() == '9,000'
    status = window.mmr_status.text().lower()
    assert '1/2' in status and '1 live readings saved' in status
    assert '429' in status
    assert 'retry' in status or 'cooldown' in status
    assert not window.live_ratings_busy
    window.resize(900, 700)
    window.show()
    qt_application.processEvents()
    viewport = window.tabs.widget(0).viewport()
    geometry = QRect(window.mmr_status.mapTo(viewport, QPoint()), window.mmr_status.size())
    assert viewport.rect().contains(geometry)
    assert window.mmr_status.height() >= window.mmr_status.heightForWidth(window.mmr_status.width())


def test_background_failure_keeps_saved_values_and_updates_visible_status(window):
    window.routes = routes()
    window.live_ratings.records['501'] = observation(9000)
    window.render_routes()
    jobs = []
    window.launch_worker = lambda *args, **kwargs: jobs.append(args)
    window.services_started = True
    window.refresh_live_ratings()
    jobs[0][2]('Connection failed')
    status = window.mmr_status.text().lower()
    assert 'failed' in status or 'unavailable' in status
    assert '1/2' in status and '1 live readings saved' in status
    assert window.match_table.item(0, 0).text() == '9,000'
    assert not window.live_ratings_busy


def test_initial_state_does_not_claim_feed_success_or_quota_failure(window):
    window.services_started = True
    window.update_mmr_status()
    status = window.mmr_status.text().lower()
    assert '0/0' in status and '0 live readings saved' in status
    assert 'waiting for first check' in status
    assert 'connected' not in status and '429' not in status


def test_manual_lookup_supplies_only_selected_hero_mmr_candidates(window, monkeypatch):
    hero = window.hero.currentData()
    window.live_ratings.records = {
        '501': dict(observation(9100), hero_ids=[hero]),
        '502': dict(observation(8000), hero_ids=[hero + 1]),
        '503': dict(observation(6500), hero_ids=[hero])}
    jobs, captured = [], []
    window.launch_worker = lambda *args, **kwargs: jobs.append(args)
    def lookup(client, actual_hero, role, *args):
        assert not getattr(client, 'rated_candidates', [])
        return [], 'Fixture complete'
    def mmr_lookup(client, actual_hero, role, candidates, progress, cancel, deadline, on_update):
        captured.append((actual_hero, role, candidates))
        assert deadline - time.monotonic() > 7  # independent of ordinary lookup's remaining time
        return [], 'Fixture MMR complete'
    monkeypatch.setattr('dota_helper.recommendations.recommended_routes', lookup)
    monkeypatch.setattr('dota_helper.rated_builds.rated_routes', mmr_lookup)
    window.fetch(force=True)
    assert len(jobs) == 2
    result = jobs[0][0](lambda _: None, lambda _: None)
    jobs[0][1](result)
    result = jobs[1][0](lambda _: None, lambda _: None)
    jobs[1][1](result)
    assert captured[0][:2] == (hero, window.role.currentData())
    assert [entry['match_id'] for entry in captured[0][2]] == [501, 503]
    assert captured[0][2][0]['average_mmr'] == 9100


def test_resolved_mmr_build_is_displayed_selected_and_saved_while_normal_lookup_runs(window):
    from dota_helper.history import decode
    hero = window.hero.currentData()
    window.live_ratings.records = {'502': dict(observation(8352), hero_ids=[hero])}
    window.routes = routes()[:1]
    window.render_routes()
    original = window.current_route().id
    window.session.choose(original)
    window.fetching = True
    jobs = []
    window.launch_worker = lambda *args, **kwargs: jobs.append(args)
    window.lookup_rated_builds()
    assert len(jobs) == 1 and window.mmr_lookup_busy
    route = routes()[1]
    route.average_mmr = 8352
    route.average_mmr_source = SOURCE
    jobs[0][1](([route], 'MMR build ready'))
    assert not window.mmr_lookup_busy and window.fetching
    assert window.match_table.item(0, 0).text() == '8,352'
    assert window.current_route().id == original  # preserve chosen guide
    window.match_table.setCurrentCell(0, 0)
    window.route_choice.setCurrentIndex(0)
    window.select_route()
    assert window.current_route().average_mmr == 8352
    saved = decode(window.history.find(hero, window.role.currentData(), 0))
    assert saved[0].average_mmr == 8352 and saved[0].average_mmr_source == SOURCE
    window.fetching = False


def test_mmr_results_for_previous_hero_are_discarded(window):
    hero = window.hero.currentData()
    window.live_ratings.records = {'502': dict(observation(8352), hero_ids=[hero])}
    jobs = []
    window.launch_worker = lambda *args, **kwargs: jobs.append(args)
    window.lookup_rated_builds()
    window.hero.setCurrentIndex(window.hero.findData(2 if hero != 2 else 1))
    jobs[0][1](([routes()[1]], 'Old hero complete'))
    assert not window.routes and not window.mmr_lookup_busy


def test_first_feed_arrival_resolves_candidates_after_initial_search(window):
    window.services_started = True
    jobs = []
    window.launch_worker = lambda *args, **kwargs: jobs.append(args)
    window.refresh_live_ratings()
    window.lookup_rated_builds()
    assert window.mmr_lookup_pending and len(jobs) == 1
    hero = window.hero.currentData()
    window.live_ratings.records = {'502': dict(observation(8352), hero_ids=[hero])}
    jobs[0][1](SimpleNamespace(status='Feed ready', error=None))
    assert len(jobs) == 2 and window.mmr_lookup_busy and not window.mmr_lookup_pending
    jobs[1][1](([], 'No completed matches'))
