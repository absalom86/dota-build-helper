"""Historical pairwise matchup ranking, not a full-draft win prediction."""
from dataclasses import dataclass
import threading
import time

from .catalog import HEROES
from .providers import OpenDota, DataError
from .fast_lookup import DeadlineJobs

MIN_GAMES = 20
PRIOR_GAMES = 100


@dataclass(frozen=True)
class Matchup:
    enemy_id: int
    games: int
    wins: int

    @property
    def rate(self):
        return self.wins / self.games

    @property
    def adjusted(self):
        return (self.wins + PRIOR_GAMES / 2) / (self.games + PRIOR_GAMES)


@dataclass(frozen=True)
class Suggestion:
    hero_id: int
    score: float
    matchups: tuple[Matchup, ...]


def rank_picks(enemy_ids, tables, excluded=(), pool="Any hero", limit=10):
    enemies = tuple(dict.fromkeys(enemy_ids))
    if not 1 <= len(enemies) <= 5 or any(str(h) not in HEROES for h in enemies):
        raise DataError("Select between one and five different enemy heroes.")
    blocked = set(excluded) | set(enemies)
    by_enemy = {}
    for enemy in enemies:
        rows = tables.get(enemy, [])
        valid = {}
        for row in rows:
            candidate, games, enemy_wins = row.get("hero_id"), row.get("games_played"), row.get("wins")
            if not all(type(v) is int for v in (candidate, games, enemy_wins)):
                continue
            if games < MIN_GAMES or not 0 <= enemy_wins <= games:
                continue
            # Endpoint wins belong to the queried ENEMY, not the candidate.
            valid[candidate] = Matchup(enemy, games, games - enemy_wins)
        by_enemy[enemy] = valid
    results = []
    for key, hero in HEROES.items():
        hero_id = int(key)
        if hero_id in blocked:
            continue
        if pool != "Any hero" and pool not in hero.get("roles", []):
            continue
        pairs = tuple(by_enemy[e][hero_id] for e in enemies if hero_id in by_enemy[e])
        # Missing evidence is not a neutral/favourable matchup. Require every enemy.
        if len(pairs) != len(enemies):
            continue
        score = 100 * sum(p.adjusted for p in pairs) / len(pairs)
        results.append(Suggestion(hero_id, score, pairs))
    return sorted(results, key=lambda s: (-s.score, -min(p.games for p in s.matchups), s.hero_id))[:limit]


class DraftProvider:
    def __init__(self, client=None):
        self.client = client or OpenDota()

    def suggestions(self, enemies, excluded=(), pool="Any hero", progress=lambda _: None, cancel=None):
        self.client.cancel = cancel or threading.Event()
        self.client.stale = []
        tables = {}
        unique = tuple(dict.fromkeys(enemies))
        if not 1 <= len(unique) <= 5 or any(str(e) not in HEROES for e in unique):
            raise DataError("Select between one and five different enemy heroes.")
        jobs = DeadlineJobs(self.client.cancel)
        pending = list(unique)
        progress("Quick draft lookup · cached data first · 8-second budget")
        while pending or jobs.active:
            while pending:
                enemy = pending[0]
                cached = getattr(self.client, "cached", lambda *a, **kw: None)(f"heroes/{enemy}/matchups", ttl=21600, allow_stale=True)
                if cached is not None:
                    tables[enemy] = cached
                    pending.pop(0)
                elif jobs.submit(enemy, lambda enemy=enemy: self.client.get(f"heroes/{enemy}/matchups", ttl=21600)):
                    pending.pop(0)
                else:
                    break
            if not jobs.active:
                break
            event = jobs.next()
            if event is None:
                break
            enemy, data, error = event
            if error is None:
                tables[enemy] = data
        if self.client.cancel.is_set():
            raise DataError("Draft search cancelled")
        if len(tables) != len(unique):
            raise DataError("Matchup API unavailable within the 8-second budget. No partial-draft ranking; cached responses will speed up a later retry.")
        picks = rank_picks(unique, tables, excluded, pool)
        status = f"{len(picks)} suggestions · at least {MIN_GAMES} games against every selected enemy."
        if not picks:
            status = "No heroes have enough data against every selected enemy in this pool. Try Any hero or fewer enemy picks."
        if self.client.stale:
            status += " STALE CACHE: " + " · ".join(self.client.stale)
        return picks, status
