"""Bounded read-only real-provider check. Requests can use the local response cache."""
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dota_helper.providers import OpenDota
from dota_helper.catalog import item_name

provider = OpenDota()
routes, status = provider.routes(1, 1, 0, lambda text: print(text, flush=True))
print(status)
for route in routes:
    print(route.id, route.evidence, route.title)
    print("Starting purchases:", [item_name(p.key) for p in route.purchases if p.time < 0])
    print("Skill entries:", len(route.skills), "Matches:", route.match_ids)
