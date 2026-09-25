import threading

import pytest

from dota_helper.match_import import match_id, load_match
from dota_helper.providers import DataError
from test_fast_lookup import match, setup_client
from dota_helper.fast_lookup import fast_routes


def test_match_id_accepts_only_numeric_or_opendota_url():
    assert match_id("8972893223") == 8972893223
    assert match_id("https://dota2protracker.com/matches/8987805727") == 8987805727
    assert match_id("https://www.opendota.com/matches/8972893223?x=1") == 8972893223
    for text in ("https://evil.com/matches/123", "https://opendota.com.evil.com/matches/123", "../123", "0", "-123"):
        with pytest.raises(DataError):
            match_id(text)


def test_pro_registry_never_qualifies_divine_player(tmp_path, monkeypatch):
    def detail(mid):
        data = match(mid)
        data["players"][0].update(account_id=42, rank_tier=72)
        return data
    client = setup_client(tmp_path, monkeypatch, detail)
    original = client.cached
    monkeypatch.setattr(client, "cached", lambda path, **kw: [{"account_id": 42}] if path == "proPlayers" else original(path, **kw))
    assert not fast_routes(client, 1, 1, 0, lambda _: None, threading.Event())[0]


def test_divine_teammate_excluded(tmp_path, monkeypatch):
    def detail(mid):
        data = match(mid)
        data["players"].append({"hero_id": 2, "rank_tier": 75})
        return data
    client = setup_client(tmp_path, monkeypatch, detail)
    assert not fast_routes(client, 1, 1, 0, lambda _: None, threading.Event())[0]


def test_same_build_games_remain_individual_exact_timings(tmp_path, monkeypatch):
    def detail(mid):
        data = match(mid)
        data["players"][0]["purchase_log"][1]["time"] = 800 + mid * 100
        return data
    client = setup_client(tmp_path, monkeypatch, detail)
    routes, _ = fast_routes(client, 1, 1, 0, lambda _: None, threading.Event())
    assert len(routes) == 2
    assert {r.purchases[1].time for r in routes} == {900, 1000}
    assert all(len(r.match_ids) == 1 and r.purchases[1].samples == 1 for r in routes)
    assert all("UNVERIFIED" in r.evidence for r in routes)


def test_import_direct_without_discovery_and_checks_context(tmp_path, monkeypatch):
    data = match(123)
    data["radiant_win"] = True
    client = setup_client(tmp_path, monkeypatch, lambda mid: data)
    calls = []
    monkeypatch.setattr(client, "get", lambda path, **kw: (calls.append(path), data)[1])
    route = load_match(client, 123, 1, 1, 0, threading.Event())
    assert calls == ["matches/123"]
    assert route.match_ids == [123] and route.result == "Won"
    assert "User-selected" in route.evidence and "UNVERIFIED" in route.evidence
    for hero, role, lane in ((2, 1, 0), (1, 2, 0), (1, 1, 2)):
        with pytest.raises(DataError):
            load_match(client, 123, hero, role, lane, threading.Event())
    data["patch"] -= 1
    with pytest.raises(DataError, match="patch"):
        load_match(client, 123, 1, 1, 0, threading.Event())
