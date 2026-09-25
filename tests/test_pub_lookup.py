from copy import deepcopy
import threading
import time

import pytest

from dota_helper.pub_lookup import candidates, discovery_query, recent_pubs
from dota_helper.providers import OpenDota, DataError
from test_fast_lookup import match


def row(mid=1):
    return {"match_id": mid, "start_time": int(time.time()) - mid, "avg_rank_tier": 80,
            "num_rank_tier": 10, "lobby_type": 7, "radiant_team": [1, 2, 3, 4, 5], "dire_team": [6, 7, 8, 9, 10]}


def test_recent_ranked_all_ten_immortal_and_hero_required():
    now = time.time()
    good = row()
    rows = [good]
    for key, value in (("avg_rank_tier", 79), ("num_rank_tier", 9), ("lobby_type", 0), ("start_time", now - 8 * 86400), ("radiant_team", [2])):
        rows.append(dict(good, **{key: value, "match_id": len(rows) + 1}))
    assert [r["match_id"] for r in candidates({"rows": rows}, 1, now)] == [1]
    pg = {key: str(value) if key in ("match_id", "start_time") else value for key, value in good.items()}
    assert candidates({"rows": [pg]}, 1, now)[0]["match_id"] == 1
    with pytest.raises(ValueError):
        discovery_query("1; DROP TABLE matches")


def test_recent_pubs_no_league_scan_and_exact_games(tmp_path, monkeypatch):
    client = OpenDota(tmp_path)
    requests = []
    def get(path, **kwargs):
        requests.append(path)
        if path == "explorer":
            return {"rows": [row(1), row(2)]}
        data = match(int(path.split('/')[-1]))
        data.update(lobby_type=7, leagueid=0)
        data["players"][0]["rank_tier"] = None
        return data
    monkeypatch.setattr(client, "get", get)
    routes, status = recent_pubs(client, 1, 1, lambda _: None, threading.Event())
    assert len(routes) == 2 and all(len(r.match_ids) == 1 for r in routes)
    assert requests[0] == "explorer" and len(requests) == 3
    assert "10/10" in routes[0].evidence
    assert "numeric MMR unavailable" in routes[0].evidence
    assert "D2PT" in status
    monkeypatch.setattr(client, "get", lambda *a, **kw: pytest.fail("fresh snapshot must avoid network"))
    cached, status = recent_pubs(client, 1, 1, lambda _: None, threading.Event())
    assert len(cached) == 2 and "ready immediately" in status


def test_detail_still_requires_ranked_pub_patch_role_and_purchases(tmp_path, monkeypatch):
    client = OpenDota(tmp_path)
    def get(path, **kwargs):
        if path == "explorer":
            return {"rows": [row(i) for i in range(1, 6)]}
        mid = int(path.split('/')[-1])
        data = match(mid)
        data.update(lobby_type=7, leagueid=0)
        if mid == 1:
            data["leagueid"] = 123
        elif mid == 2:
            data["patch"] -= 1
        elif mid == 3:
            data["players"][0]["position_est"] = 2
        elif mid == 4:
            data["players"][0]["purchase_log"] = []
        else:
            data["players"].append({"hero_id": 2, "rank_tier": 75})
        return data
    monkeypatch.setattr(client, "get", get)
    routes, status = recent_pubs(client, 1, 1, lambda _: None, threading.Event())
    assert not routes and "not a ranked pub" in status and "purchase history unavailable" in status


def test_discovery_failure_never_substitutes_legacy_games(tmp_path, monkeypatch):
    client = OpenDota(tmp_path)
    monkeypatch.setattr(client, "get", lambda *a, **kw: (_ for _ in ()).throw(DataError("offline")))
    routes, status = recent_pubs(client, 1, 1, lambda _: None, threading.Event())
    assert not routes and "1 API failures" in status and "No older league-game substitution" in status


def test_pub_deadline_does_not_wait_for_discovery(tmp_path, monkeypatch):
    client = OpenDota(tmp_path)
    release = threading.Event()
    monkeypatch.setattr(client, "get", lambda *a, **kw: (release.wait(2), {"rows": []})[1])
    started = time.monotonic()
    try:
        routes, status = recent_pubs(client, 1, 1, lambda _: None, threading.Event(), seconds=.1)
        assert time.monotonic() - started < .4
        assert not routes and "1 unfinished" in status
    finally:
        release.set()
        time.sleep(.02)
