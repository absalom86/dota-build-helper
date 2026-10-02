import hashlib
import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from dota_helper import updates
from dota_helper.updates import ASSET, REPOSITORY, Release, UpdateError, Updater, version_tuple

DATA = b'MZ' + b'installer fixture' * 100


def release(tag='v9.0.0', data=DATA):
    return Release(tag, 'Test notes', f'https://github.com/{REPOSITORY}/releases/download/{tag}/{ASSET}',
                   hashlib.sha256(data).hexdigest(), len(data))


def payload(item=None):
    item = item or release()
    return {'tag_name': item.tag, 'body': item.notes, 'draft': False, 'prerelease': False,
            'assets': [{'name': ASSET, 'size': item.size, 'browser_download_url': item.url,
                        'digest': f'sha256:{item.sha256}'}]}


@pytest.fixture
def updater(tmp_path, monkeypatch):
    instance = Updater(tmp_path)
    monkeypatch.setattr(instance, '_open', lambda _: pytest.fail('Unexpected network request'))
    return instance


@pytest.mark.parametrize('value', ['v1.2', '../1.2.3', 'v1.2.3-beta', '01.2.3', None, '1.2.3;exe'])
def test_rejects_invalid_versions(value):
    with pytest.raises(UpdateError):
        version_tuple(value)


def test_check_caches_daily_and_manual_can_refresh(updater, monkeypatch):
    calls = []
    monkeypatch.setattr(updater, '_small', lambda url: calls.append(url) or json.dumps(payload()).encode())
    assert updater.check() == release()
    assert not updater.due()
    assert updater.check() == release()
    assert len(calls) == 1
    updater.check(force=True)
    assert len(calls) == 2
    updater.later()
    restored = Updater(updater.root.parent)
    assert restored.release == release() and restored.deferred() and not restored.due()


@pytest.mark.parametrize('tag', ['v' + updates.VERSION, 'v0.1.13'])
def test_never_offers_same_version_or_downgrade(updater, monkeypatch, tag):
    monkeypatch.setattr(updater, '_small', lambda _: json.dumps(payload(release(tag))).encode())
    assert updater.check() is None
    with pytest.raises(UpdateError):
        updater.download(release(tag))
    with pytest.raises(UpdateError):
        updater.launch_installer('irrelevant', release(tag))


@pytest.mark.parametrize('field', ['draft', 'prerelease'])
def test_rejects_unpublished_releases(updater, monkeypatch, field):
    data = payload()
    data[field] = True
    monkeypatch.setattr(updater, '_small', lambda _: json.dumps(data).encode())
    with pytest.raises(UpdateError):
        updater.check()
    assert updater.release is None


@pytest.mark.parametrize('code', [403, 429])
def test_rate_limit_applies_to_manual_checks(updater, monkeypatch, code):
    def limited(_):
        raise HTTPError(updates.API_URL, code, 'limited', {'Retry-After': '3600'}, None)
    monkeypatch.setattr(updater, '_small', limited)
    with pytest.raises(UpdateError, match='rate limited'):
        updater.check()
    with pytest.raises(UpdateError, match='cooling down'):
        updater.check(force=True)
    assert not updater.due()


def test_checksum_fallback_and_exact_asset(updater, monkeypatch):
    data = payload()
    data['assets'][0].pop('digest')
    url = release().url.rsplit('/', 1)[0] + '/SHA256SUMS.txt'
    data['assets'].append({'name': 'SHA256SUMS.txt', 'browser_download_url': url})
    monkeypatch.setattr(updater, '_small', lambda address: json.dumps(data).encode() if address == updates.API_URL
                        else f'{release().sha256}  {ASSET}\n'.encode())
    assert updater.check() == release()
    data['assets'][0]['browser_download_url'] = 'https://example.com/installer.exe'
    with pytest.raises(UpdateError):
        updater.check(force=True)


def test_missing_checksum_never_downloads_installer(updater, monkeypatch):
    data = payload()
    data['assets'][0].pop('digest')
    monkeypatch.setattr(updater, '_small', lambda _: json.dumps(data).encode())
    with pytest.raises(UpdateError, match='no installer checksum'):
        updater.check()


def test_download_verifies_and_reuses_then_rejects_tampered_file(updater, monkeypatch):
    calls = []
    monkeypatch.setattr(updater, '_open', lambda url: calls.append(url) or io.BytesIO(DATA))
    progress = []
    path = updater.download(release(), progress.append)
    assert path.read_bytes() == DATA and progress[-1].endswith('100%')
    assert updater.download(release()) == path and len(calls) == 1
    path.write_bytes(b'MZtampered')
    with pytest.raises(UpdateError, match='verification failed'):
        updater.launch_installer(path, release())
    assert updater.download(release()).read_bytes() == DATA and len(calls) == 2


@pytest.mark.parametrize('data', [b'MZshort', DATA + b'extra', b'ZZ' + DATA[2:], b'MZ' + b'x' * (len(DATA) - 2)])
def test_corrupt_download_never_becomes_executable(updater, monkeypatch, data):
    monkeypatch.setattr(updater, '_open', lambda _: io.BytesIO(data))
    with pytest.raises(UpdateError):
        updater.download(release())
    assert not updater.installer_path(release()).exists()
    assert not list(updater.root.rglob('*.part'))


def test_cancel_before_worker_start_is_not_cleared(updater):
    updater.cancel.set()
    with pytest.raises(UpdateError, match='cancelled'):
        updater.download(release())


def test_cancel_during_download_cleans_partial(updater, monkeypatch):
    monkeypatch.setattr(updater, '_open', lambda _: io.BytesIO(DATA))
    with pytest.raises(UpdateError, match='cancelled'):
        updater.download(release(), lambda _: updater.cancel.set())
    assert not updater.installer_path(release()).exists()
    assert not list(updater.root.rglob('*.part'))


def test_installer_only_launches_explicitly_with_expected_arguments(updater, monkeypatch):
    monkeypatch.setattr(updater, '_open', lambda _: io.BytesIO(DATA))
    calls = []
    monkeypatch.setattr(updates.subprocess, 'Popen', lambda *args, **kwargs: calls.append((args, kwargs)))
    path = updater.download(release())
    assert calls == []
    updater.launch_installer(path, release())
    assert calls[0][0][0] == [str(path), '/SILENT', '/NORESTART', '/UPDATE=1']
    assert 'shell' not in calls[0][1]
    assert calls[0][1]['env']['PYINSTALLER_RESET_ENVIRONMENT'] == '1'


@pytest.mark.parametrize('url', ['http://github.com/a', 'https://evil.com/a',
                               'https://github.com.evil.com/a', 'https://name@github.com/a'])
def test_untrusted_redirects_are_rejected(url):
    with pytest.raises(UpdateError):
        updates.TrustedRedirects().redirect_request(Request(updates.API_URL), None, 302, '', {}, url)


def test_dialog_defers_install_until_out_of_match(tmp_path, monkeypatch, qt_application):
    from PySide6.QtWidgets import QWidget
    from dota_helper.update_ui import UpdateController
    import sys
    window = QWidget()
    window.observed_game_state = 'DOTA_GAMERULES_STATE_GAME_IN_PROGRESS'
    window.manual_running = False
    window.closing = False
    jobs = []
    window.launch_worker = lambda *args, **kwargs: jobs.append((args, kwargs))
    controller = UpdateController(window, tmp_path)
    controller.updater.release = release()
    controller.updater.state['last_attempt'] = updates.time.time()
    controller.path = controller.updater.installer_path(release())
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    controller.show()
    assert not controller.install_button.isEnabled()
    controller.install()
    assert not jobs
    window.observed_game_state = 'DOTA_GAMERULES_STATE_POST_GAME'
    controller.refresh()
    assert controller.install_button.isEnabled()
    controller.install()
    assert len(jobs) == 1
    # A game starts while verification is running: re-check before closing.
    window.observed_game_state = 'DOTA_GAMERULES_STATE_HERO_SELECTION'
    jobs[0][0][1](controller.path)
    assert not hasattr(window, 'pending_update')
    controller.later()
    assert controller.button.text() == 'Updates'
    assert controller.updater.deferred()
    controller.timer.stop()
    window.close()
