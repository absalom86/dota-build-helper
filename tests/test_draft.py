import threading

import pytest

from dota_helper.draft import rank_picks, DraftProvider
from dota_helper.providers import DataError


def rows(hero, games, enemy_wins):
    return {"hero_id": hero, "games_played": games, "wins": enemy_wins}


def test_enemy_perspective_is_inverted():
    picks = rank_picks([2], {2: [rows(1, 100, 20), rows(3, 100, 80)]})
    assert picks[0].hero_id == 1
    assert picks[0].matchups[0].wins == 80
    assert picks[0].score == 65


def test_enemies_allies_and_bans_are_excluded():
    picks = rank_picks([2], {2: [rows(1, 100, 20), rows(2, 100, 10), rows(3, 100, 20)]}, excluded=[1])
    assert [p.hero_id for p in picks] == [3]


def test_missing_or_small_samples_cannot_outrank_complete_evidence():
    picks = rank_picks([2, 14], {2: [rows(1, 100, 0), rows(3, 100, 50), rows(5, 19, 0)],
                               14: [rows(3, 100, 50), rows(5, 100, 0)]})
    assert [p.hero_id for p in picks] == [3]


def test_small_sample_is_shrunk_and_enemies_are_equal_weighted():
    pick = rank_picks([2, 14], {2: [rows(1, 20, 0)], 14: [rows(1, 1000, 600)]})[0]
    expected = ((20 + 50) / 120 + (400 + 50) / 1100) * 50
    assert pick.score == pytest.approx(expected)


def test_duplicate_enemy_does_not_inflate_score():
    tables = {2: [rows(1, 100, 40)]}
    assert rank_picks([2, 2], tables)[0] == rank_picks([2], tables)[0]


def test_support_pool_uses_tag_not_invented_position():
    picks = rank_picks([2], {2: [rows(1, 100, 10), rows(5, 100, 30)]}, pool="Support")
    assert [p.hero_id for p in picks] == [5]


def test_bad_records_and_unknown_heroes_are_ignored():
    tables = {2: [rows(1, 100, 101), rows(3, 100, -1), rows(5, "100", 30), rows(99999, 100, 10)]}
    assert rank_picks([2], tables) == []


@pytest.mark.parametrize("enemies", [[], [99999], [1, 2, 3, 4, 5, 6]])
def test_invalid_enemy_selection(enemies):
    with pytest.raises(DataError):
        rank_picks(enemies, {})


class Client:
    def __init__(self, fail=False, stale=False):
        self.cancel = threading.Event()
        self.stale = []
        self.fail = fail
        self.use_stale = stale
        self.calls = []

    def get(self, path, ttl):
        self.calls.append(path)
        if self.fail and path == "heroes/14/matchups":
            raise DataError("unavailable")
        if self.use_stale:
            self.stale.append("Cached response: 24 hours old")
        return [rows(1, 100, 30)]


def test_provider_only_fetches_enemies_and_surfaces_stale_cache():
    client = Client(stale=True)
    picks, status = DraftProvider(client).suggestions([2, 14])
    assert client.calls == ["heroes/2/matchups", "heroes/14/matchups"]
    assert len(picks) == 1
    assert "STALE CACHE" in status


def test_failed_enemy_request_does_not_rank_partial_draft():
    with pytest.raises(DataError):
        DraftProvider(Client(fail=True)).suggestions([2, 14])


def test_cancelled_search_cannot_deliver_recommendations():
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(DataError, match="cancelled"):
        DraftProvider(Client()).suggestions([2], cancel=cancel)
