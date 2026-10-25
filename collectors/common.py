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
                                     access_level_default, country, lang,
                                     allsides_label, allsides_source_url, mbfc_label, mbfc_source_url,
                                     adfontes_source_url, ratings_checked_at)
                VALUES (%(id)s, %(name)s, %(domain)s, %(kind)s, %(flank)s, %(tier)s, %(independence_group)s,
                        %(audience)s, %(audience_source_url)s, %(allsides)s, %(mbfc)s, %(adfontes)s,
                        %(rss_urls)s, %(access_level_default)s, %(country)s, %(lang)s,
                        %(allsides_label)s, %(allsides_source_url)s, %(mbfc_label)s, %(mbfc_source_url)s,
                        %(adfontes_source_url)s, %(ratings_checked_at)s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name, domain = EXCLUDED.domain, kind = EXCLUDED.kind,
                    flank = EXCLUDED.flank, tier = EXCLUDED.tier,
                    independence_group = EXCLUDED.independence_group, audience = EXCLUDED.audience,
                    audience_source_url = EXCLUDED.audience_source_url, allsides = EXCLUDED.allsides,
                    mbfc = EXCLUDED.mbfc, adfontes = EXCLUDED.adfontes, rss_urls = EXCLUDED.rss_urls,
                    access_level_default = EXCLUDED.access_level_default, country = EXCLUDED.country,
                    lang = EXCLUDED.lang,
                    allsides_label = EXCLUDED.allsides_label, allsides_source_url = EXCLUDED.allsides_source_url,
                    mbfc_label = EXCLUDED.mbfc_label, mbfc_source_url = EXCLUDED.mbfc_source_url,
                    adfontes_source_url = EXCLUDED.adfontes_source_url, ratings_checked_at = EXCLUDED.ratings_checked_at
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
                    # provenance columns (migrations_002); absent in older CSVs -> NULL
                    "allsides_label": r.get("allsides_label") or None,
                    "allsides_source_url": r.get("allsides_source_url") or None,
                    "mbfc_label": r.get("mbfc_label") or None,
                    "mbfc_source_url": r.get("mbfc_source_url") or None,
                    "adfontes_source_url": r.get("adfontes_source_url") or None,
                    "ratings_checked_at": r.get("ratings_checked_at") or None,
                },
            )
    conn.commit()
    return len(rows)


def ensure_topic(conn: psycopg.Connection, topic_id: str, name: str, query_terms: list[str]) -> None:
    """Seed a topic if it does not exist. DECISION(2026-10-25, Anastasia/Claude Code): ON CONFLICT DO NOTHING, not
    UPDATE. Why: the topics table is the source of truth (the web app writes it); a seed in code must not overwrite a
    user's or reasoning's terms on every pass. Changing a seeded topic's terms is an UPDATE on the table."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO topics (id, name, query_terms) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
            (topic_id, name, query_terms),
        )
    conn.commit()


_TOPIC_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")  # reasoning's --topic rule (tools/corpus.py)


def load_topics(conn: psycopg.Connection) -> list[dict]:
    """Active topics in collection order (created_at, id): the first topic that matches a document keeps it.

    A row with a bad slug or no terms is skipped with a warning rather than aborting the pass: the web app may have
    written it a moment ago and can still fix it; nothing is collected under it until then.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, query_terms FROM topics WHERE active ORDER BY created_at, id")
        rows = cur.fetchall()
    topics: list[dict] = []
    for r in rows:
        terms = [t.strip() for t in (r["query_terms"] or []) if t and t.strip()]
        if not _TOPIC_SLUG.match(r["id"]) or not terms:
            log.warning("topic %r skipped: %s", r["id"], "bad slug" if not _TOPIC_SLUG.match(r["id"]) else "no query_terms")
            continue
        topics.append({"id": r["id"], "name": r["name"], "query_terms": terms})
    return topics

# ------------------------------------------------------------- topics ----

def matches_topic(text: str, query_terms: Iterable[str]) -> bool:
    """Case-insensitive whole-word match of any term. Cheap gate before any fetch."""
    haystack = (text or "").lower()
    for term in query_terms:
        if re.search(r"\b" + re.escape(term.lower()) + r"\b", haystack):
            return True
    return False


def topic_match_of(title: str, lead: str | None, query_terms: Iterable[str]) -> str | None:
    """'title' when a term is in the headline, 'lead' when only in the summary, else None (documents.topic_match)."""
    terms = list(query_terms)
    if matches_topic(title, terms):
        return "title"
    if lead and matches_topic(lead, terms):
        return "lead"
    return None


def first_topic_match(title: str, lead: str | None, topics: list[dict]) -> tuple[dict, str] | tuple[None, None]:
    """The first topic in list order whose terms match, with where it matched: (topic, 'title' | 'lead').

    Each topic is {"id", "name", "query_terms"} as load_topics returns them (collection order: created_at, id); the
    per-topic rule is topic_match_of, unchanged. Returns (None, None) when no topic matches, so the caller skips.

    Decision: collectors/README.md › Decisions, 2026-10-25 (single feed walk, first topic in collection order wins).
    """
    for topic in topics:
        match = topic_match_of(title, lead, topic["query_terms"])
        if match:
            return topic, match
    return None, None

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

# Wire detection — what it catches and what it does not (wire-v2, 2026-10-23).
# Reasoning counts a reprint in the WIRE's independence group (lowercased value must equal the agency row's
# independence_group: AP->ap, Reuters->reuters, AFP->afp), so a MISSED mark double-counts a reprint as an
# independent outlet and can falsely confirm a claim, while a FALSE mark folds an outlet's own reporting into the
# agency and can hide a real confirmation. The rule therefore fires only on authorship signals:
#   - byline names the agency ("By The Associated Press", "AP", "Reuters", "AFP", "Reuters Staff")
#   - lead OPENS with a wire dateline credit: "WASHINGTON (AP) —", "(Reuters) -", "KYIV, Oct 22 (Reuters)"
#   - an "AP/Reuters/AFP contributed to this report" or "Reporting by ... Editing by ..." trailer
# It does NOT fire on a mere mention inside the lead ("..., Reuters reported Tuesday") — that is citation,
# not reprint. Reprints with the wire credit only deep in the body (level 2 documents: no body) are missed.
# DECISION(2026-10-24, Anastasia/Claude Code): the dateline place may carry commas and slashes ("KYIV, Ukraine (AP) —",
# "WASHINGTON/KYIV, Oct 22 (Reuters) -"); the rule label is bumped to wire-v3 so wire_origin_version says which class
# marked a row. Why: AP's city-country form is the standard dateline on this topic; without the comma every such
# reprint was counted as an independent outlet. No live row had been marked under wire-v2 (0 marks on 2026-10-24).
_WIRE_NAMES = {
    "AP": r"(?:the\s+)?associated\s+press|\bAP\b",
    "Reuters": r"\breuters\b",
    "AFP": r"\bAFP\b|agence\s+france[- ]presse",
}
_WIRE_BYLINE = {k: re.compile(rf"^\s*(?:by\s+)?(?:{v})(?:\s+staff|\s+news)?\s*$", re.I) for k, v in _WIRE_NAMES.items()}
_WIRE_DATELINE = {k: re.compile(rf"^\s*(?:[A-Z][A-Za-z.,'/ -]{{1,60}},?\s*(?:[A-Z][a-z]{{2,8}}\.?\s+\d{{1,2}}\s*)?)?\(\s*(?:{v})\s*\)\s*[-\u2013\u2014:]", re.I) for k, v in _WIRE_NAMES.items()}
_WIRE_TRAILER = {k: re.compile(rf"(?:{v})\s+contributed\s+to\s+this\s+report", re.I) for k, v in _WIRE_NAMES.items()}
# "Reporting by ...; Editing by ..." is Reuters' house sign-off and appears on no other agency's copy.
_REUTERS_SIGNOFF = re.compile(r"\breporting\s+by\b.*\bediting\s+by\b", re.I | re.S)


def detect_wire_origin(byline: str | None, lead: str | None) -> str | None:
    """Return 'AP' | 'Reuters' | 'AFP' when the document is a wire reprint by authorship signals, else None."""
    b, l = (byline or "").strip(), (lead or "").strip()
    for name in ("AP", "Reuters", "AFP"):
        if b and _WIRE_BYLINE[name].search(b):
            return name
        if l and (_WIRE_DATELINE[name].search(l) or _WIRE_TRAILER[name].search(l)):
            return name
    if l and _REUTERS_SIGNOFF.search(l):
        return "Reuters"
    return None


WIRE_RULE_VERSION = "wire-v3"

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

    def resolve(self, url: str) -> str:
        """Hook for aggregator links. Google News RSS links cannot be resolved without executing Google's
        JavaScript (checked 2026-10-22: no redirect, no decodable token in the HTML), so they are left as-is and
        such sources are collected at level 3 only (fact of coverage). See collectors/README.md › Decisions."""
        return url

    def get(self, url: str, *, respect_robots: bool = True, **kwargs: Any) -> httpx.Response | None:
        url = self.resolve(url)
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
    topic_match: str | None = None  # 'title' | 'lead' | 'body' (schema.sql DECISION 2026-10-24)


def upsert_document(conn: psycopg.Connection, d: Doc) -> int | None:
    """Insert a document row; returns its id, or None if this exact (url, hash) already exists."""
    canon = canonicalize(d.url)
    d.title, d.lead, d.byline = clean_field(d.title, TITLE_MAX) or "", clean_field(d.lead, LEAD_MAX), clean_field(d.byline, 200)
    h = content_hash(d.title, d.lead, d.body_for_hash)
    wire = detect_wire_origin(d.byline, d.lead)
    with conn.cursor() as cur:
        # DECISION(2026-10-24, Anastasia/Claude Code): a (canonical_url, content_hash) pair that already exists anywhere
        # in the chain is a known version: refresh its fetched_at and insert nothing, even if it is not the newest row.
        # Why: the previous code compared only against the newest row, so an article whose hash reverted (A -> B -> A)
        # hit the UNIQUE constraint and crashed the whole pass; the live collector restarted 37 times on one Fox News
        # URL between 00:23Z and 01:03Z on 2026-10-24 and no source after it was collected.
        cur.execute("SELECT id FROM documents WHERE canonical_url = %s AND content_hash = %s", (canon, h))
        known = cur.fetchone()
        if known:
            cur.execute("UPDATE documents SET fetched_at = now() WHERE id = %s", (known["id"],))
            conn.commit()
            return None
        cur.execute("SELECT id FROM documents WHERE canonical_url = %s ORDER BY id DESC LIMIT 1", (canon,))
        prev = cur.fetchone()
        cur.execute(
            """
            INSERT INTO documents (source_id, topic_id, url, canonical_url, title, lead, byline, published_at,
                                   lang, access_level, content_hash, wire_origin, wire_origin_version, supersedes_id,
                                   topic_match)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (d.source_id, d.topic_id, d.url, canon, d.title, d.lead, d.byline, d.published_at, d.lang,
             d.access_level, h, wire, WIRE_RULE_VERSION if wire else None, prev["id"] if prev else None,
             d.topic_match),
        )
        new_id = cur.fetchone()["id"]
    conn.commit()
    return new_id


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TAGS_INLINE = re.compile(r"<[^>]+>")
TITLE_MAX, LEAD_MAX = 300, 600


def clean_text(value: str | None) -> str | None:
    """Postgres TEXT rejects NUL bytes; some Federal Register raw texts contain them. Also drops other C0 controls."""
    return _CONTROL.sub("", value) if value else value


def clean_field(value: str | None, max_len: int) -> str | None:
    """Title/lead hygiene at collection time (injection audit, 2026-10-23): strip tags and control characters,
    collapse whitespace, cap length. Reasoning caps again on its side; two layers."""
    if not value:
        return value
    from html import unescape
    text = " ".join(unescape(_TAGS_INLINE.sub(" ", _CONTROL.sub("", value))).split())
    return text[:max_len] or None


def upsert_official_doc(conn: psycopg.Connection, *, source_id: str, topic_id: str | None, url: str, doc_type: str,
                        doc_number: str | None, title: str, full_text: str, signed_at: datetime | None,
                        published_at: datetime | None, lang: str = "en") -> bool:
    title, full_text = clean_field(title, TITLE_MAX) or "", clean_text(full_text) or ""
    with conn.cursor() as cur:
        # DECISION(2026-10-24, Anastasia/Claude Code): a re-collected official document refreshes doc_type, doc_number and
        # its dates, not only its text; a date the API omits this pass never replaces a stored one (COALESCE). Why:
        # congress.py derives doc_type from the bill's latest action, which changes between passes (introduced ->
        # passed -> enacted); frozen at first sight, an enacted bill would have stayed 'release' and never confirmed.
        # official_docs has no version chain (unlike documents): a row is the latest known state of its URL.
        cur.execute(
            """
            INSERT INTO official_docs (source_id, topic_id, url, doc_type, doc_number, title, full_text,
                                       signed_at, published_at, lang)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (url) DO UPDATE SET full_text = EXCLUDED.full_text, title = EXCLUDED.title,
                                            doc_type = EXCLUDED.doc_type, doc_number = EXCLUDED.doc_number,
                                            signed_at = COALESCE(EXCLUDED.signed_at, official_docs.signed_at),
                                            published_at = COALESCE(EXCLUDED.published_at, official_docs.published_at),
                                            fetched_at = now()
            RETURNING (xmax = 0) AS inserted
            """,
            (source_id, topic_id, url, doc_type, doc_number, title, full_text, signed_at, published_at, lang),
        )
        inserted = cur.fetchone()["inserted"]
    conn.commit()
    return bool(inserted)


# ------------------------------------------------ public contract: fetch_text ----

_P_TAG = re.compile(r"<p[^>]*>(.*?)</p>", re.I | re.S)
_ANY_TAG = re.compile(r"<[^>]+>")
_DROP_BLOCKS = re.compile(r"<(script|style|nav|header|footer|aside|noscript|form|svg)\b.*?</\1>", re.I | re.S)
_MAIN_BLOCK = re.compile(r"<(article|main)\b.*?</\1>", re.I | re.S)
_SHARED_FETCHER: Fetcher | None = None


def extract_text(html: str) -> str:
    """Article paragraphs from a page, deterministically: the SAME function feeds documents.content_hash at
    collection time and FetchedText.text at analysis time, so hashes and offsets agree.

    Prefers the <article>/<main> block when present; drops navigation, header, footer, scripts and styles;
    keeps <p> paragraphs joined by a blank line; strips NUL bytes.
    """
    # DECISION(2026-10-22, Anastasia/Claude): one extractor for hashing and for quoting. Why: the first live probe
    # showed NPR's "Skip to main content" navigation leading the text and hashes differing between the two paths.
    from html import unescape
    body = _DROP_BLOCKS.sub(" ", html)
    main = _MAIN_BLOCK.search(body)
    scope = main.group(0) if main else body
    paras = []
    for raw in _P_TAG.findall(scope):
        cleaned = " ".join(unescape(_ANY_TAG.sub(" ", raw)).split())
        if len(cleaned) >= 20:  # skip captions, labels and one-word paragraphs
            paras.append(cleaned)
    return clean_text("\n\n".join(paras)) or ""


@dataclass
class FetchedText:
    url: str
    text: str            # paragraph text only; Unicode str, offsets in code points
    content_hash: str    # same formula as documents.content_hash, so a quote can be tied to the version it was cut from
    access_level: int    # 1 = full text returned; 2 = page not fetchable (robots.txt / error), text is empty
    fetched_at: datetime


def fetch_text(url: str, *, title: str = "", lead: str | None = None, fetcher: Fetcher | None = None) -> FetchedText:
    """The one function reasoning calls to read an article at analysis time.

    Honours robots.txt and the per-domain delay; never stores the text. Returns the paragraph text, the content hash
    computed with the same formula as `documents.content_hash` (title + lead + first 2000 chars of body), and the
    access level actually achieved. Character offsets that reasoning records in `quotes.char_start/char_end` are
    indexes into `FetchedText.text` as a Python str (Unicode code points, not bytes).
    """
    # DECISION(2026-10-22, Anastasia/Claude): fetch_text is the public contract; rss.py's internal helpers are not.
    # Why: ARCHITECTURE.md (reasoning) calls fetch_text(url); it must exist with stable semantics.
    global _SHARED_FETCHER
    if fetcher is None:
        if _SHARED_FETCHER is None:
            _SHARED_FETCHER = Fetcher()
        fetcher = _SHARED_FETCHER
    now = datetime.now(timezone.utc)
    resp = fetcher.get(url)
    if resp is None:
        return FetchedText(url=url, text="", content_hash=content_hash(title, lead, None), access_level=2, fetched_at=now)
    text = extract_text(resp.text)
    return FetchedText(url=url, text=text, content_hash=content_hash(title, lead, text), access_level=1, fetched_at=now)


def verify_quote(text: str, quote_text: str, char_start: int, char_end: int) -> bool:
    """The rule the quotes table enforces: the quote must appear verbatim at the given code-point offsets."""
    return 0 <= char_start < char_end <= len(text) and text[char_start:char_end] == quote_text


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
