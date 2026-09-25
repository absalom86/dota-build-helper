"""Bounded lookup orchestration: cached first, streamed results, no waiting for stragglers."""
from copy import deepcopy
from collections import Counter
from dataclasses import asdict
from datetime import datetime
import json
from queue import Queue, Empty
import threading
import time
import uuid

from .builds import normalize, rank_routes
from .catalog import PATCHES
from .models import Route, Purchase
from .ranking import ranked

LOOKUP_SECONDS = 8.0
MAX_MATCHES = 10
NETWORK_SLOTS = threading.BoundedSemaphore(3)


class DeadlineJobs:
    """Daemon I/O can finish caching later, but never extends the UI's deadline."""
    def __init__(self, cancel, seconds=LOOKUP_SECONDS):
        self.cancel = cancel
        self.deadline = time.monotonic() + seconds
        self.queue = Queue()
        self.active = 0

    def submit(self, key, fn):
        if self.cancel.is_set() or time.monotonic() >= self.deadline or not NETWORK_SLOTS.acquire(False):
            return False
        self.active += 1
        def work():
            try:
                result = (key, fn(), None)
            except Exception as exc:
                result = (key, None, exc)
            finally:
                NETWORK_SLOTS.release()
            self.queue.put(result)
        threading.Thread(target=work, daemon=True).start()
        return True

    def next(self):
        while not self.cancel.is_set() and time.monotonic() < self.deadline:
            try:
                value = self.queue.get(timeout=min(.05, max(.001, self.deadline - time.monotonic())))
                self.active -= 1
                return value
            except Empty:
                pass
        return None


def current_candidates(rows, pros, cached_ranks=None):
    patch_start = datetime.fromisoformat(PATCHES[-1]["date"].replace("Z", "+00:00")).timestamp()
    cached_ranks = cached_ranks or {}
    unique = {r["match_id"]: r for r in rows if isinstance(r, dict) and r.get("match_id")
              and r.get("start_time", 0) >= patch_start
              and (r.get("patch") is None or r["patch"] == PATCHES[-1]["id"])}
    return sorted(unique.values(), key=lambda r: (r.get("account_id") in pros,
                  cached_ranks.get(r["match_id"], 0), r.get("start_time", 0)), reverse=True)[:MAX_MATCHES]


def fast_routes(client, hero_id, role, lane, progress, cancel, on_update=None, seconds=LOOKUP_SECONDS):
    from .providers import DataError
    start = time.monotonic()
    jobs = DeadlineJobs(cancel, seconds)
    snapshot_path = client.cache_dir / f"matches-v3-{PATCHES[-1]['id']}-{hero_id}-{role}-{lane}.json"
    fallback = []
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        for row in snapshot["routes"]:
            row = dict(row)
            row["purchases"] = [Purchase(**p) for p in row["purchases"]]
            route = Route(**row)
            if route.patch == PATCHES[-1]["id"] and route.hero_id == hero_id and route.role == role and (not lane or route.lane == lane):
                fallback.append(route)
        fallback = ranked(fallback)
        age = max(0, int(time.time() - snapshot["at"]))
        if fallback:
            status = f"Cached individual games · Match MMR unverified · {age // 60} minutes old · ready immediately."
            if age < 1800 and snapshot.get("complete") is True and not getattr(client,'force_refresh',False):
                return fallback, status + " " + snapshot.get("diagnostic", "")
            for route in fallback:
                route.warnings.append(f"Cached build snapshot: {age // 60} minutes old; refresh pending.")
            if on_update:
                on_update((deepcopy(fallback), status + " Checking for more games within 8 seconds…"))
    except (OSError, ValueError, TypeError, KeyError):
        fallback = []
    client.cancel = cancel
    client.stale = []
    pros_cache = client.cached("proPlayers", ttl=86400, allow_stale=True)
    rows_cache = client.cached(f"heroes/{hero_id}/matches", ttl=1800, allow_stale=True)
    pros = {p["account_id"] for p in (pros_cache or []) if p.get("account_id")}
    rows = rows_cache or []
    discovery = []
    if client.cached("proPlayers", ttl=86400) is None:
        discovery.append(("pros", lambda: client.get("proPlayers", ttl=86400)))
    if client.cached(f"heroes/{hero_id}/matches", ttl=1800) is None:
        discovery.append(("heroes", lambda: client.get(f"heroes/{hero_id}/matches", ttl=1800)))
    # Ready raw cache is immediately useful even when discovery is currently down.
    pending = []
    attempted = set()
    records = []
    eligible = []
    failures = 0
    outcomes = {}

    def collect(match):
        mid = match.get("match_id") if isinstance(match, dict) else None
        if not isinstance(match, dict) or match.get("patch") != PATCHES[-1]["id"]:
            outcomes[mid] = "wrong/unknown patch"
            return
        # Registry membership never overrides rank. Reject known below-Immortal
        # profiles anywhere in the lobby; absent ranks are explicitly unverified.
        if any(0 < (p.get("rank_tier") or 0) < 80 for p in match.get("players", [])):
            outcomes[mid] = "below-Immortal profile"
            return
        outcomes[mid] = "hero missing"
        for player in match.get("players", []):
            if player.get("hero_id") != hero_id:
                continue
            if (player.get("rank_tier") or 0) >= 80:
                evidence = "Immortal-ranked player profile · Match MMR UNVERIFIED"
            else:
                outcomes[mid] = "target rank unknown/below Immortal"
                continue
            route = normalize(match, player, evidence)
            if route and route.role == role and (not lane or route.lane == lane):
                eligible.append(route)
                outcomes[mid] = "accepted"
            elif not route:
                outcomes[mid] = "purchase history unavailable"
            else:
                outcomes[mid] = "different/unknown position"

    def results():
        unique = {r.id: r for r in eligible}
        return deepcopy(ranked(unique.values(), MAX_MATCHES))

    def enqueue_candidates():
        ranks = {}
        for row in rows:
            cached = client.cached(f"matches/{row.get('match_id')}", ttl=86400, allow_stale=True)
            if cached:
                ranks[row["match_id"]] = max((p.get("rank_tier") or 0 for p in cached.get("players", []) if p.get("hero_id") == hero_id), default=0)
        for row in current_candidates(rows, pros, ranks):
            mid = row["match_id"]
            if mid not in attempted and mid not in pending and len(attempted) + len(pending) < MAX_MATCHES:
                pending.append(mid)

    enqueue_candidates()
    progress("Quick lookup · current patch only · up to 10 candidates · 8-second budget")
    last_signature = None
    while not cancel.is_set() and time.monotonic() < jobs.deadline:
        while discovery:
            key, fn = discovery[0]
            if not jobs.submit(key, fn):
                break
            discovery.pop(0)
        while pending:
            mid = pending[0]
            cached = client.cached(f"matches/{mid}", ttl=86400, allow_stale=True)
            if cached:
                pending.pop(0)
                attempted.add(mid)
                records.append(cached)
                collect(cached)
            elif jobs.submit(mid, lambda mid=mid: client.get(f"matches/{mid}", ttl=86400)):
                pending.pop(0)
                attempted.add(mid)
            else:
                break
        ready = results()
        signature = tuple((r.id, len(r.match_ids)) for r in ready)
        if ready and signature != last_signature:
            last_signature = signature
            if on_update:
                on_update((ready, f"{len(ready)} individual games ready in {time.monotonic() - start:.1f}s · Match MMR unverified · checking remaining candidates…"))
        if not jobs.active and not discovery and not pending:
            break
        if not jobs.active:
            # Other lookups own all network slots; do not spin or enqueue unbounded work.
            break
        event = jobs.next()
        if event is None:
            break
        key, data, error = event
        if error:
            failures += 1
            continue
        if key == "pros":
            pros = {p["account_id"] for p in data if p.get("account_id")}
            eligible.clear()
            for match in records:
                collect(match)
            enqueue_candidates()
        elif key == "heroes":
            rows = data
            enqueue_candidates()
        else:
            records.append(data)
            collect(data)
    if cancel.is_set():
        raise DataError("Search cancelled")
    ready = results()
    elapsed = time.monotonic() - start
    complete = not (failures or pending or jobs.active or discovery)
    excluded = Counter(reason for reason in outcomes.values() if reason != "accepted")
    detail = "; ".join(f"{n} {reason}" for reason, n in sorted(excluded.items()))
    diagnostic = f"{len(attempted)} candidates · {len(records)} details received · {failures} API failures · {len(pending) + jobs.active + len(discovery)} unfinished"
    if detail:
        diagnostic += " · Excluded: " + detail
    if ready:
        for route in ready:
            route.warnings.extend(client.stale)
            route.warnings.append("Up to 10 discovered candidates, prioritizing registered pros and known profile ranks; not a global top-10 MMR ranking.")
        temp = snapshot_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        temp.write_text(json.dumps({"at": time.time(), "complete": complete, "diagnostic": diagnostic, "routes": [asdict(r) for r in ready]}), encoding="utf-8")
        temp.replace(snapshot_path)
        return ready, f"{len(ready)} individual games · Match MMR unverified · {elapsed:.1f}s. {diagnostic}." + (" Partial search; retry to check for more games." if not complete else "")
    if fallback:
        return fallback, f"{len(fallback)} cached games retained after {elapsed:.1f}s. {diagnostic}. Match MMR unverified."
    return [], f"No matching current-patch game available within {elapsed:.1f}s. {diagnostic}. OpenDota does not verify match MMR. Paste a chosen match ID to load it directly."
