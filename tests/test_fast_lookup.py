from copy import deepcopy
import threading
import time

import pytest

from dota_helper.fast_lookup import fast_routes, current_candidates
from dota_helper.providers import OpenDota
from dota_helper.catalog import PATCHES


def match(mid=1, patch=None):
    return {"match_id": mid, "patch": PATCHES[-1]["id"] if patch is None else patch,
            "start_time": int(time.time()), "players": [{"hero_id": 1, "player_slot": 0, "rank_tier": 80,
            "position_est": 1, "lane_role": 1, "purchase_log": [{"key": "tango", "time": -30},
            {"key": "bfury", "time": 900}], "ability_upgrades_arr": [5003]}]}


def setup_client(tmp_path, monkeypatch, detail):
    client = OpenDota(tmp_path)
    def cached(path, **kwargs):
        if path == "proPlayers":
            return []
        if path == "heroes/1/matches":
            return [{"match_id": i, "start_time": int(time.time()) - i} for i in (1, 2)]
        return None
    monkeypatch.setattr(client, "cached", cached)
    monkeypatch.setattr(client, "get", lambda path, **kwargs: detail(int(path.split('/')[-1])))
    return client


def test_deadline_returns_without_waiting_for_slow_io(tmp_path, monkeypatch):
    release = threading.Event()
    client = setup_client(tmp_path, monkeypatch, lambda mid: (release.wait(2), match(mid))[1])
    start = time.monotonic()
    try:
        routes, status = fast_routes(client, 1, 1, 0, lambda _: None, threading.Event(), seconds=.15)
        assert time.monotonic() - start < .5
        assert not routes
    finally:
        release.set()
        time.sleep(.03)


def test_first_result_streams_before_slow_other_match(tmp_path, monkeypatch):
    release = threading.Event()
    updates = []
    def detail(mid):
        if mid == 2:
            release.wait(2)
        return match(mid)
    client = setup_client(tmp_path, monkeypatch, detail)
    start = time.monotonic()
    try:
        routes, _ = fast_routes(client, 1, 1, 0, lambda _: None, threading.Event(),
                                on_update=lambda value: updates.append((time.monotonic(), value)), seconds=.2)
        assert routes and updates
        assert updates[0][0] - start < .15
        assert updates[0][1][0][0].purchases[0].key == "tango"
    finally:
        release.set()
        time.sleep(.03)


def test_fresh_build_snapshot_does_not_touch_network(tmp_path, monkeypatch):
    client = setup_client(tmp_path, monkeypatch, match)
    routes, _ = fast_routes(client, 1, 1, 0, lambda _: None, threading.Event())
    assert routes
    monkeypatch.setattr(client, "get", lambda *a, **kw: pytest.fail("Network must not run"))
    start = time.monotonic()
    cached, status = fast_routes(client, 1, 1, 0, lambda _: None, threading.Event())
    assert cached and "ready immediately" in status
    assert time.monotonic() - start < .1


def test_partial_snapshot_rechecks_late_cached_games(tmp_path, monkeypatch):
    import json
    from dataclasses import asdict
    from dota_helper.builds import normalize
    client = setup_client(tmp_path, monkeypatch, match)
    first = match(1)
    route = normalize(first, first["players"][0], "MMR unverified")
    snapshot = tmp_path / f"matches-v3-{PATCHES[-1]['id']}-1-1-0.json"
    # Older snapshots did not track completeness, so must also refresh.
    snapshot.write_text(json.dumps({"at": time.time(), "routes": [asdict(route)]}))
    updates = []
    routes, status = fast_routes(client, 1, 1, 0, lambda _: None, threading.Event(), on_update=updates.append)
    assert len(updates[0][0]) == 1
    assert len(routes) == 2
    assert "0 API failures" in status
    assert json.loads(snapshot.read_text())["complete"] is True


def test_failure_distinguished_from_filter_rejection(tmp_path, monkeypatch):
    from dota_helper.providers import DataError
    def detail(mid):
        if mid == 2:
            raise DataError("timeout")
        data = match(mid)
        data["players"][0]["position_est"] = 2
        return data
    client = setup_client(tmp_path, monkeypatch, detail)
    routes, status = fast_routes(client, 1, 1, 0, lambda _: None, threading.Event())
    assert not routes
    assert "1 API failures" in status
    assert "1 different/unknown position" in status


def test_previous_patch_never_substituted(tmp_path, monkeypatch):
    client = setup_client(tmp_path, monkeypatch, lambda mid: match(mid, PATCHES[-1]["id"] - 1))
    assert not fast_routes(client, 1, 1, 0, lambda _: None, threading.Event())[0]


def test_candidates_capped_ten_and_pro_priority():
    rows = [{"match_id": i, "account_id": i, "start_time": int(time.time()) - i} for i in range(1, 30)]
    rows.append({"match_id": 100, "start_time": 0})
    result = current_candidates(rows, {25})
    assert len(result) == 10 and result[0]["match_id"] == 25
    assert all(r["match_id"] != 100 for r in result)


def test_stale_discovery_is_refreshed_without_hiding_cached_build(tmp_path, monkeypatch):
    client = OpenDota(tmp_path)
    calls, updates = [], []
    def cached(path, allow_stale=False, **kw):
        if path == "proPlayers":
            return []
        if path == "heroes/1/matches":
            return [{"match_id": 1, "start_time": int(time.time())}] if allow_stale else None
        if path == "matches/1":
            return match(1)
    def get(path, **kw):
        calls.append(path)
        return [{"match_id": 1, "start_time": int(time.time())}]
    monkeypatch.setattr(client, "cached", cached)
    monkeypatch.setattr(client, "get", get)
    ready, _ = fast_routes(client, 1, 1, 0, lambda _: None, threading.Event(), on_update=updates.append)
    assert ready and updates and "heroes/1/matches" in calls
