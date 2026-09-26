"""Keep observed live match MMR by exact match ID, separately from build lookup."""
from dataclasses import dataclass, replace
from email.utils import parsedate_to_datetime
from http.client import HTTPException
import json
import math
from pathlib import Path
import re
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

from .ratings import numeric_mmr


URL = 'https://api.opendota.com/api/live'
SOURCE = 'OpenDota live feed'
MIN_INTERVAL = 120
MAX_BACKOFF = 86400
MAX_AGE = 30 * 86400
MAX_RECORDS = 10000
SAFE_ERRORS = frozenset({'Connection timed out', 'TLS connection failed', 'Network connection failed',
                         'Invalid live feed response', 'Could not save match MMR observations'})


def _match_id(value):
    if type(value) is int:
        return str(value) if 0 < value < 2 ** 64 else None
    if isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,19}', value):
        return value if int(value) < 2 ** 64 else None
    return None


def _hero_id(value):
    return value if type(value) is int and 0 < value < 2 ** 32 else None


def _hero_ids(values):
    if not isinstance(values, list):
        return []
    return sorted({value for value in values if _hero_id(value) is not None})


def _timestamp(value):
    try:
        return (float(value) if type(value) in (int, float) and math.isfinite(value)
                and value >= 0 else None)
    except OverflowError:
        return None


def _mmr(value):
    try:
        return numeric_mmr(value)
    except OverflowError:
        return None


def _safe_error(value):
    if isinstance(value, str) and (value in SAFE_ERRORS or re.fullmatch(r'HTTP [1-5][0-9]{2}', value)):
        return value
    return None


def _network_error(exc):
    cause = exc.reason if isinstance(exc, URLError) else exc
    if isinstance(cause, TimeoutError):
        return 'Connection timed out'
    if isinstance(cause, ssl.SSLError):
        return 'TLS connection failed'
    return 'Network connection failed'


@dataclass(frozen=True)
class RefreshResult:
    fetched: bool
    count: int
    status: str
    error: str | None = None


class LiveRatings:
    def __init__(self, root):
        self.path = Path(root) / 'match-ratings.json'
        self.records = {}
        self.last_fetch = 0.0
        self.next_refresh_at = 0.0
        self.last_success = 0.0
        self.last_error = None
        self.last_count = 0
        now = time.time()
        try:
            payload = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(payload, dict):
                return
            entries = payload.get('matches', {})
            if isinstance(entries, dict):
                for mid, record in entries.items():
                    if not _match_id(mid) or not isinstance(record, dict):
                        continue
                    mmr = _mmr(record.get('average_mmr'))
                    observed = _timestamp(record.get('observed_at'))
                    if (mmr and observed is not None and now - MAX_AGE <= observed <= now + 300
                            and record.get('source') == SOURCE):
                        self.records[mid] = dict(average_mmr=mmr, observed_at=observed, source=SOURCE)
                        heroes = _hero_ids(record.get('hero_ids'))
                        if heroes:
                            self.records[mid]['hero_ids'] = heroes
            last = _timestamp(payload.get('last_fetch'))
            if last is not None and last <= now + 300:
                self.last_fetch = last
            retry = _timestamp(payload.get('next_refresh_at'))
            if retry is not None:
                self.next_refresh_at = min(retry, self.last_fetch + MAX_BACKOFF)
            self.next_refresh_at = max(self.next_refresh_at, self.last_fetch + MIN_INTERVAL)
            success = _timestamp(payload.get('last_success'))
            if success is not None and success <= now + 300:
                self.last_success = success
            self.last_error = _safe_error(payload.get('last_error'))
            count = payload.get('last_count')
            if type(count) is int and 0 <= count <= MAX_RECORDS:
                self.last_count = count
            self._prune(now)
        except (OSError, ValueError, TypeError):
            # A broken optional cache must never affect builds or settings.
            pass

    def _prune(self, now):
        valid = ((mid, record) for mid, record in self.records.items()
                 if now - MAX_AGE <= record['observed_at'] <= now + 300)
        self.records = dict(sorted(valid, key=lambda item: item[1]['observed_at'], reverse=True)[:MAX_RECORDS])

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f'.{uuid.uuid4().hex}.tmp')
        try:
            temporary.write_text(json.dumps(dict(version=1, last_fetch=self.last_fetch,
                                                next_refresh_at=self.next_refresh_at, last_success=self.last_success,
                                                last_error=self.last_error, last_count=self.last_count, matches=self.records),
                                            separators=(',', ':'), allow_nan=False), encoding='utf-8')
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def status_text(self):
        """Safe, durable diagnostics without URLs, response bodies or exception text."""
        remaining = max(0, math.ceil(self.next_refresh_at - time.time()))
        retry = f'retry in {remaining}s' if remaining else 'retry due'
        if self.last_error:
            retained = 'saved readings retained' if self.observation_count() else 'no saved readings'
            return f'MMR feed: {self.last_error}; {retained}; {retry}'
        if self.last_success:
            return (f'MMR feed ready: {self.last_count} positive readings in latest response'
                    if self.last_count else 'MMR feed responded with no positive readings')
        if self.last_fetch:
            return f'MMR feed outcome unavailable; {retry}'
        return 'MMR feed waiting for first check'

    def observation_count(self):
        """Read a published cache snapshot without mutating it or fetching data."""
        now = time.time()
        records = self.records
        return sum(now - MAX_AGE <= record['observed_at'] <= now + 300
                   for record in records.values())

    def candidates(self, hero_id, minimum_mmr=7000):
        """Find observed games containing this hero; completion and role need verification."""
        if (_hero_id(hero_id) is None or type(minimum_mmr) not in (int, float)
                or not 0 <= minimum_mmr < 30000):
            return []
        now = time.time()
        records = self.records
        result = []
        for mid, record in records.items():
            if (hero_id in record.get('hero_ids', []) and record['average_mmr'] >= minimum_mmr
                    and now - MAX_AGE <= record['observed_at'] <= now + 300):
                result.append(dict(match_id=int(mid), average_mmr=record['average_mmr'],
                                   observed_at=record['observed_at']))
        return sorted(result, key=lambda entry: (entry['average_mmr'], entry['observed_at'], entry['match_id']),
                      reverse=True)

    def refresh(self):
        """Perform at most one anonymous request; failures retain observations."""
        now = time.time()
        if now < self.next_refresh_at:
            return RefreshResult(False, 0, self.status_text(), self.last_error)
        self.last_fetch = now
        self.next_refresh_at = now + MIN_INTERVAL
        count = 0
        error = None
        try:
            request = Request(URL, headers={'User-Agent': 'DotaBuildHelper', 'Accept': 'application/json'})
            with urlopen(request, timeout=3) as response:
                payload = json.loads(response.read(2_000_001))
            if not isinstance(payload, list):
                raise ValueError('Expected a live-match list')
            records = dict(self.records)
            for match in payload:
                if not isinstance(match, dict):
                    continue
                mid = _match_id(match.get('match_id'))
                mmr = _mmr(match.get('average_mmr'))
                if mid and mmr:
                    players = match.get('players')
                    heroes = _hero_ids([player.get('hero_id') for player in players if isinstance(player, dict)]) \
                        if isinstance(players, list) else []
                    if not heroes:
                        heroes = _hero_ids(records.get(mid, {}).get('hero_ids'))
                    records[mid] = dict(average_mmr=mmr, observed_at=now, source=SOURCE)
                    if heroes:
                        records[mid]['hero_ids'] = heroes
                    count += 1
            self.records = records
            self.last_success = now
        except HTTPError as exc:
            error = f'HTTP {exc.code}'
            if exc.code == 429:
                retry = (exc.headers.get('Retry-After') if exc.headers else None) or '300'
                try:
                    delay = float(retry)
                    if not math.isfinite(delay):
                        raise ValueError('Invalid retry interval')
                except (ValueError, TypeError):
                    try:
                        delay = parsedate_to_datetime(retry).timestamp() - now
                    except (ValueError, TypeError, OverflowError):
                        delay = 300
                self.next_refresh_at = now + min(MAX_BACKOFF, max(MIN_INTERVAL, delay))
        except (OSError, URLError, HTTPException) as exc:
            error = _network_error(exc)
        except (ValueError, TypeError):
            error = 'Invalid live feed response'
        self.last_count = count
        self.last_error = error
        self._prune(now)
        try:
            self._save()
        except OSError:
            self.last_error = error or 'Could not save match MMR observations'
        return RefreshResult(True, count, self.status_text(), self.last_error)

    def enrich(self, routes):
        """Apply a captured match average without guessing from players or medals."""
        now = time.time()
        result = []
        for route in routes:
            if route.demo or route.tournament or _mmr(route.average_mmr):
                result.append(route)
                continue
            mid = _match_id(route.match_ids[0]) if route.match_ids else None
            record = self.records.get(mid)
            if record and now - MAX_AGE <= record['observed_at'] <= now + 300:
                route = replace(route, average_mmr=record['average_mmr'], average_mmr_source=SOURCE)
            result.append(route)
        return result
