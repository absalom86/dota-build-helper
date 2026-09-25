import json
import time
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

import pytest
from PIL import Image, ImageDraw

from dota_helper.builds import normalize, rank_routes
from dota_helper.detection import Detector
from dota_helper.gsi import Receiver
from dota_helper.models import Session, Purchase
from dota_helper.providers import OpenDota, Demo, DataError


def match_fixture():
    return {"match_id": 123, "patch": 60, "start_time": int(time.time()),
            "players": [{"hero_id": 1, "player_slot": 0, "position_est": 1, "lane_role": 1,
                         "purchase_log": [{"key": "tango", "time": -40}, {"key": "branches", "time": -40},
                                          {"key": "branches", "time": -40}, {"key": "bfury", "time": 900}],
                         "ability_upgrades_arr": [5003, 5004]}]}


def route_fixture():
    match = match_fixture()
    return normalize(match, match["players"][0], "fixture")


def gsi(hero=1, match=42, clock=100):
    return {"hero": {"id": hero, "level": 4}, "player": {"steamid": "test"},
            "map": {"matchid": match, "clock_time": clock, "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"},
            "items": {"slot0": {"name": "item_bfury"}},
            "abilities": {"ability0": {"name": "antimage_mana_break", "level": 2, "ability_passive": True}}}


def test_purchase_quantities_and_negative_time_are_preserved():
    route = route_fixture()
    assert [(p.key, p.occurrence) for p in route.purchases[:3]] == [("tango", 1), ("branches", 1), ("branches", 2)]
    assert route.purchases[0].time < 0


def test_no_timeline_no_fabricated_route():
    m = match_fixture()
    m["players"][0]["purchase_log"] = None
    m["players"][0]["item_0"] = 145
    assert normalize(m, m["players"][0], "test") is None


def test_role_and_lane_unknown_do_not_match():
    r = route_fixture()
    assert not rank_routes([r], 5, 0, 60, time.time())
    assert not rank_routes([r], 1, 3, 60, time.time())
    r.role = 0
    assert not rank_routes([r], 1, 0, 60, time.time())


def test_benchmark_only_when_enough_samples():
    routes = []
    for i, second in enumerate([800, 900, 1000]):
        r = route_fixture()
        r.id = f"test:{i}"
        r.match_ids = [i + 1]
        r.purchases[-1].time = second
        routes.append(r)
    result = rank_routes(routes, 1, 0, 60, time.time())
    assert len(result) == 1
    assert result[0].purchases[-1].time == 900
    assert (result[0].purchases[-1].low, result[0].purchases[-1].high) == (850, 950)
    assert len(result[0].match_ids) == 3


def test_single_sample_has_no_range_and_old_patch_is_labeled():
    result = rank_routes([route_fixture()], 1, 0, 61, time.time())[0]
    assert result.purchases[-1].low is None
    assert any("OLDER PATCH" in w for w in result.warnings)


def test_route_switch_keeps_completion_and_skill_progress():
    s = Session()
    s.completed.add(("bfury", 1))
    s.learned["antimage_mana_break"] = 1
    s.choose("route-2")
    assert s.is_complete(Purchase("bfury", 900))
    assert s.next_skill(route_fixture())[0] == "antimage_blink"


def test_explicit_choice_not_replaced_by_refresh():
    s = Session(selected="chosen", explicit_choice=True)
    s.accept_routes([route_fixture()])
    assert s.selected == "chosen"


def test_session_resets_on_new_match_and_bot_pregame():
    s = Session()
    s.ingest(gsi())
    s.completed.add(("bfury", 1))
    s.ingest(gsi(match=43))
    assert not s.completed
    s.completed.add(("bfury", 1))
    s.ingest(gsi(match=0, clock=-50))
    assert not s.completed


def test_hover_and_spectator_are_not_confirmed():
    s = Session()
    payload = gsi(hero=2)
    payload["map"]["game_state"] = "DOTA_GAMERULES_STATE_HERO_SELECTION"
    assert not s.ingest(payload)
    assert s.hero_id == 1
    payload["hero"] = {"team2": {"player0": {"id": 2}}}
    assert not s.ingest(payload)


def test_passive_skill_and_pause_clock():
    s = Session()
    payload = gsi(clock=100)
    payload["map"]["paused"] = True
    assert s.ingest(payload)
    assert s.paused and s.clock == 100
    assert s.learned["antimage_mana_break"] == 2


def test_incompatible_talent_is_reported_but_innate_ignored():
    s = Session()
    s.learned["antimage_innate"] = 1
    assert s.next_skill(route_fixture())[0]
    s.learned["special_bonus_other_talent"] = 1
    assert s.next_skill(route_fixture())[0] is None


def test_demo_only_supports_labeled_fixed_hero():
    assert not Demo().routes(2, 1, 0)[0]
    assert all(r.demo and not r.match_ids for r in Demo().routes(1, 1, 0)[0])


def test_detector_requires_three_frames_and_rejects_blank(tmp_path):
    frame = Image.new("RGB", (100, 60), "blue")
    ImageDraw.Draw(frame).rectangle((0, 0, 45, 30), fill="red")
    frame.save(tmp_path / "1.png")
    detector = Detector(tmp_path)
    assert detector.inspect(frame)[0] is None
    assert detector.inspect(frame)[0] is None
    assert detector.inspect(frame)[0] == 1
    assert detector.inspect(Image.new("RGB", (100, 60), "black"))[0] is None


def test_gsi_auth_and_payload_roundtrip():
    received = []
    server = Receiver(received.append, "secret", port=0)
    server.start()
    url = f"http://127.0.0.1:{server.server.server_port}/"
    try:
        payload = gsi()
        payload["auth"] = {"token": "wrong"}
        with pytest.raises(HTTPError) as exc:
            urlopen(Request(url, json.dumps(payload).encode()), timeout=2)
        assert exc.value.code == 403
        payload["auth"]["token"] = "secret"
        with urlopen(Request(url, json.dumps(payload).encode()), timeout=2) as response:
            assert response.status == 200
        assert len(received) == 1 and "auth" not in received[0]
    finally:
        server.stop()


def test_cache_and_offline_stale_label(tmp_path, monkeypatch):
    provider = OpenDota(tmp_path)
    import hashlib
    key = hashlib.sha256(b"heroes/1/matches{}").hexdigest()
    (tmp_path / f"{key}.json").write_text(json.dumps({"at": 0, "data": [1]}))
    monkeypatch.setattr("dota_helper.providers.urlopen", lambda *a, **kw: (_ for _ in ()).throw(URLError("offline")))
    monkeypatch.setattr(provider.cancel, "wait", lambda delay: False)
    assert provider.get("heroes/1/matches") == [1]
    assert provider.stale and "Cached" in provider.stale[0]


def test_cancel_does_not_make_request(tmp_path):
    provider = OpenDota(tmp_path)
    provider.cancel.set()
    with pytest.raises(DataError, match="cancelled"):
        provider.get("heroes")


def test_fast_search_skips_public_scan_and_enforces_individual_rank(tmp_path, monkeypatch):
    provider = OpenDota(tmp_path)
    requested = []
    m = match_fixture()
    m["players"][0]["rank_tier"] = 80
    def fake_get(path, params=None, ttl=3600):
        requested.append(path)
        if path == "proPlayers":
            return []
        if path == "heroes/1/matches":
            return [{"match_id": 123, "start_time": int(time.time())}]
        if path == "matches/123":
            return m
        raise AssertionError(path)
    monkeypatch.setattr(provider, "get", fake_get)
    routes, _ = provider.routes(1, 1, 0)
    assert len(routes) == 1
    assert "Immortal-ranked player" in routes[0].evidence
    assert "publicMatches" not in requested


def test_optional_discovery_failure_retains_ranked_hero_route(tmp_path, monkeypatch):
    provider = OpenDota(tmp_path)
    m = match_fixture()
    m["players"][0]["rank_tier"] = 80
    def fake_get(path, params=None, ttl=3600):
        if path in ("proPlayers", "publicMatches"):
            raise DataError("offline")
        if path == "heroes/1/matches":
            return [{"match_id": 123, "start_time": int(time.time())}]
        return m
    monkeypatch.setattr(provider, "get", fake_get)
    routes, status = provider.routes(1, 1, 0)
    assert len(routes) == 1
    assert "Partial search" in status
