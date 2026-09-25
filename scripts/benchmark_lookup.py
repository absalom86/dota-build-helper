"""Measure first usable build and total wait; --cold uses an empty isolated cache."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dota_helper.providers import OpenDota, LOCAL

parser = argparse.ArgumentParser()
parser.add_argument("--cold", action="store_true")
parser.add_argument("--raw-cache", action="store_true")
args = parser.parse_args()
cache = LOCAL / "cache"
if args.cold or args.raw_cache:
    cache = LOCAL / "benchmarks" / uuid.uuid4().hex
    cache.mkdir(parents=True)
    if args.raw_cache:
        for path in (LOCAL / "cache").glob("*.json"):
            if not path.name.startswith("builds-"):
                shutil.copyfile(path, cache / path.name)
start = time.monotonic()
first = []
def update(result):
    if result[0] and not first:
        first.append(time.monotonic() - start)
routes, status = OpenDota(cache).routes(1, 1, 0, on_update=update)
elapsed = time.monotonic() - start
print(json.dumps({"mode": "cold" if args.cold else "raw-cache" if args.raw_cache else "warm",
                  "first_build_seconds": round(first[0] if first else elapsed, 3) if routes or first else None,
                  "total_seconds": round(elapsed, 3), "routes": len(routes), "status": status}, indent=2))
