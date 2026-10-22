"""Shared plumbing for all collectors: env, database, polite HTTP, hashing, wire detection.

Module decisions are recorded in collectors/README.md › Decisions.
"""
from __future__ import annotations

import csv
import hashlib
import logging
import os
import re
import time
import urllib.robotparser as robotparser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
log = logging.getLogger("collectors")

# ---------------------------------------------------------------- env ----

def load_env() -> None:
    """Read .env / .env.local without overriding real environment variables."""
    for name in (".env", ".env.local"):
        path = ROOT / name
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def env(name: str, default: str = "") -> str:
    load_env()
    return (os.environ.get(name) or default).strip()


USER_AGENT = env("COLLECTOR_USER_AGENT", "QuorumBot/0.1 (+https://github.com/rcc00n/Quorum)")

# ----------------------------------------------------------- database ----

def connect() -> psycopg.Connection:
    url = env("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is missing from .env or .env.local")
    return psycopg.connect(url, row_factory=dict_row, autocommit=False)


def load_sources_csv(conn: psycopg.Connection, path: Path = HERE / "sources.csv") -> int:
    """Upsert the hand-edited registry. Returns number of rows written."""
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(
                """
                INSERT INTO sources (id, name, domain, kind, flank, tier, independence_group, audience,
                                     audience_source_url, allsides, mbfc, adfontes, rss_urls,
                                     access_level_default, country, lang)
                VALUES (%(id)s, %(name)s, %(domain)s, %(kind)s, %(flank)s, %(tier)s, %(independence_group)s,
                        %(audience)s, %(audience_source_url)s, %(allsides)s, %(mbfc)s, %(adfontes)s,
                        %(rss_urls)s, %(access_level_default)s, %(country)s, %(lang)s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name, domain = EXCLUDED.domain, kind = EXCLUDED.kind,
                    flank = EXCLUDED.flank, tier = EXCLUDED.tier,
                    independence_group = EXCLUDED.independence_group, audience = EXCLUDED.audience,
                    audience_source_url = EXCLUDED.audience_source_url, allsides = EXCLUDED.allsides,
                    mbfc = EXCLUDED.mbfc, adfontes = EXCLUDED.adfontes, rss_urls = EXCLUDED.rss_urls,
                    access_level_default = EXCLUDED.access_level_default, country = EXCLUDED.country,
                    lang = EXCLUDED.lang
                """,
                {
                    "id": r["id"], "name": r["name"], "domain": r["domain"], "kind": r["kind"],
                    "flank": r["flank"] or None, "tier": r["tier"] or None,
                    "independence_group": r["independence_group"],
                    "audience": int(r["audience"]) if r["audience"] else None,
                    "audience_source_url": r["audience_source_url"] or None,
                    "allsides": float(r["allsides"]) if r["allsides"] else None,
                    "mbfc": float(r["mbfc"]) if r["mbfc"] else None,
                    "adfontes": float(r["adfontes"]) if r["adfontes"] else None,
                    "rss_urls": [u for u in (r["rss_urls"] or "").split("|") if u],
                    "access_level_default": int(r["access_level_default"] or 1),
                    "country": r["country"] or None, "lang": r["lang"] or "en",
                },
            )
    conn.commit()
    return len(rows)


def ensure_topic(conn: psycopg.Connection, topic_id: str, name: str, query_terms: list[str]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO topics (id, name, query_terms) VALUES (%s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, query_terms = EXCLUDED.query_terms""",
            (topic_id, name, query_terms),
        )
    conn.commit()

# ------------------------------------------------------------- topics ----

def matches_topic(text: str, query_terms: Iterable[str]) -> bool:
    """Case-insensitive whole-word match of any term. Cheap gate before any fetch."""
    haystack = (text or "").lower()
    for term in query_terms:
        if re.search(r"\b" + re.escape(term.lower()) + r"\b", haystack):
            return True
    return False

# ------------------------------------------------------------ hashing ----

_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "cmpid", "ito"}


def canonicalize(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKING]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", urlencode(query), ""))


def content_hash(title: str, lead: str | None, text: str | None) -> str:
    # DECISION(2026-10-22, Anastasia/Claude): hash = title + lead + first 2000 chars of body, fixed at fetch time.
    # Why: stable across tracking-parameter changes, sensitive to edits of the article itself.
    blob = (title or "") + "\n" + (lead or "") + "\n" + (text or "")[:2000]
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

# ---------------------------------------------------- wire detection ----

_WIRE_PATTERNS = {
    "AP": re.compile(r"\b(associated press|\(ap\)|by ap\b|ap news)\b", re.I),
    "Reuters": re.compile(r"\breuters\b", re.I),
    "AFP": re.compile(r"\b(afp|agence france-presse)\b", re.I),
}


def detect_wire_origin(byline: str | None, lead: str | None) -> str | None:
    """Rule v1: byline or lead names a wire service. Title matching against agency rows is done in SQL later."""
    blob = f"{byline or ''} {lead or ''}"
    for name, pattern in _WIRE_PATTERNS.items():
        if pattern.search(blob):
            return name
    return None


WIRE_RULE_VERSION = "byline-v1"

# --------------------------------------------------------- polite HTTP ----

@dataclass
class Fetcher:
    """HTTP client that honours robots.txt and a per-domain delay."""

    min_interval: float = 2.0
    timeout: float = 20.0
    _robots: dict[str, robotparser.RobotFileParser | None] = field(default_factory=dict)
    _last_hit: dict[str, float] = field(default_factory=dict)
    _client: httpx.Client | None = None

    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=self.timeout)
        return self._client

    def _domain(self, url: str) -> str:
        return urlsplit(url).netloc.lower()

    def allowed(self, url: str) -> bool:
        """robots.txt verdict for our user agent; cached per domain for the process lifetime (re-run daily)."""
        domain = self._domain(url)
        if domain not in self._robots:
            rp = robotparser.RobotFileParser()
            try:
                resp = self.client().get(f"{urlsplit(url).scheme}://{domain}/robots.txt")
                if resp.status_code >= 400:
                    rp = None  # no robots.txt: nothing forbids us
                else:
                    rp.parse(resp.text.splitlines())
            except httpx.HTTPError:
                rp = None
            self._robots[domain] = rp
        rp = self._robots[domain]
        return True if rp is None else rp.can_fetch(USER_AGENT.split("/")[0], url)

    def _wait(self, url: str) -> None:
        domain = self._domain(url)
        elapsed = time.monotonic() - self._last_hit.get(domain, 0.0)
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_hit[domain] = time.monotonic()

    def get(self, url: str, *, respect_robots: bool = True, **kwargs: Any) -> httpx.Response | None:
        if respect_robots and not self.allowed(url):
            log.info("robots.txt disallows %s", url)
            return None
        self._wait(url)
        try:
            resp = self.client().get(url, **kwargs)
            resp.raise_for_status()
            return resp
        except httpx.HTTPError as exc:
            log.warning("fetch failed %s: %s", url, type(exc).__name__)
            return None

# ------------------------------------------------------------- writes ----

@dataclass
class Doc:
    source_id: str
    topic_id: str | None
    url: str
    title: str
    lead: str | None
    byline: str | None
    published_at: datetime | None
    access_level: int
    lang: str = "en"
    body_for_hash: str | None = None  # used for the hash only, never stored


def upsert_document(conn: psycopg.Connection, d: Doc) -> int | None:
    """Insert a document row; returns its id, or None if this exact (url, hash) already exists."""
    canon = canonicalize(d.url)
    h = content_hash(d.title, d.lead, d.body_for_hash)
    wire = detect_wire_origin(d.byline, d.lead)
    with conn.cursor() as cur:
        cur.execute("SELECT id, content_hash FROM documents WHERE canonical_url = %s ORDER BY id DESC LIMIT 1", (canon,))
        prev = cur.fetchone()
        if prev and prev["content_hash"] == h:
            cur.execute("UPDATE documents SET fetched_at = now() WHERE id = %s", (prev["id"],))
            conn.commit()
            return None
        cur.execute(
            """
            INSERT INTO documents (source_id, topic_id, url, canonical_url, title, lead, byline, published_at,
                                   lang, access_level, content_hash, wire_origin, wire_origin_version, supersedes_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (d.source_id, d.topic_id, d.url, canon, d.title, d.lead, d.byline, d.published_at, d.lang,
             d.access_level, h, wire, WIRE_RULE_VERSION if wire else None, prev["id"] if prev else None),
        )
        new_id = cur.fetchone()["id"]
    conn.commit()
    return new_id


def upsert_official_doc(conn: psycopg.Connection, *, source_id: str, topic_id: str | None, url: str, doc_type: str,
                        doc_number: str | None, title: str, full_text: str, signed_at: datetime | None,
                        published_at: datetime | None, lang: str = "en") -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO official_docs (source_id, topic_id, url, doc_type, doc_number, title, full_text,
                                       signed_at, published_at, lang)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (url) DO UPDATE SET full_text = EXCLUDED.full_text, title = EXCLUDED.title,
                                            fetched_at = now()
            RETURNING (xmax = 0) AS inserted
            """,
            (source_id, topic_id, url, doc_type, doc_number, title, full_text, signed_at, published_at, lang),
        )
        inserted = cur.fetchone()["inserted"]
    conn.commit()
    return bool(inserted)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
