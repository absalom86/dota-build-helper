import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .builds import normalize, rank_routes
from .catalog import PATCHES
from .models import Purchase, Route
from .paths import user_data_dir

ROOT = Path(__file__).resolve().parent.parent
LOCAL = user_data_dir()
_RATE_LOCK = threading.Lock()
_NEXT_REQUEST = 0.0


class Provider(Protocol):
    def routes(self, hero_id: int, role: int, lane: int, progress, cancel: threading.Event): ...


class DataError(Exception):
    pass


class OpenDota:
    def __init__(self, cache_dir=None):
        self.cache_dir = Path(cache_dir or LOCAL / "cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.stale = []
        self.next_request = 0
        self.cancel = threading.Event()
        self.force_refresh = False

    def cached(self, path, params=None, ttl=3600, allow_stale=False):
        if self.force_refresh and not path.startswith('matches/'):
            return None
        key = hashlib.sha256((path + json.dumps(dict(params or {}), sort_keys=True)).encode()).hexdigest()
        try:
            record = json.loads((self.cache_dir / f"{key}.json").read_text(encoding="utf-8"))
            age = time.time() - record["at"]
            if age < ttl or allow_stale:
                if age >= ttl:
                    message = f"Cached {path}: {int(age / 3600)} hours old"
                    if message not in self.stale:
                        self.stale.append(message)
                return record["data"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def get(self, path, params=None, ttl=3600):
        global _NEXT_REQUEST
        if self.force_refresh and not path.startswith('matches/'):
            ttl=0
        if self.cancel.is_set():
            raise DataError("Search cancelled")
        params = dict(params or {})
        cache_key = hashlib.sha256((path + json.dumps(params, sort_keys=True)).encode()).hexdigest()
        file = self.cache_dir / f"{cache_key}.json"
        cached = None
        try:
            cached = json.loads(file.read_text(encoding="utf-8"))
            if time.time() - cached["at"] < ttl:
                return cached["data"]
        except (OSError, ValueError, KeyError):
            cached = None
        token = os.environ.get("OPENDOTA_API_KEY")
        if token:
            params["api_key"] = token
        url = "https://api.opendota.com/api/" + path + ("?" + urlencode(params) if params else "")
        error = "Network unavailable"
        # One short attempt. Orchestrators own the total deadline; no chained retries.
        for attempt in range(1):
            with _RATE_LOCK:
                now = time.monotonic()
                delay = max(0, _NEXT_REQUEST - now)
                _NEXT_REQUEST = max(now, _NEXT_REQUEST) + 1.05
            if self.cancel.wait(delay):
                raise DataError("Search cancelled")
            self.next_request = time.monotonic() + 1.1
            try:
                with urlopen(Request(url, headers={"User-Agent": "DotaBuildHelper/0.2"}), timeout=3) as response:
                    result = json.load(response)
                temp = file.with_suffix(f".{uuid.uuid4().hex}.tmp")
                temp.write_text(json.dumps({"at": time.time(), "data": result}), encoding="utf-8")
                temp.replace(file)
                return result
            except HTTPError as exc:
                error = f"OpenDota HTTP {exc.code}"
                if exc.code not in (429, 500, 502, 503, 504):
                    break
                retry = exc.headers.get("Retry-After", "")
                delay = min(30, int(retry)) if retry.isdigit() else 2 ** (attempt + 1)
                self.next_request = time.monotonic() + delay
                if exc.code == 429:
                    with _RATE_LOCK:
                        _NEXT_REQUEST = max(_NEXT_REQUEST, self.next_request)
            except (URLError, TimeoutError, OSError, ValueError):
                error = "OpenDota connection or response failed"
                self.next_request = time.monotonic() + 2 ** (attempt + 1)
        if cached:
            age = int((time.time() - cached["at"]) / 3600)
            self.stale.append(f"Cached {path}: {age} hours old ({error})")
            return cached["data"]
        raise DataError(error + "; no cached response available")

    def routes(self, hero_id, role, lane, progress=lambda _: None, cancel=None, on_update=None):
        from .fast_lookup import fast_routes
        return fast_routes(self, hero_id, role, lane, progress, cancel or threading.Event(), on_update)


class Demo:
    def routes(self, hero_id, role, lane, progress=lambda _: None, cancel=None):
        # Deliberately fixed hero, clearly synthetic; never passed through the live provider.
        if hero_id != 1 or role != 1:
            return [], "Demo contains Anti-Mage carry only. Select Anti-Mage / Carry."
        result = []
        for index, late in enumerate(("manta", "black_king_bar", "skadi")):
            keys = [("tango", -60), ("branches", -60), ("branches", -60), ("quelling_blade", -60),
                    ("boots", 180), ("power_treads", 420), ("bfury", 900), (late, 1320), ("basher", 1800)]
            from collections import Counter
            counts = Counter()
            purchases = []
            for key, second in keys:
                counts[key] += 1
                purchases.append(Purchase(key, second, counts[key]))
            result.append(Route(f"demo:{index}", 1, 1, 1, 0,
                                ["Farm into Manta", "Earlier spell protection", "Stats and slow"][index],
                                purchases, ["antimage_mana_break", "antimage_blink", "antimage_mana_break"],
                                [], 0, "SYNTHETIC DEMO · Not a recommended build", "Demo", demo=True,
                                warnings=["Synthetic purchase times and skills for testing the interface only."]))
        return result, "OFFLINE DEMO · Synthetic Anti-Mage carry routes. No live recommendations."
