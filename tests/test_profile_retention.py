import json
from pathlib import Path

import pytest

from dota_helper import credentials, profile
from dota_helper.app import MainWindow


@pytest.fixture
def key_file(tmp_path, monkeypatch):
    path = tmp_path / 'stratz-key.bin'
    monkeypatch.delenv('STRATZ_API_TOKEN', raising=False)
    monkeypatch.setattr(credentials, 'credential_path', lambda: path)
    return path


def test_key_replacement_keeps_encrypted_backup(key_file):
    credentials.save_token('old-test-key')
    old_bytes = key_file.read_bytes()
    credentials.save_token('new-test-key')
    assert credentials.load_token() == 'new-test-key'
    assert profile.backup_path(key_file).read_bytes() == old_bytes
    assert b'old-test-key' not in old_bytes


def test_wrong_account_does_not_replace_existing_key(key_file, monkeypatch):
    credentials.save_token('existing-test-key')
    original = key_file.read_bytes()
    monkeypatch.setattr(credentials, '_crypt', lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('wrong account')))
    with pytest.raises(RuntimeError, match='still present'):
        credentials.load_token()
    with pytest.raises(RuntimeError, match='still present'):
        credentials.save_token('replacement-test-key')
    assert key_file.read_bytes() == original
    assert not profile.backup_path(key_file).exists()


def test_credential_load_recovers_backup_without_modifying_original(key_file):
    credentials.save_token('previous-test-key')
    credentials.save_token('current-test-key')
    key_file.write_bytes(b'corrupt ciphertext')
    assert credentials.load_token() == 'previous-test-key'
    assert key_file.read_bytes() == b'corrupt ciphertext'


def test_failed_atomic_save_retains_original_key(key_file, monkeypatch):
    credentials.save_token('existing-test-key')
    original = key_file.read_bytes()
    replace = Path.replace
    def fail_target(self, target):
        if target == key_file:
            raise OSError('simulated interrupted save')
        return replace(self, target)
    monkeypatch.setattr(Path, 'replace', fail_target)
    with pytest.raises(OSError):
        credentials.save_token('new-test-key')
    assert key_file.read_bytes() == original
    assert credentials.load_token() == 'existing-test-key'


def test_settings_recover_last_good_backup(tmp_path):
    path = tmp_path / 'settings.json'
    original = {'role': 5, 'gsi_token': 'local-connection-test-token'}
    profile.save_settings(path, original)
    profile.save_settings(path, {**original, 'overlay_w': 300})
    path.write_text('{invalid')
    assert profile.load_settings(path) == original
    profile.save_settings(path, {**original, 'overlay_w': 400})
    assert profile.load_settings(path)['overlay_w'] == 400
    assert json.loads(profile.backup_path(path).read_text()) == original


def test_unreadable_settings_are_not_reset_to_defaults(tmp_path):
    path = tmp_path / 'settings.json'
    path.write_text('{invalid')
    with pytest.raises(RuntimeError, match='preserved'):
        profile.save_settings(path, {'role': 1})
    assert path.read_text() == '{invalid'


def test_existing_profile_load_preserves_settings_and_connection_token(tmp_path, monkeypatch, qt_application):
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    data = {'role': 5, 'hero_id': 48, 'gsi_token': 'persistent-test-connection-token',
            'dota_directory': 'remembered-installation', 'custom_upgrade_marker': 'keep'}
    profile.save_settings(tmp_path / 'settings.json', data)
    window = MainWindow(start_services=False)
    assert window.existing_profile
    assert window.role.currentData() == 5 and window.hero.currentData() == 48
    assert window.settings['gsi_token'] == data['gsi_token']
    window.close()
    saved = profile.load_settings(tmp_path / 'settings.json')
    assert saved['custom_upgrade_marker'] == 'keep'
    assert saved['dota_directory'] == 'remembered-installation'
    assert saved['gsi_token'] == data['gsi_token']
    qt_application.processEvents()
