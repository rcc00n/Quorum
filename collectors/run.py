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
from collectors.common import Fetcher, connect, ensure_topic, load_sources_csv, load_topics  # noqa: E402

# DECISION(2026-10-22, Anastasia/Claude): topics are a small dict in code until the portal exists; the demo event
# gets added here by the team. Why: the portal (topic picker) is not built yet and a YAML file is one more format.
# -- superseded 2026-10-25: the `topics` TABLE is the source of truth (free-text topics typed by the user, Issue #2,
# Yelysei 2026-10-25); this dict is only the seed, inserted if missing (ensure_topic) and never overwriting the table.
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
    errors = 0

    def step(key: str, fn, *args) -> None:
        """One collector or source per step. DECISION(2026-10-24, Anastasia/Claude Code): an exception inside one
        collector is logged with its traceback, rolled back, counted and reported as {"error": <type>}; the pass goes
        on with the next source. Why: without this boundary one bad item (a UNIQUE violation on 2026-10-24, a JSON
        decode error, a bad URL) aborted the whole pass, the container restarted 37 times and every source after
        the failing one was silently not collected; the freshness check could not see it."""
        nonlocal errors
        try:
            report[key] = fn(*args)
        except Exception as exc:  # noqa: BLE001 - the boundary exists to keep the pass alive
            log.exception("%s failed: %s", key, type(exc).__name__)
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            report[key] = {"error": type(exc).__name__}
            errors += 1

    for topic_id, spec in TOPICS.items():
        ensure_topic(conn, topic_id, spec["name"], spec["query_terms"])
    topics = load_topics(conn)
    log.info("topics: %s", ", ".join(f"{t['id']} ({len(t['query_terms'])} terms)" for t in topics) or "none active")
    for topic in topics:
        t = topic["id"]  # report keys carry the topic so N topics do not overwrite each other's counters
        if only in (None, "rss"):
            for source in rss_sources:
                step(f"{t}/rss/{source['id']}", rss.collect_source, conn, fetcher, source, topic)
            for source in official_feeds:
                step(f"{t}/official/{source['id']}", rss.collect_official_feed, conn, fetcher, source, topic)
        if only in (None, "guardian"):
            step(f"{t}/guardian", guardian.collect, conn, fetcher, topic)
        if only in (None, "federal_register"):
            step(f"{t}/federal_register", federal_register.collect, conn, fetcher, topic)
        if only in (None, "congress"):
            step(f"{t}/congress", congress.collect, conn, fetcher, topic)
    conn.close()
    report["_errors"] = errors
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
        errors = report.pop("_errors", 0)
        total = sum(r.get("inserted", 0) for r in report.values())
        log.info("pass complete: %d new rows, %d collector errors", total, errors)
        if not args.loop:
            return 0
        time.sleep(args.loop)


if __name__ == "__main__":
    sys.exit(main())
