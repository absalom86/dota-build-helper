"""Optional, public GitHub release updates. Never reads or sends API credentials."""
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .profile import atomic_write
from .providers import DataError
from .version import VERSION

REPOSITORY = 'absalom86/dota-build-helper'
RELEASES_URL = f'https://github.com/{REPOSITORY}/releases/latest'
API_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
ASSET = 'DotaBuildHelper-Setup.exe'
DAY = 86400
MAX_INSTALLER = 200 * 1024 * 1024
MAX_METADATA = 2 * 1024 * 1024


class UpdateError(DataError):
    pass


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value):
        raise UpdateError('The release has an unsupported version number.')
    return tuple(map(int, value.removeprefix('v').split('.')))


class TrustedRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443)
                or parsed.hostname not in {'github.com', 'api.github.com',
                                          'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}):
            raise UpdateError('GitHub returned an unexpected download location.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass(frozen=True)
class Release:
    tag: str
    notes: str
    url: str
    sha256: str
    size: int

    def validate(self):
        version_tuple(self.tag)
        if (self.url != f'https://github.com/{REPOSITORY}/releases/download/{self.tag}/{ASSET}'
                or not isinstance(self.sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', self.sha256)
                or type(self.size) is not int or not 0 < self.size <= MAX_INSTALLER
                or not isinstance(self.notes, str) or len(self.notes) > 20000):
            raise UpdateError('Release download metadata is incomplete or invalid.')
        return self


class Updater:
    def __init__(self, root, current=VERSION):
        self.root = Path(root) / 'updates'
        self.current = current
        self.state_file = self.root / 'state.json'
        self.state = {}
        self.release = None
        self.message = ''
        self.cancel = threading.Event()
        self.opener = build_opener(TrustedRedirects())
        try:
            state = json.loads(self.state_file.read_text(encoding='utf-8'))
            if isinstance(state, dict):
                self.state = state
                release = Release(**state['release']).validate()
                if version_tuple(release.tag) > version_tuple(current):
                    self.release = release
        except (OSError, ValueError, KeyError, TypeError, UpdateError):
            pass

    def _time(self, key):
        value = self.state.get(key)
        return value if type(value) in (int, float) and 0 <= value <= time.time() + 7 * DAY else 0

    def due(self):
        return time.time() >= max(self._time('last_attempt') + DAY, self._time('retry_at'))

    def deferred(self):
        return time.time() < self._time('deferred_until')

    def save(self):
        self.state['release'] = asdict(self.release) if self.release else None
        atomic_write(self.state_file, json.dumps(self.state).encode('utf-8'))

    def later(self):
        self.state['deferred_until'] = time.time() + DAY
        self.save()

    def _open(self, url):
        request = Request(url, headers={'User-Agent': f'DotaBuildHelper/{self.current}',
                                      'Accept': 'application/vnd.github+json' if url == API_URL else 'application/octet-stream'})
        return self.opener.open(request, timeout=8)

    def _small(self, url):
        with self._open(url) as response:
            data = response.read(MAX_METADATA + 1)
        if len(data) > MAX_METADATA:
            raise UpdateError('Release information is too large.')
        return data

    def check(self, force=False):
        if time.time() < self._time('retry_at'):
            raise UpdateError('GitHub update checks are cooling down. Try again later.')
        if not force and not self.due():
            return self.release
        self.state['last_attempt'] = time.time()
        self.save()
        try:
            payload = json.loads(self._small(API_URL))
            if not isinstance(payload, dict):
                raise UpdateError('GitHub returned invalid release information.')
            if payload.get('draft') or payload.get('prerelease'):
                raise UpdateError('No stable release is available from this response.')
            tag = payload.get('tag_name')
            if version_tuple(tag) <= version_tuple(self.current):
                self.release = None
                self.message = f'You are up to date (v{self.current}).'
            else:
                assets = payload.get('assets') or []
                installer = [a for a in assets if isinstance(a, dict) and a.get('name') == ASSET]
                if len(installer) != 1:
                    raise UpdateError('This release does not contain a Windows installer yet.')
                asset = installer[0]
                digest = asset.get('digest') or ''
                sha = digest.removeprefix('sha256:') if isinstance(digest, str) and digest.startswith('sha256:') else ''
                if not re.fullmatch(r'[0-9a-f]{64}', sha):
                    checksum_url = f'https://github.com/{REPOSITORY}/releases/download/{tag}/SHA256SUMS.txt'
                    if not any(isinstance(a, dict) and a.get('name') == 'SHA256SUMS.txt'
                               and a.get('browser_download_url') == checksum_url for a in assets):
                        raise UpdateError('This release has no installer checksum. Use the release page to review it.')
                    lines = self._small(checksum_url).decode('utf-8-sig').splitlines()
                    values = [m[1].lower() for line in lines
                              if (m := re.fullmatch(r'([0-9a-fA-F]{64})\s+\*?' + re.escape(ASSET), line.strip()))]
                    if len(values) != 1:
                        raise UpdateError('The release installer checksum is missing or ambiguous.')
                    sha = values[0]
                self.release = Release(tag, str(payload.get('body') or '')[:20000],
                                       asset.get('browser_download_url'), sha, asset.get('size')).validate()
                self.message = f'{tag} is available.'
            self.save()
            return self.release
        except HTTPError as exc:
            if exc.code in (403, 429):
                now = time.time()
                try:
                    retry = max(now + float(exc.headers.get('Retry-After', 60)),
                                float(exc.headers.get('X-RateLimit-Reset', 0)))
                except (TypeError, ValueError):
                    retry = now + 3600
                self.state['retry_at'] = min(now + DAY, max(now + 60, retry))
                self.save()
                raise UpdateError('GitHub update checks are rate limited. Try again later.') from None
            raise UpdateError('No published release found.' if exc.code == 404 else f'GitHub update check failed (HTTP {exc.code}).') from None
        except (OSError, URLError, ValueError, TypeError):
            raise UpdateError('Could not check for updates. Your current app remains usable.') from None

    def installer_path(self, release):
        release.validate()
        return self.root / release.tag / ASSET

    def verify(self, path, release):
        release.validate()
        path = Path(path)
        if path.resolve() != self.installer_path(release).resolve():
            raise UpdateError('Unexpected installer path.')
        try:
            with path.open('rb') as stream:
                header = stream.read(2)
                stream.seek(0)
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if header != b'MZ' or path.stat().st_size != release.size or actual != release.sha256:
                raise UpdateError('Installer verification failed. Download it again.')
        except OSError:
            raise UpdateError('The downloaded installer is missing or unreadable. Download it again.') from None
        return path

    def download(self, release, progress=lambda _: None):
        path = self.installer_path(release)
        if version_tuple(release.tag) <= version_tuple(self.current):
            raise UpdateError('This update is not newer than the running app.')
        if self.cancel.is_set():
            raise UpdateError('Update download cancelled.')
        if path.is_file():
            try:
                return self.verify(path, release)
            except UpdateError:
                pass
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.part')
        started, count = time.monotonic(), 0
        try:
            with self._open(release.url) as response, temporary.open('wb') as output:
                while True:
                    if self.cancel.is_set():
                        raise UpdateError('Update download cancelled.')
                    if time.monotonic() - started > 120:
                        raise UpdateError('Update download timed out. Try again later.')
                    chunk = response.read(128 * 1024)
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > release.size:
                        raise UpdateError('The installer is larger than its release metadata.')
                    output.write(chunk)
                    progress(f'Downloading {release.tag}: {min(100, count * 100 // release.size)}%')
            if self.cancel.is_set():
                raise UpdateError('Update download cancelled.')
            # Check the partial file before it can become an executable download.
            with temporary.open('rb') as stream:
                header = stream.read(2)
                stream.seek(0)
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if header != b'MZ' or count != release.size or actual != release.sha256:
                raise UpdateError('Installer checksum verification failed. Nothing was installed.')
            temporary.replace(path)
            return self.verify(path, release)
        except (OSError, URLError):
            raise UpdateError('The update download failed. Nothing was installed; try again later.') from None
        finally:
            temporary.unlink(missing_ok=True)

    def launch_installer(self, path, release):
        if version_tuple(release.tag) <= version_tuple(self.current):
            raise UpdateError('This update is not newer than the running app.')
        path = self.verify(path, release)
        if os.name != 'nt':
            raise UpdateError('The installer requires Windows.')
        try:
            # A list of arguments avoids shell interpretation. Inno restarts the
            # installed application after a successful explicitly requested update.
            environment = os.environ.copy()
            # Unpack the restarted one-file app independently of this app's
            # temporary PyInstaller directory, which disappears when we exit.
            environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
            return subprocess.Popen([str(path), '/SILENT', '/NORESTART', '/UPDATE=1'],
                                    close_fds=True, env=environment)
        except OSError:
            raise UpdateError('Could not start the installer. Reopen the helper and retry.') from None
