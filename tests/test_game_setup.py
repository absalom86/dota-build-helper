from pathlib import Path

import pytest

from dota_helper import game_setup
from dota_helper.app import MainWindow
from dota_helper.setup_ui import SetupDialog


TOKEN = 'test-local-connection-token-12345'


def dota(root):
    executable = root / 'game' / 'bin' / 'win64' / 'dota2.exe'
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b'fixture; never executed')
    return root


def test_steam_library_discovery_and_deduplication(tmp_path):
    steam = tmp_path / 'Steam'
    library = tmp_path / 'Games'
    root = dota(library / 'steamapps' / 'common' / 'Dota custom folder')
    (steam / 'steamapps').mkdir(parents=True)
    escaped = str(library).replace('\\', '\\\\')
    (steam / 'steamapps' / 'libraryfolders.vdf').write_text(
        f'"libraryfolders" {{ "0" {{ "path" "{escaped}" }} "1" "{escaped}" }}')
    (library / 'steamapps' / 'appmanifest_570.acf').write_text(
        '"AppState" { "appid" "570" "installdir" "Dota custom folder" }')
    assert game_setup.dota_directories([steam, library]) == [root.resolve()]


def test_missing_manifest_default_directory_and_reject_traversal(tmp_path):
    root = dota(tmp_path / 'steamapps' / 'common' / 'dota 2 beta')
    assert game_setup.dota_directories([tmp_path]) == [root.resolve()]
    (tmp_path / 'steamapps' / 'appmanifest_570.acf').write_text('"installdir" "../elsewhere"')
    assert game_setup.dota_directories([tmp_path]) == []


def test_config_install_is_idempotent_and_preserves_existing_files(tmp_path):
    root = dota(tmp_path / 'Dota')
    installed = game_setup.install_config(root, TOKEN)
    assert game_setup.config_ready(root, TOKEN)
    timestamp = installed.stat().st_mtime_ns
    game_setup.install_config(root, TOKEN)
    assert installed.stat().st_mtime_ns == timestamp
    assert not list(installed.parent.glob('*.bak'))
    other = installed.parent / 'gamestate_integration_other.cfg'
    other.write_text('another app config')
    installed.write_bytes(b'original contents')
    game_setup.install_config(root, TOKEN)
    assert next(installed.parent.glob('*.bak')).read_bytes() == b'original contents'
    assert other.read_text() == 'another app config'
    assert game_setup.config_ready(root, TOKEN)


def test_install_rejects_wrong_folder_and_unsafe_token(tmp_path):
    with pytest.raises(ValueError):
        game_setup.install_config(tmp_path, TOKEN)
    root = dota(tmp_path / 'Dota')
    with pytest.raises(ValueError):
        game_setup.install_config(root, '"invalid token"')
    assert not game_setup.config_path(root).exists()


def test_launch_arguments_and_running_game_guard(tmp_path, monkeypatch):
    root = dota(tmp_path / 'Dota')
    steam = tmp_path / 'Steam' / 'steam.exe'
    game_setup.install_config(root, TOKEN)
    calls = []
    monkeypatch.setattr(game_setup, 'steam_executable', lambda: steam)
    monkeypatch.setattr(game_setup, 'dota_running', lambda: False)
    monkeypatch.setattr(game_setup.subprocess, 'Popen', lambda args, **kwargs: calls.append(args))
    game_setup.launch_dota(root, TOKEN)
    assert calls == [[str(steam), '-applaunch', '570', '-gamestateintegration']]
    monkeypatch.setattr(game_setup, 'dota_running', lambda: True)
    with pytest.raises(ValueError, match='already running'):
        game_setup.launch_dota(root, TOKEN)
    assert len(calls) == 1
    with pytest.raises(ValueError, match='Connect Dota first'):
        game_setup.launch_dota(root, 'different-token')


@pytest.fixture
def setup_dialog(tmp_path, monkeypatch, qt_application):
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path / 'profile')
    root = dota(tmp_path / 'Dota')
    monkeypatch.setattr(game_setup, 'dota_directories', lambda: [root])
    monkeypatch.setattr('dota_helper.setup_ui.credentials.load_token', lambda: 'existing-test-key')
    window = MainWindow(start_services=False)
    window.timer.stop()
    window.capture_timer.stop()
    # Simulate an available receiver without binding a port.
    window.receiver = object()
    dialog = SetupDialog(window)
    yield dialog, root
    dialog.close()
    window.receiver = None
    window.close()
    qt_application.processEvents()


def test_quick_setup_connects_without_folder_prompt_and_does_not_launch_implicitly(setup_dialog, monkeypatch):
    dialog, root = setup_dialog
    launches = []
    monkeypatch.setattr(game_setup, 'launch_dota', lambda *args: launches.append(args))
    assert not dialog.launch_button.isEnabled()
    assert not dialog.key.text()
    dialog.connect_game()
    assert game_setup.config_ready(root, dialog.owner.settings['gsi_token'])
    assert dialog.launch_button.isEnabled()
    assert dialog.owner.settings['dota_directory'] == str(root)
    assert not launches
    dialog.start_game()
    assert len(launches) == 1
    assert 'Launch requested' in dialog.status.text()


def test_unavailable_receiver_and_write_failure_are_visible(setup_dialog, monkeypatch):
    dialog, _ = setup_dialog
    monkeypatch.setattr(game_setup, 'install_config', lambda *args: (_ for _ in ()).throw(PermissionError('Read only')))
    dialog.connect_game()
    assert not dialog.launch_button.isEnabled()
    assert 'Read only' in dialog.status.text()
    dialog.owner.receiver = None
    dialog.refresh()
    assert 'receiver unavailable' in dialog.status.text()


def test_key_saved_only_on_explicit_action_and_not_in_settings(setup_dialog, monkeypatch):
    dialog, _ = setup_dialog
    saved = []
    monkeypatch.setattr('dota_helper.setup_ui.credentials.save_token', saved.append)
    monkeypatch.setattr(dialog.owner.draft, 'refresh_meta', lambda: None)
    dialog.key.setText('private-test-token')
    assert not saved
    dialog.store_key()
    assert saved == ['private-test-token']
    assert not dialog.key.text()
    assert 'private-test-token' not in dialog.owner.settings_file.read_text()
