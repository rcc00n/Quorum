"""Login-only reader for installed reasoning 1.0 editions. Opt-in by flag; never a provider call.

DECISION(2026-10-26, Anastasia/Claude Code; agreed in Issue #2 by Yelysei (comment 6411653104) and Anastasia
(6411408519), Vadim's items covered this week at Yelysei's request (6426106426), his recorded decisions kept):
real reasoning 1.0 editions reach signed-in readers only through this module. It is off unless
QUORUM_ENABLE_REASONING_READER=1 and QUORUM_REASONING_EDITIONS_ROOT names a private directory that
`manage.py reasoning_snapshot … --install` filled after the acceptance checks passed. The proposal store, the
loopback DEBUG preview and the rule that anonymous visitors see no publication are unchanged. Why: the store
validates only `quorum.portal.snapshot.v1-proposal`, the preview is loopback-only, and the judges need a login
that shows the day's real editions with the same labels the preview shows.

Layout under the root: <topic>/<date>/v<N>.json (the original bytes), v<N>.sidecar.json, v<N>.meta.json
(install record). The highest N of a topic and date is current. Nothing here writes; the command does.
"""
import hashlib
import json
import os
import re
from pathlib import Path
from django.conf import settings
from .snapshot_store import read_bounded
from .snapshot_validation import SnapshotError

ENABLE = "QUORUM_ENABLE_REASONING_READER"
ROOT = "QUORUM_REASONING_EDITIONS_ROOT"
TOPIC = re.compile(r"[a-z0-9][a-z0-9-]{0,79}")
DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
VERSION = re.compile(r"v(\d{1,4})\.json")
# Reasoning's roundup vocabulary (reasoning/quorum_reasoning/nodes/roundup.py: "confirmed", "disputed",
# "statements only", "single source", "reported, not confirmed", "unverified") mapped to the portal's claim
# statuses; the producer's own wording travels with every line as `label`. Anything unmapped is unknown.
STATUS = {
    "confirmed": "established",
    "established": "established",
    "disputed": "disputed",
    "statements only": "attributed",
    "statement": "attributed",
    "attributed": "attributed",
}
INVALID = (SnapshotError, OSError, ValueError, TypeError, KeyError, AttributeError)


def root():
    """The editions directory when the reader is switched on and configured; otherwise None."""
    if os.getenv(ENABLE) != "1":
        return None
    value = os.getenv(ROOT, "")
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute() or not path.is_dir():
        return None
    return path


def revision_id(day):
    return f"editions-{day}"


def _versions(folder):
    out = {}
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    for name in names:
        match = VERSION.fullmatch(name)
        if match and (folder / name).is_file():
            out[int(match[1])] = folder / name
    return out


def installed(base):
    """{day: {topic: (version, path)}} for the current version of every installed edition."""
    out = {}
    try:
        topics = sorted(os.listdir(base))
    except OSError:
        return out
    for topic in topics:
        if not TOPIC.fullmatch(topic) or not (base / topic).is_dir():
            continue
        try:
            days = sorted(os.listdir(base / topic))
        except OSError:
            continue
        for day in days:
            if not DAY.fullmatch(day) or not (base / topic / day).is_dir():
                continue
            versions = _versions(base / topic / day)
            if versions:
                current = max(versions)
                out.setdefault(day, {})[topic] = (current, versions[current])
    return out


def load(path, catalog):
    """Present one installed edition exactly as the preview does; bind its sidecar when installed with one."""
    from .reasoning_preview import present_reasoning, bind_preview_sidecar, parse_preview_json
    from .snapshot_validation import require

    raw = read_bounded(path)
    result = present_reasoning(raw, catalog=catalog if catalog and catalog["catalog_revision"] else None)
    stem = path.name[: -len(".json")]
    sidecar = path.with_name(stem + ".sidecar.json")
    # DECISION(2026-10-26, rcc00n/Codex): serve only complete, hash-bound install triplets.
    # Why: removing a sidecar or replacing accepted bytes must not silently bypass the installer's gates.
    sidecar_raw = read_bounded(sidecar)
    bind_preview_sidecar(sidecar_raw, raw, result)
    meta_path = path.with_name(stem + ".meta.json")
    meta = parse_preview_json(read_bounded(meta_path, 65536))
    require(isinstance(meta, dict), 'invalid_install_record')
    require(meta.get('snapshot_sha256') == hashlib.sha256(raw).hexdigest()
            and meta.get('sidecar_sha256') == hashlib.sha256(sidecar_raw).hexdigest(), 'install_hash_mismatch')
    p = result['reasoning']
    require(all(type(meta.get(k)) is type(p[k]) and meta[k] == p[k]
                for k in ('topic_id', 'edition_date', 'version', 'run_id')), 'install_identity_mismatch')
    require(settings.DEBUG or p['provenance']['fictional'] is False, 'fictional_edition_requires_debug')
    return result, meta


def edition_of(p, result):
    """The edition row the brief reads: completion, quiet day, summary, the preview's honesty labels, the roundup."""
    preview = result["preview"]
    binding = preview.get("corpus_binding") or {}
    # The preview's labels travel with the edition (Yelysei's review of PR #31): the sidecar's provisional
    # flag and corpus capture time, the edition window and the preview warnings, so the reader never
    # presents an edition as firmer than the preview would. No bound flag reads as provisional.
    provisional = preview.get("provisional")
    return {
        "topic_id": p["topic_id"],
        "date": p["edition_date"],
        "completion": "partial" if p["status"] == "partial" or p.get("errors") else "complete",
        "quiet_day": bool(p["roundup"]["empty_day"]),
        "summary": p["summary"],
        "provisional": True if provisional is None else bool(provisional),
        "corpus_as_of_utc": binding.get("corpus_as_of_utc"),
        "edition_window_utc": [p["window"]["start"], p["window"]["end"]],
        "closed_edition": bool(binding.get("closed_edition")),
        "warnings": list(preview.get("warnings") or []),
        "missing_provenance": list(preview.get("missing_provenance") or []),
        "roundup": [
            {
                "name": group["name"],
                "items": [
                    {
                        # Below-the-bar events have no page of their own: no event link is offered.
                        "event_id": None,
                        "text": item["line"],
                        "status": STATUS.get(item["status"], "unknown"),
                        "label": item["status"],
                        "line_source": item.get("line_source"),
                        "needs_review": item.get("needs_review"),
                        "sources": [{"title": s["title"], "url": s["url"]} for s in item["sources"]],
                    }
                    for item in group["items"]
                ],
            }
            for group in p["roundup"]["groups"]
        ],
    }


def snapshot(day, topic="", revision=None):
    """The feed for a day from the installed editions, or None when the reader has nothing for it."""
    base = root()
    if base is None or not day or not DAY.fullmatch(day):
        return None
    index = installed(base).get(day)
    if not index or (topic and topic not in index):
        return None
    if revision and revision != revision_id(day):
        return None
    from .integration import CatalogAdapter

    catalog = CatalogAdapter().snapshot()
    if catalog["status"] == "error":
        catalog = None
    names = {t["id"]: t["name"] for t in (catalog["topics"] if catalog else [])}
    events, editions, digests, errors, sources, seen = [], [], [], [], {}, []
    edition_of_event = {}
    fictional, partial, generated, expires, published, run_ids = False, [], [], [], [], []
    for name, (version, path) in sorted(index.items()):
        if topic and name != topic:
            continue
        try:
            result, meta = load(path, catalog)
        except INVALID:
            errors.append(
                {
                    "code": "reasoning_edition_invalid",
                    "message": f"The installed edition for {name} could not be read or validated.",
                    "event_id": None,
                }
            )
            partial.append(True)
            continue
        p = result["reasoning"]
        seen.append(name)
        fictional = fictional or p["provenance"]["fictional"]
        partial.append(result["preview"]["status"] == "partial")
        events.extend(result["events"])
        digests.extend(result["digests"])
        errors.extend(p.get("errors", []))
        editions.append(edition_of(p, result))
        for event_row in result["events"]:
            edition_of_event[event_row["id"]] = editions[-1]
        generated.append(p["generated_at"])
        expires.append(p["expires_at"])
        run_ids.append(p["run_id"])
        if isinstance(meta.get("installed_at"), str):
            published.append(meta["installed_at"])
        if not catalog:
            sources.update({s["id"]: s for s in result["sources"]})
    if not seen:
        # A configured, broken installed day is an error; never fall through to a successful pending feed.
        catalog = catalog or {'catalog_revision': None, 'topics': [], 'sources': []}
        return {**catalog, 'status': 'error', 'events': [], 'digests': [], 'editions': [], 'errors': errors,
                'publication': {'status': 'error', 'error_code': 'reasoning_edition_invalid',
                                'revision': revision_id(day), 'edition': day}}
    topics = [dict(t) for t in (catalog["topics"] if catalog else [])]
    topics.extend({"id": name, "name": names.get(name, name)} for name in seen if name not in names)
    # DECISION(2026-10-26, Anastasia/Claude Code): a day is "partial" for the brief only when every edition read
    # for it is partial (or the one topic asked for is); other gaps stay per edition (`completion`) and in
    # `errors`, so one incomplete topic never hides the others' stories. Why: the brief's empty state is per
    # publication, the reasoning contract's partial status is per edition.
    return {
        "status": "demo" if fictional else "available",
        "catalog_revision": catalog["catalog_revision"] if catalog else None,
        "topics": topics,
        "sources": catalog["sources"] if catalog else list(sources.values()),
        "events": events,
        "digests": digests,
        "editions": editions,
        "publication": {
            "status": "partial" if all(partial) else "available",
            "revision": revision_id(day),
            "edition": day,
            "run_id": ", ".join(run_ids),
            "generated_at": max(generated),
            "expires_at": min(expires),
            # published_at is when the reader began serving the edition to signed-in readers, i.e. the
            # install time; installed_at says the same under its own name.
            "published_at": max(published) if published else None,
            "installed_at": max(published) if published else None,
            "provisional": any(e["provisional"] for e in editions),
            # The earliest capture time among the provisional editions served; event() narrows it to the
            # event's own edition (Yelysei's re-review of PR #31).
            "corpus_as_of_utc": min(
                (e["corpus_as_of_utc"] for e in editions if e["provisional"] and e["corpus_as_of_utc"]),
                default=None,
            ),
            "warnings": list(dict.fromkeys(w for e in editions for w in e["warnings"])),
            "fallback": False,
            "mode": "demo" if fictional else "live",
        },
        "errors": errors,
        "_edition_of_event": edition_of_event,
    }


def feed(day, topic="", revision=None):
    """snapshot() for the feed: the per-event helper map is not part of the API."""
    result = snapshot(day, topic, revision)
    if result is not None:
        result.pop("_edition_of_event", None)
    return result


def event(event_id, day="", revision=None):
    """The feed holding one event, or None when no installed edition carries it."""
    base = root()
    if base is None:
        return None
    if day:
        result = snapshot(day, revision=revision)
    else:
        result = None
        for candidate in sorted(installed(base), reverse=True):
            found = snapshot(candidate)
            if found and any(e["id"] == event_id for e in found["events"]):
                result = found
                break
    if result is None:
        return None
    own = result.pop("_edition_of_event", {}).get(event_id)
    if own:
        result["publication"]["provisional"] = own["provisional"]
        result["publication"]["corpus_as_of_utc"] = own["corpus_as_of_utc"]
        result["publication"]["warnings"] = list(own["warnings"])
    result["events"] = [e for e in result["events"] if e["id"] == event_id]
    return result
