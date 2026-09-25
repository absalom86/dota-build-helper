"""Load a user-selected game independently through OpenDota, without discovery."""
import re
from urllib.parse import urlparse

from .builds import normalize
from .catalog import PATCHES
from .fast_lookup import DeadlineJobs
from .providers import DataError


def match_id(text):
    value = text.strip()
    if not value.isdecimal():
        url = urlparse(value)
        if url.scheme != "https" or url.netloc not in ("opendota.com", "www.opendota.com", "dota2protracker.com", "www.dota2protracker.com"):
            raise DataError("Paste a numeric match ID or an HTTPS D2PT/OpenDota match URL.")
        found = re.fullmatch(r"/matches/(\d+)/?", url.path)
        value = found[1] if found else ""
    if not re.fullmatch(r"[1-9][0-9]{0,11}", value):
        raise DataError("Invalid match ID.")
    return int(value)


def load_match(client, mid, hero_id, role, lane, cancel):
    client.cancel = cancel
    jobs = DeadlineJobs(cancel)
    if not jobs.submit(mid, lambda: client.get(f"matches/{mid}", ttl=86400)):
        raise DataError("Another lookup is finishing. Try again shortly.")
    event = jobs.next()
    if cancel.is_set():
        raise DataError("Search cancelled")
    if event is None:
        raise DataError("Match lookup exceeded 8 seconds. Try again shortly.")
    _, data, error = event
    if error:
        raise DataError("OpenDota could not load this game. Try again shortly.")
    if not isinstance(data, dict) or data.get("match_id") != mid:
        raise DataError("OpenDota returned an unexpected match.")
    if data.get("patch") != PATCHES[-1]["id"]:
        raise DataError("This game is not on the latest known patch; it was not loaded.")
    players = [p for p in data.get("players", []) if p.get("hero_id") == hero_id]
    if len(players) != 1:
        raise DataError("The selected hero is missing or ambiguous in this game.")
    route = normalize(data, players[0], "User-selected game · Match MMR UNVERIFIED")
    if not route:
        raise DataError("This game has no usable parsed purchase history. Choose another game.")
    if route.role != role or (lane and route.lane != lane):
        raise DataError("This game's estimated role/lane differs from your selection. Adjust the selectors first.")
    route.warnings.extend(client.stale)
    return route
