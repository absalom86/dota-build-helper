import pytest
from PySide6.QtCore import Qt

from dota_helper.app import MainWindow
from dota_helper.catalog import ability_name
from dota_helper.providers import Demo


def gsi(clock=100, hero=1, match=42):
    return {
        'hero': {'id': hero, 'level': 4},
        'player': {'steamid': 'local-test-player'},
        'map': {'matchid': match, 'clock_time': clock,
                'game_state': 'DOTA_GAMERULES_STATE_GAME_IN_PROGRESS'},
    }


@pytest.fixture
def telemetry_window(tmp_path, monkeypatch, qt_application):
    now = [100.0]
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    monkeypatch.setattr('dota_helper.starting_items.user_data_dir', lambda: tmp_path)
    monkeypatch.setattr('dota_helper.quantity_evidence.user_data_dir', lambda: tmp_path)
    monkeypatch.setattr('dota_helper.models.time.monotonic', lambda: now[0])
    monkeypatch.setattr('dota_helper.app.dota_active', lambda: False)
    window = MainWindow(start_services=False)
    window.timer.stop()
    window.capture_timer.stop()
    window.draft.meta_active = False
    monkeypatch.setattr(window.draft, 'overlay_text', lambda: None)
    monkeypatch.setattr(window, 'fetch', lambda: None)
    routes, _ = Demo().routes(1, 1, 0)
    route = routes[0]
    route.demo = False
    route.source = 'STRATZ'
    route.match_ids = [42]
    window.routes = [route]
    window.session.accept_routes(window.routes)
    window.render_routes()
    yield window, now, route
    window.close()
    qt_application.processEvents()


def test_clock_freshness_uses_clock_field_not_recent_hero_heartbeat(telemetry_window):
    window, now, _ = telemetry_window
    window.on_gsi(gsi())
    assert window.game_clock() == (100, 'Game clock')
    now[0] = 106
    update = gsi()
    del update['map']['clock_time']
    window.on_gsi(update)
    assert window.session.field_status('hero') == 'fresh'
    assert window.game_clock() == (100, 'GSI stale · frozen')
    window.tick()
    assert 'Clock stale' in window.connection_summary.text()
    assert 'GSI stale · frozen' in window.overlay.clock.text()
    assert 'Clock: stale · 6s ago' in window.diagnostics.text()


def test_missing_clock_keeps_manual_estimate_and_explicit_override_works(telemetry_window):
    window, now, _ = telemetry_window
    update = gsi()
    del update['map']['clock_time']
    window.manual_second = 70
    window.on_gsi(update)
    assert window.game_clock() == (70, 'Manual estimate · paused')
    window.on_gsi(gsi(clock=100))
    assert window.game_clock() == (100, 'Game clock')
    window.manual_time.setValue(90)
    window.sync_clock()
    now[0] += 2
    assert window.game_clock() == (92, 'Manual estimate')


def test_missing_inventory_and_skills_are_explicit_in_connection_and_overlay(telemetry_window):
    window, _, _ = telemetry_window
    window.on_gsi(gsi())
    window.tick()
    assert 'Inventory missing' in window.connection_summary.text()
    assert 'Skills missing' in window.connection_summary.text()
    assert 'inventory missing' in window.overlay.note.text()
    assert 'skills missing' in window.overlay.note.text()
    assert 'Inventory: missing · not received' in window.diagnostics.text()
    assert 'Charges: missing · not received' in window.diagnostics.text()
    assert 'clock and inventory received' not in window.gsi_status


def test_stale_inventory_cannot_complete_purchases_on_unrelated_update(telemetry_window):
    window, now, route = telemetry_window
    chosen = next(p for p in route.purchases
                  if p.time >= 0 and sum(other.key == p.key for other in route.purchases) == 1)
    owned = gsi()
    owned['items'] = {'slot0': {'name': 'item_' + chosen.key}}
    # Last-known inventory predates the unrelated heartbeat. Do not apply it anew.
    window.session.ingest(owned)
    now[0] += 6
    window.on_gsi(gsi())
    row = route.purchases.index(chosen)
    assert not window.session.is_complete(chosen)
    assert window.purchases.item(row, 0).checkState() == Qt.CheckState.Unchecked
    window.tick()
    assert 'inventory stale' in window.overlay.note.text()
    window.on_gsi(owned)
    assert window.session.is_complete(chosen)
    assert window.purchases.item(row, 0).checkState() == Qt.CheckState.Checked


def test_manual_skill_undo_survives_payload_without_abilities(telemetry_window):
    window, _, route = telemetry_window
    first = route.skills[0]
    window.mark_skill()
    assert window.manual_skill_history == [first]
    assert window.session.learned[first] == 1
    window.on_gsi(gsi())
    assert window.manual_skill_history == [first]
    assert window.session.learned[first] == 1
    window.undo_skill()
    assert not window.manual_skill_history
    assert window.session.learned[first] == 0


def test_fresh_skills_replace_manual_state_and_later_staleness_is_visible(telemetry_window):
    window, now, route = telemetry_window
    first = route.skills[0]
    window.mark_skill()
    update = gsi()
    update['items'] = {}
    update['abilities'] = {'ability0': {'name': first, 'level': 1}}
    window.on_gsi(update)
    assert not window.manual_skill_history
    assert window.session.learned[first] == 1
    window.tick()
    assert 'Inventory fresh' in window.connection_summary.text()
    assert 'Skills fresh' in window.connection_summary.text()
    skill, _ = window.session.next_skill(route)
    assert ability_name(skill) in window.overlay.skill.text()
    now[0] += 6
    window.tick()
    assert 'Skills stale' in window.connection_summary.text()
    assert 'skills stale' in window.overlay.note.text()
    assert 'Skills: stale · 6s ago' in window.diagnostics.text()


def test_new_hero_without_abilities_clears_previous_manual_undo_history(telemetry_window):
    window, _, _ = telemetry_window
    window.mark_skill()
    assert window.manual_skill_history
    assert window.session.skills_at is None
    window.on_gsi(gsi(hero=2))
    assert window.session.hero_id == 2
    assert not window.manual_skill_history
    assert not window.session.learned
