"""Independent discovery of recent ranked pubs, using OpenDota's public SQL API.

The sample is not D2PT's tracked population and contains no numeric MMR.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
import json
import time
import uuid

from .builds import normalize
from .catalog import HEROES, PATCHES
from .fast_lookup import DeadlineJobs
from .models import Purchase, Route
from .ranking import ranked

DAYS = 7
LIMIT = 10


def discovery_query(hero_id):
    if str(hero_id) not in HEROES:
        raise ValueError("Unknown hero")
    # Constants/validated integer only; no user-supplied SQL. Containment uses
    # OpenDota's documented GIN hero-team indexes. One query, no global paging.
    hero_id = int(hero_id)
    return ("SELECT match_id,start_time,avg_rank_tier,num_rank_tier,lobby_type,"
            "radiant_team,dire_team FROM public_matches "
            "WHERE start_time >= EXTRACT(EPOCH FROM NOW() - INTERVAL '7 days') "
            "AND avg_rank_tier = 80 AND num_rank_tier = 10 AND lobby_type = 7 "
            f"AND (radiant_team @> ARRAY[{hero_id}] OR dire_team @> ARRAY[{hero_id}]) "
            "ORDER BY start_time DESC, match_id DESC LIMIT 10")


def candidates(data, hero_id, now):
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list) or data.get("err"):
        raise ValueError("Invalid discovery response")
    minimum = max(now - DAYS * 86400,
                  datetime.fromisoformat(PATCHES[-1]["date"].replace("Z", "+00:00")).timestamp())
    found = {}
    for row in data["rows"]:
        if not isinstance(row, dict):
            continue
        row = dict(row)
        try:
            for key in ("match_id", "start_time", "num_rank_tier", "lobby_type"):
                row[key] = int(row[key])
            row["avg_rank_tier"] = float(row["avg_rank_tier"])
        except (TypeError, ValueError, KeyError):
            continue
        teams = (row.get("radiant_team") or []) + (row.get("dire_team") or [])
        if (row.get("match_id") and minimum <= row.get("start_time", 0) <= now
                and row.get("avg_rank_tier") == 80 and row.get("num_rank_tier") == 10
                and row.get("lobby_type") == 7 and hero_id in teams):
            found[row["match_id"]] = row
    return sorted(found.values(), key=lambda r: (r["start_time"], r["match_id"]), reverse=True)[:LIMIT]


def recent_pubs(client, hero_id, role, progress, cancel, on_update=None, seconds=8):
    from .providers import DataError
    started = time.monotonic()
    now = time.time()
    client.cancel = cancel
    jobs = DeadlineJobs(cancel, seconds)
    params = {"sql": discovery_query(hero_id)}
    snapshot = client.cache_dir / f"pubs-v1-{PATCHES[-1]['id']}-{hero_id}-{role}.json"
    ready, pending, outcomes = {}, [], {}
    failures = 0
    signature = None
    attempted = set()
    discovery = None
    try:
        saved = json.loads(snapshot.read_text(encoding="utf-8"))
        for row in saved["routes"]:
            row["purchases"] = [Purchase(**p) for p in row["purchases"]]
            route = Route(**row)
            if (route.hero_id == hero_id and route.role == role and route.patch == PATCHES[-1]["id"]
                    and now - DAYS * 86400 <= route.start_time <= now):
                ready[route.id] = route
        if ready and saved.get("complete") and now - saved["at"] < 300 and not getattr(client,'force_refresh',False):
            return ranked(ready.values(), LIMIT), saved["status"] + " Cached; ready immediately."
    except (OSError, ValueError, TypeError, KeyError):
        ready = {}

    def publish():
        nonlocal signature
        routes = ranked(ready.values(), LIMIT)
        current = tuple(r.id for r in routes)
        if routes and on_update and current != signature:
            signature = current
            on_update((deepcopy(routes), f"{len(routes)} recent Immortal pub games · checking remaining results. Numeric MMR unavailable."))
        return routes

    publish()
    cached = client.cached("explorer", params=params, ttl=300, allow_stale=True)
    if cached:
        try:
            pending = candidates(cached, hero_id, now)
        except ValueError:
            pass
    if client.cached("explorer", params=params, ttl=300) is None:
        discovery = lambda: client.get("explorer", params=params, ttl=300)
    progress("Recent ranked pubs · last 7 days · 10 recorded Immortal ranks · newest first · 8-second limit")

    def collect(match, row):
        mid = row["match_id"]
        if (not isinstance(match, dict) or match.get("match_id") != mid
                or match.get("patch") != PATCHES[-1]["id"]
                or not now - DAYS * 86400 <= match.get("start_time", 0) <= now):
            outcomes[mid] = "wrong patch/date or match"
            return
        if match.get("leagueid") or match.get("lobby_type") != 7:
            outcomes[mid] = "not a ranked pub"
            return
        players = [p for p in match.get("players", []) if p.get("hero_id") == hero_id]
        if len(players) != 1:
            outcomes[mid] = "hero missing/ambiguous"
            return
        player = players[0]
        if any(0 < (p.get("rank_tier") or 0) < 80 for p in match.get("players", [])):
            outcomes[mid] = "conflicting below-Immortal profile"
            return
        if player.get("position_est") != role:
            outcomes[mid] = "different/unknown position"
            return
        route = normalize(match, player, "OpenDota sampled pub · 10/10 recorded ranks Immortal · numeric MMR unavailable")
        if not route:
            outcomes[mid] = "purchase history unavailable"
            return
        route.warnings.extend(["Independent OpenDota sample, not D2PT's tracked games or numeric MMR ranking.",
                               "All ten recorded rank tiers in the discovery sample are Immortal. Within Immortal, MMR cannot be compared."])
        ready[route.id] = route
        outcomes[mid] = "accepted"

    while not cancel.is_set() and time.monotonic() < jobs.deadline:
        if discovery and jobs.submit("discovery", discovery):
            discovery = None
        while pending:
            row = pending[0]
            mid = row["match_id"]
            if mid in attempted:
                pending.pop(0)
                continue
            if len(attempted) >= LIMIT:
                pending.clear()
                break
            cached_match = client.cached(f"matches/{mid}", ttl=86400, allow_stale=True)
            if cached_match:
                attempted.add(mid)
                pending.pop(0)
                collect(cached_match, row)
            elif jobs.submit(mid, lambda row=row: (row, client.get(f"matches/{row['match_id']}", ttl=86400))):
                attempted.add(mid)
                pending.pop(0)
            else:
                break
        publish()
        if not jobs.active:
            break
        event = jobs.next()
        if event is None:
            break
        key, data, error = event
        if error:
            failures += 1
        elif key == "discovery":
            try:
                pending = candidates(data, hero_id, now)
            except ValueError:
                failures += 1
        else:
            row, match = data
            collect(match, row)
    if cancel.is_set():
        raise DataError("Search cancelled")
    routes = publish()
    complete = not (failures or jobs.active or discovery or pending)
    rejected = Counter(value for value in outcomes.values() if value != "accepted")
    exclusions = "; ".join(f"{count} {reason}" for reason, count in sorted(rejected.items()))
    status = (f"{len(routes)} recent Immortal pub games · {time.monotonic() - started:.1f}s · "
              f"{len(attempted)} candidates checked · {failures} API failures · "
              f"{jobs.active + len(pending) + bool(discovery)} unfinished. "
              + (f"Excluded: {exclusions}. " if exclusions else "")
              + "Independent OpenDota sample; D2PT coverage and numeric MMR unavailable.")
    if not routes:
        status += " No older league-game substitution. You can still import a chosen match ID."
    for route in routes:
        route.warnings.extend(w for w in client.stale if w not in route.warnings)
    temp = snapshot.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps({"at": now, "complete": complete, "status": status,
                                "routes": [asdict(r) for r in routes]}), encoding="utf-8")
    temp.replace(snapshot)
    return routes, status
