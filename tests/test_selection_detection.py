import pytest

from dota_helper.app import MainWindow


def payload(hero=48, state='HERO_SELECTION', match='42'):
    return {'hero': {'id': hero}, 'player': {'steamid': 'test'},
            'map': {'matchid': match, 'clock_time': -70,
                    'game_state': 'DOTA_GAMERULES_STATE_' + state}}


@pytest.fixture
def selection(tmp_path, monkeypatch, qt_application):
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    now = [100.0]
    monkeypatch.setattr('dota_helper.app.time.monotonic', lambda: now[0])
    window = MainWindow(start_services=False)
    window.timer.stop()
    window.capture_timer.stop()
    calls = []
    window.fetch = lambda: calls.append((window.hero.currentData(), window.role.currentData()))
    yield window, now, calls
    window.close()
    qt_application.processEvents()


def test_stable_draft_preloads_once_but_never_confirms_lock(selection):
    window, now, calls = selection
    window.on_gsi(payload())
    now[0] += 1
    window.on_gsi(payload())
    assert not calls
    now[0] += 1
    window.on_gsi(payload())
    assert calls == [(48, 1)]
    assert window.session.field_status('hero') == 'missing'
    window.on_gsi(payload())
    window.tick()
    assert not window.draft.meta_active
    assert 'unconfirmed' in window.overlay.clock.text()
    window.on_gsi(payload(state='STRATEGY_TIME'))
    assert window.session.field_status('hero') == 'fresh'
    assert window.draft_preview_hero is None
    assert calls == [(48, 1)]


def test_unstable_hover_missing_local_player_and_opt_out_do_not_prefetch(selection):
    window, now, calls = selection
    for hero in [48, 1, 48, 1, 48]:
        window.on_gsi(payload(hero))
        now[0] += 3
    missing = payload()
    missing['player'] = {'team2': {'player0': {'steamid': 'spectator'}}}
    window.on_gsi(missing)
    window.on_gsi(payload())
    assert not calls
    window.preview_draft_hero.setChecked(False)
    for _ in range(3):
        now[0] += 3
        window.on_gsi(payload())
    assert not calls


def test_manual_hero_survives_confirmation_and_can_resume(selection):
    window, _, calls = selection
    window.on_gsi(payload())
    window.hero.setCurrentIndex(window.hero.findData(2))
    window.hero.activated.emit(window.hero.currentIndex())
    window.on_gsi(payload(state='STRATEGY_TIME'))
    assert window.hero.currentData() == 2
    assert window.session.hero_id == 2
    assert calls == [(2, 1)]
    assert 'keeping manual' in window.gsi_status
    window.resume_detection()
    window.on_gsi(payload(state='STRATEGY_TIME'))
    assert window.hero.currentData() == 48
    assert calls[-1] == (48, 1)


def test_role_swap_keeps_live_skills_and_refreshes_builds(selection):
    window, _, calls = selection
    live = payload(state='GAME_IN_PROGRESS')
    live['abilities'] = {'ability0': {'name': 'luna_lucent_beam', 'level': 2}}
    window.on_gsi(live)
    window.role.setCurrentIndex(window.role.findData(3))
    window.role.activated.emit(window.role.currentIndex())
    window.on_gsi(live)
    assert window.role.currentData() == 3 and window.role_manual
    assert window.session.learned['luna_lucent_beam'] == 2
    assert calls == [(48, 1), (48, 3)]


def test_new_match_releases_overrides_but_initial_draft_preserves_user_choice(selection):
    window, _, _ = selection
    window.hero.setCurrentIndex(window.hero.findData(2))
    window.hero.activated.emit(window.hero.currentIndex())
    window.on_gsi(payload())
    assert window.hero_manual
    window.on_gsi(payload(state='STRATEGY_TIME'))
    window.on_gsi(payload(match='43'))
    assert not window.hero_manual
    window.on_gsi(payload(state='STRATEGY_TIME', match='43'))
    assert window.hero.currentData() == 48


def test_late_role_detection_refreshes_preview_and_manual_role_blocks_it(selection, monkeypatch):
    window, now, calls = selection
    for _ in range(3):
        window.on_gsi(payload())
        now[0] += 1
    window.settings['role_region'] = {'left': 0, 'top': 0, 'width': 100, 'height': 30}
    window.role_ocr.setChecked(True)
    monkeypatch.setattr('dota_helper.app.dota_active', lambda: True)
    jobs = []
    window.launch_worker = lambda *args: jobs.append(args)
    for _ in range(3):
        window.detect_role()
        jobs[-1][1](5)
    assert calls == [(48, 1), (48, 5)]
    assert window.role_applied
    window.role.setCurrentIndex(window.role.findData(4))
    window.role.activated.emit(window.role.currentIndex())
    window.detect_role()
    assert window.role.currentData() == 4 and window.role_manual


def test_selection_change_queues_latest_context_behind_cancelled_fetch(selection):
    window, _, calls = selection
    window.fetching = True
    window.hero.setCurrentIndex(window.hero.findData(48))
    window.hero.activated.emit(window.hero.currentIndex())
    window.role.setCurrentIndex(window.role.findData(5))
    window.role.activated.emit(window.role.currentIndex())
    assert window.cancel.is_set() and window.pending_auto_fetch
    assert not calls


def test_draft_hover_lookups_are_rate_limited(selection):
    window, now, calls = selection
    for hero in [48, 2, 3]:
        for _ in range(3):
            window.on_gsi(payload(hero))
            now[0] += 1
    assert calls == [(48, 1)]
    for _ in range(5):
        now[0] += 1
        window.on_gsi(payload(3))
    assert calls == [(48, 1), (3, 1)]


def test_reconnection_does_not_count_stale_candidate_reads(selection):
    window, now, calls = selection
    for _ in range(2):
        window.on_gsi(payload())
        now[0] += 1
    now[0] += 20
    window.on_gsi(payload())
    assert not calls


def test_bot_restart_without_draft_releases_manual_override(selection):
    window, _, _ = selection
    live = payload(state='GAME_IN_PROGRESS', match='0')
    live['map']['clock_time'] = 100
    window.on_gsi(live)
    window.hero.setCurrentIndex(window.hero.findData(2))
    window.hero.activated.emit(window.hero.currentIndex())
    window.on_gsi(payload(state='PRE_GAME', match='0'))
    assert not window.hero_manual
    assert window.hero.currentData() == 48


def test_new_draft_preview_does_not_reuse_previous_games_clock(selection):
    window, now, _ = selection
    live = payload(state='GAME_IN_PROGRESS')
    live['map']['clock_time'] = 1800
    window.on_gsi(live)
    for _ in range(3):
        window.on_gsi(payload(match='43'))
        now[0] += 1
    assert window.draft_preview_hero == 48
    assert window.session.clock is None
    assert window.game_clock()[0] == 0
