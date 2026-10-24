#!/usr/bin/env python3
"""Check every feed in sources.csv and the robots.txt verdict for each domain. Network only, no database.

    python3 -m collectors.probe_feeds

Prints one line per feed: HTTP status, item count, and whether robots.txt lets QuorumBot fetch article pages.
Run it on a machine with open internet; the cloud sandbox cannot reach news sites.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.common import HERE, Fetcher  # noqa: E402
from collectors.rss import _entries  # noqa: E402  # same parser as the collector: RSS/Atom and the news-sitemap XML


def main() -> int:
    fetcher = Fetcher(min_interval=0.5)
    bad = 0
    with (HERE / "sources.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            feeds = [u for u in (row["rss_urls"] or "").split("|") if u]
            if not feeds:
                continue
            robots = fetcher.allowed(f"https://{row['domain']}/")
            for url in feeds:
                resp = fetcher.get(url, respect_robots=False)
                if resp is None:
                    print(f"FAIL  {row['id']:<16} unreachable  {url}")
                    bad += 1
                    continue
                n = len(_entries(resp.content))
                status = "OK  " if n else "WARN"
                bad += int(n == 0)
                print(f"{status}  {row['id']:<16} {resp.status_code} items={n:<3} robots={'allow' if robots else 'DENY '}  {url}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
