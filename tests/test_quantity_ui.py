from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from dota_helper import guides, quantity_evidence, starting_items
from dota_helper.app import MainWindow
from dota_helper.models import Purchase, Route


@pytest.fixture
def quantity_ui(tmp_path, monkeypatch, qt_application):
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    monkeypatch.setattr(starting_items, 'user_data_dir', lambda: tmp_path)
    monkeypatch.setattr(quantity_evidence, 'user_data_dir', lambda: tmp_path)
    starting_items.load.cache_clear()
    quantity_evidence._load.cache_clear()
    window = MainWindow(start_services=False)
    window.timer.stop()
    window.capture_timer.stop()
    window.draft.meta_active = False
    queued, workers = [], []
    monkeypatch.setattr(QTimer, 'singleShot', lambda delay, callback: queued.append((delay, callback)))

    def launch(fn, done, fail=None, **_):
        workers.append({'route': window.current_route(), 'done': done, 'fail': fail})

    monkeypatch.setattr(window, 'launch_worker', launch)
    routes = [Route(
        f'stratz:{match}:0', 1, 1, 1, 0, f'Fixture {match}',
        [Purchase('branches', -60), Purchase('tango', -60), Purchase('boots', 120),
         Purchase('bfury', 900)], ['antimage_mana_break'], [match], 0,
        'Test purchase log', 'Fixture player', source='STRATZ', account_id=12345,
        player_slot=0,
    ) for match in (100, 101)]
    window.routes = routes
    window.session.accept_routes(routes)
    window.render_routes()

    def drain():
        for _ in range(20):
            if not queued:
                return
            _, callback = queued.pop(0)
            callback()
        pytest.fail('Quantity scheduling did not settle')

    yield window, routes, workers, queued, drain
    # No real QThreads were started, so closing does not need a queued retry.
    window.close()
    qt_application.processEvents()
    starting_items.load.cache_clear()
    quantity_evidence._load.cache_clear()


def conflict():
    return {'status': 'conflict', 'message': 'The two purchase logs disagree.',
            'counts': {'branches': 4, 'tango': 1}}


def test_default_selected_route_schedules_one_automatic_check(quantity_ui, monkeypatch):
    window, routes, workers, queued, drain = quantity_ui
    window.services_started = True
    monkeypatch.setattr(QMessageBox, 'question', lambda *_: pytest.fail('Automatic check must not apply a correction'))
    window.render_routes()
    assert queued and window.current_route() is routes[0]
    drain()
    assert len(workers) == 1 and workers[0]['route'] is routes[0]
    assert window.quantity_busy and not window.verify_quantities_button.isEnabled()
    workers[0]['done'](conflict())
    assert not window.quantity_busy and window.verify_quantities_button.isEnabled()
    assert starting_items.correction(routes[0]) is None
    window.render_routes()
    drain()
    assert len(workers) == 1
    assert 'purchase logs disagree' in window.quantity_preview.text()


def test_switch_during_check_reschedules_current_route_without_applying_stale_result(quantity_ui, monkeypatch):
    window, routes, workers, _, drain = quantity_ui
    window.services_started = True
    prompts = []
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: prompts.append(args) or QMessageBox.StandardButton.Yes)
    window.verify_starting_quantities(True)
    assert workers[0]['route'] is routes[0]
    window.route_choice.setCurrentIndex(1)
    drain()
    assert len(workers) == 1  # A still owns the only quantity request.
    workers[0]['done'](conflict())
    assert not prompts
    assert starting_items.correction(routes[0]) is None
    assert starting_items.correction(routes[1]) is None
    drain()
    assert len(workers) == 2 and workers[1]['route'] is routes[1]
    workers[1]['done']({'status': 'unavailable', 'message': 'No parsed log.', 'counts': None})
    assert not window.quantity_busy
    assert 'No parsed log.' in window.quantity_preview.text()
    window.render_routes()
    drain()
    assert len(workers) == 2  # An unavailable result must not produce a retry loop.


@pytest.mark.parametrize('accept', [False, True])
def test_conflicting_counts_require_explicit_user_acceptance(quantity_ui, monkeypatch, accept):
    window, routes, workers, _, _ = quantity_ui
    original = [vars(p).copy() for p in routes[0].purchases]
    questions = []

    def answer(*args):
        questions.append(args)
        return QMessageBox.StandardButton.Yes if accept else QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, 'question', answer)
    window.verify_starting_quantities(True)
    workers[0]['done'](conflict())
    assert len(questions) == 1
    assert questions[0][-1] == QMessageBox.StandardButton.No
    assert 'Neither log proves a complete starting inventory' in questions[0][2]
    expected = {'branches': 4, 'tango': 1} if accept else None
    assert starting_items.correction(routes[0]) == expected
    assert [vars(p) for p in routes[0].purchases] == original
    if accept:
        assert '(corrected)' in window.quantity_preview.text()
        assert 'OpenDota log accepted by user' in window.quantity_preview.toolTip()


def test_old_generation_result_does_not_prompt_or_change_current_quantities(quantity_ui, monkeypatch):
    window, routes, workers, _, _ = quantity_ui
    monkeypatch.setattr(QMessageBox, 'question', lambda *_: pytest.fail('Old selection cannot ask to apply counts'))
    window.verify_starting_quantities(True)
    window.generation += 1
    workers[0]['done'](conflict())
    assert not window.quantity_busy
    assert starting_items.correction(routes[0]) is None


def export_to_test_folder(window, route, tmp_path, monkeypatch):
    folder = tmp_path / 'chosen-guides'
    folder.mkdir(exist_ok=True)
    window.settings['guide_export_dir'] = str(folder)
    monkeypatch.setattr(guides, 'guide_directories', lambda: [tmp_path / 'account-a', tmp_path / 'account-b'])
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *_: pytest.fail('Saved folder must avoid account reprompt'))
    suggested = []

    def choose_file(*args):
        suggested.append(Path(args[2]))
        return args[2], 'Dota hero guide (*.build)'

    monkeypatch.setattr(QFileDialog, 'getSaveFileName', choose_file)
    monkeypatch.setattr(QMessageBox, 'information', lambda *_: None)
    window.export_shop_guide()
    path = folder / guides.filename(route)
    assert suggested == [path] and path.is_file()
    return path


def test_export_reuses_saved_folder_and_quantity_edit_requires_reexport(quantity_ui, tmp_path, monkeypatch):
    window, routes, _, _, _ = quantity_ui
    path = export_to_test_folder(window, routes[0], tmp_path, monkeypatch)
    original = path.read_bytes()
    assert 'export is up to date' in window.guide_status.text()
    starting_items.save(routes[0], {'branches': 5, 'tango': 2})
    window.render_routes()
    assert 'build or quantities changed · export again' in window.guide_status.text()
    assert path.read_bytes() == original  # Editing a quantity does not silently rewrite the user's guide.
    window.export_shop_guide()
    assert 'export is up to date' in window.guide_status.text()
    assert path.read_bytes() != original
    starting_items.reset(routes[0])
    window.render_routes()
    assert 'build or quantities changed · export again' in window.guide_status.text()


def test_export_status_detects_external_file_change_and_missing_file(quantity_ui, tmp_path, monkeypatch):
    window, routes, _, _, _ = quantity_ui
    path = export_to_test_folder(window, routes[0], tmp_path, monkeypatch)
    path.write_text('Changed outside the helper', encoding='utf-8')
    window.refresh_guide_status()
    assert 'exported file changed' in window.guide_status.text()
    path.unlink()
    window.refresh_guide_status()
    assert 'exported file missing' in window.guide_status.text()
