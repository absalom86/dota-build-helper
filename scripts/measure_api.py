"""Small read-only latency probe; no credentials printed."""
from concurrent.futures import ThreadPoolExecutor
import json
import time
from urllib.request import Request, urlopen


def probe(url):
    start = time.monotonic()
    try:
        request = Request(url, headers={"User-Agent": "DotaBuildHelper/0.2"})
        if "stratz" in url:
            request = Request(url, data=json.dumps({"query": "{ __typename }"}).encode(),
                              headers={"Content-Type": "application/json", "User-Agent": "STRATZ_API"})
        with urlopen(request, timeout=4) as response:
            size = len(response.read())
            result = f"HTTP {response.status}, {size} bytes"
    except Exception as exc:
        result = f"{type(exc).__name__}" + (f" {exc.code}" if hasattr(exc, "code") else "")
    return {"url": url, "seconds": round(time.monotonic() - start, 2), "result": result}


if __name__ == "__main__":
    urls = ["https://api.opendota.com/api/heroes/1/matches", "https://api.opendota.com/api/matches/8972893223",
            "https://api.opendota.com/api/heroes/2/matchups", "https://api.stratz.com/graphql"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        print(json.dumps(list(pool.map(probe, urls)), indent=2))
