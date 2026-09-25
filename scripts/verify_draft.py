"""Read-only live matchup ranking check; no match parsing requests."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
from dota_helper.draft import DraftProvider
from dota_helper.catalog import HEROES

picks, status = DraftProvider().suggestions([2, 14], pool="Support", progress=lambda s: print(s, flush=True))
assert picks, status
print(status)
for pick in picks[:5]:
    print(HEROES[str(pick.hero_id)]["localized_name"], round(pick.score, 2),
          [(p.enemy_id, p.wins, p.games) for p in pick.matchups])
