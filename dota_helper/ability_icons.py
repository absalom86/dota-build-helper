"""Small public Valve ability images, loaded asynchronously and cached locally."""
from pathlib import Path
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, HTTPRedirectHandler, build_opener

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QPixmap

from .catalog import DATA
from .profile import atomic_write


def icon_url(key):
    if not isinstance(key, str) or not re.fullmatch(r'[a-z0-9_]{1,120}', key) or key.startswith('special_bonus_'):
        return None
    return f'https://cdn.akamai.steamstatic.com/apps/dota2/images/dota_react/abilities/{key}.png'


class AbilityIcons(QObject):
    changed = Signal()
    loaded = Signal(str, bytes)

    def __init__(self, directory, parent=None, *, online=True):
        super().__init__(parent)
        self.directory = Path(directory)
        self.online = online
        self.images, self.attempted, self.pending = {}, set(), {}
        self.queue = []
        self.closed = False
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ability-icons")
        self.loaded.connect(self._accept)

    def get(self, key):
        if key in self.images:
            return self.images[key]
        if not icon_url(key):
            return QPixmap()
        for directory in (DATA / 'ability_icons', self.directory):
            path = directory / f'{key}.png'
            if path.is_file() and path.stat().st_size <= 256_000:
                pixmap = QPixmap(str(path))
                if not pixmap.isNull() and pixmap.width() <= 512 and pixmap.height() <= 512:
                    self.images[key] = pixmap
                    return pixmap
        if self.online and not self.closed and key not in self.attempted:
            self.attempted.add(key)
            self.queue.append(key)
            self._pump()
        return QPixmap()

    def _pump(self):
        while self.queue and len(self.pending) < 4 and not self.closed:
            key = self.queue.pop(0)
            future = self.pool.submit(self._fetch, icon_url(key))
            self.pending[key] = future
            future.add_done_callback(lambda f, k=key: self._finished(k, f))

    @staticmethod
    def _fetch(url):
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        try:
            request = Request(url, headers={'User-Agent': 'DotaBuildHelper/ability-icons'})
            with build_opener(NoRedirect).open(request, timeout=6) as response:
                data = response.read(256_001)
            return data if len(data) <= 256_000 and data.startswith(b'\x89PNG\r\n\x1a\n') else b''
        except Exception:
            return b''

    def _finished(self, key, future):
        if self.closed:
            return
        try:
            self.loaded.emit(key, future.result())
        except RuntimeError:
            pass  # The owner may already have been destroyed during shutdown.

    @Slot(str, bytes)
    def _accept(self, key, data):
        self.pending.pop(key, None)
        if self.closed:
            return
        image = QPixmap()
        if data and image.loadFromData(data) and image.width() <= 512 and image.height() <= 512:
            self.images[key] = image
            try:
                atomic_write(self.directory / f'{key}.png', data)
            except OSError:
                pass  # A read-only cache must not prevent displaying the image.
            self.changed.emit()
        self._pump()

    def close(self):
        self.closed = True
        self.queue.clear()
        self.pool.shutdown(wait=False, cancel_futures=True)
