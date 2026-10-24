#!/usr/bin/env python3
"""Run one collection pass for every topic in collectors/topics.yaml-free config below.

Usage:
    python3 -m collectors.run                # all collectors, all topics
    python3 -m collectors.run --only rss     # one collector: rss | guardian | federal_register | congress
    python3 -m collectors.run --loop 900     # repeat every 15 minutes

Schedule it with cron or `--loop`; no daemon framework yet (see collectors/README.md › Decisions).
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import congress, federal_register, guardian, rss  # noqa: E402
from collectors.common import Fetcher, connect, ensure_topic, load_sources_csv  # noqa: E402

# DECISION(2026-10-22, Anastasia/Claude): topics are a small dict in code until the portal exists; the demo event
# gets added here by the team. Why: the portal (topic picker) is not built yet and a YAML file is one more format.
# DECISION(2026-10-23, Anastasia/Claude Code): topic id is `russia-ukraine-war`, not `ukraine-aid`. Why: reasoning's
# README, CLI and its 28-claim evaluation set already use `russia-ukraine-war`; the id is shared across blocks and
# the collector is the cheaper side to rename. Rows collected under `ukraine-aid` are re-keyed by one UPDATE.
TOPICS = {
    "russia-ukraine-war": {
        "name": "Russia–Ukraine war and US aid",
        "query_terms": ["Ukraine", "Zelensky", "Zelenskyy", "Kyiv", "Ukrainian"],
    },
}

log = logging.getLogger("collectors.run")


def run_once(only: str | None = None) -> dict:
    conn = connect()
    fetcher = Fetcher()
    n = load_sources_csv(conn)
    log.info("sources.csv: %d rows upserted", n)
    report: dict = {}
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM sources WHERE kind IN ('outlet', 'agency', 'military') AND cardinality(rss_urls) > 0")
        rss_sources = cur.fetchall()
        cur.execute("SELECT * FROM sources WHERE kind = 'official' AND cardinality(rss_urls) > 0")
        official_feeds = cur.fetchall()
    for topic_id, spec in TOPICS.items():
        ensure_topic(conn, topic_id, spec["name"], spec["query_terms"])
        topic = {"id": topic_id, **spec}
        if only in (None, "rss"):
            for source in rss_sources:
                report[f"rss/{source['id']}"] = rss.collect_source(conn, fetcher, source, topic)
            for source in official_feeds:
                report[f"official/{source['id']}"] = rss.collect_official_feed(conn, fetcher, source, topic)
        if only in (None, "guardian"):
            report["guardian"] = guardian.collect(conn, fetcher, topic)
        if only in (None, "federal_register"):
            report["federal_register"] = federal_register.collect(conn, fetcher, topic)
        if only in (None, "congress"):
            report["congress"] = congress.collect(conn, fetcher, topic)
    conn.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["rss", "guardian", "federal_register", "congress"])
    parser.add_argument("--loop", type=int, metavar="SECONDS", help="repeat forever with this interval")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(name)s %(message)s")
    # httpx logs every request URL, including api-key query parameters; keep those out of terminals and screenshots.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    while True:
        report = run_once(args.only)
        total = sum(r.get("inserted", 0) for r in report.values())
        log.info("pass complete: %d new rows", total)
        if not args.loop:
            return 0
        time.sleep(args.loop)


if __name__ == "__main__":
    sys.exit(main())
