"""Reviewed lead photos for exact installed-edition bytes. No network, model call or original-file write."""
import fcntl
import hashlib
import logging
import os
import re
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit
from django.conf import settings
from .reasoning_preview import parse_preview_json
from .snapshot_store import atomic, read_bounded
from .snapshot_validation import SnapshotError, require

SCHEMA = "quorum.editorial-photos.v1"
MAX_BYTES = 262144
PHOTO_KEYS = {"url", "source_url", "license_url", "license", "credit", "caption", "rights_confirmed"}
LICENSES = {"public domain", "CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0"}
log = logging.getLogger(__name__)


def store():
    return Path(settings.DATA_DIR) / "editorial-photos"


def approved_url(value, licence=False):
    require(isinstance(value, str) and 0 < len(value) <= 4096, "invalid_photo_url")
    try:
        u = urlsplit(value)
        valid = u.scheme == "https" and not u.username and not u.password and u.port is None
        host = u.hostname or ""
    except ValueError:
        raise SnapshotError("invalid_photo_url") from None
    allowed = host.endswith(".gov") or host == "commons.wikimedia.org"
    allowed = allowed or (host == "creativecommons.org" if licence else host in {"upload.wikimedia.org", "thumb.wikimedia.org"})
    require(valid and allowed, "unapproved_photo_origin")


def parse(raw):
    require(len(raw) <= MAX_BYTES, "photo_manifest_too_large")
    p = parse_preview_json(raw)
    require(isinstance(p, dict) and set(p) == {"schema", "reviewed_by", "reviewed_at", "entries"}, "invalid_photo_manifest")
    require(p["schema"] == SCHEMA, "invalid_photo_schema")
    require(isinstance(p["reviewed_by"], str) and 0 < len(p["reviewed_by"].strip()) <= 200, "missing_photo_reviewer")
    try:
        reviewed = datetime.fromisoformat(p["reviewed_at"].replace("Z", "+00:00"))
        require(reviewed.utcoffset() is not None, "invalid_photo_review_time")
    except (TypeError, ValueError, AttributeError):
        raise SnapshotError("invalid_photo_review_time") from None
    require(isinstance(p["entries"], list) and len(p["entries"]) <= 200, "invalid_photo_entries")
    seen = set()
    for e in p["entries"]:
        require(isinstance(e, dict) and set(e) == {"topic_id", "edition_date", "snapshot_sha256", "event_id", "photo"}, "invalid_photo_entry")
        require(isinstance(e["topic_id"], str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", e["topic_id"]), "invalid_photo_topic")
        try:
            require(date.fromisoformat(e["edition_date"]).isoformat() == e["edition_date"], "invalid_photo_date")
        except (TypeError, ValueError):
            raise SnapshotError("invalid_photo_date") from None
        require(isinstance(e["snapshot_sha256"], str) and re.fullmatch(r"[a-f0-9]{64}", e["snapshot_sha256"]), "invalid_photo_binding")
        require(isinstance(e["event_id"], str) and 0 < len(e["event_id"].strip()) <= 160, "invalid_photo_event")
        key = tuple(e[k] for k in ("topic_id", "edition_date", "snapshot_sha256", "event_id"))
        require(key not in seen, "duplicate_photo_binding")
        seen.add(key)
        photo = e["photo"]
        require(isinstance(photo, dict) and set(photo) == PHOTO_KEYS, "invalid_photo_fields")
        require(photo["rights_confirmed"] is True, "photo_rights_unconfirmed")
        require(isinstance(photo["license"], str) and photo["license"] in LICENSES, "unapproved_photo_licence")
        for k in ("credit", "caption"):
            require(isinstance(photo[k], str) and 0 < len(photo[k].strip()) <= 1000, "missing_photo_credit_or_caption")
        for k in ("url", "source_url", "license_url"):
            approved_url(photo[k], licence=k == "license_url")
    return p


def attach(events, meta):
    # DECISION(2026-10-27, rcc00n/Codex): photos are separate reviewed presentation data, bound to exact
    # accepted bytes + topic/day/event. Why: add real licensed images without changing originals or rerunning models.
    root = store()
    try:
        if root.is_symlink():
            raise SnapshotError("linked_photo_store")
        raw = read_bounded(root / "current.json", MAX_BYTES)
        p = parse(raw)
    except FileNotFoundError:
        return
    except (OSError, SnapshotError, TypeError, ValueError):
        log.warning("Editorial photos unavailable: invalid private manifest")
        return  # A media failure never invalidates an accepted news edition.
    photos = {e["event_id"]: e["photo"] for e in p["entries"] if all(
        e[k] == meta[k] for k in ("topic_id", "edition_date", "snapshot_sha256"))}
    for event in events:
        if event["id"] in photos and isinstance(event.get("article"), dict):
            event["article"]["photo"] = deepcopy(photos[event["id"]])


def validate_bindings(p):
    from .reasoning_editions import installed, load, root
    base = root()
    require(base is not None, "reasoning_reader_unavailable")
    index, checked = installed(base), {}
    for e in p["entries"]:
        key = e["topic_id"], e["edition_date"]
        if key not in checked:
            item = index.get(e["edition_date"], {}).get(e["topic_id"])
            require(item is not None, "photo_edition_not_installed")
            result, meta = load(item[1], None)
            checked[key] = meta["snapshot_sha256"], {s["event_id"] for s in result["reasoning"]["stories"]}
        digest, ids = checked[key]
        require(e["snapshot_sha256"] == digest and e["event_id"] in ids, "photo_edition_binding_mismatch")


def publish(raw, expected_current):
    p = parse(raw)
    validate_bindings(p)
    root = store()
    require(not root.is_symlink(), "linked_photo_store")
    root.mkdir(mode=0o700, exist_ok=True)
    root.chmod(0o700)
    lock = os.open(root / "publish.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock, "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        current = root / "current.json"
        try:
            old = read_bounded(current, MAX_BYTES)
            old_hash = hashlib.sha256(old).hexdigest()
        except FileNotFoundError:
            old_hash = "none"
        require(expected_current == old_hash, "photo_manifest_changed")
        digest = hashlib.sha256(raw).hexdigest()
        # Immutable manifest copies make rollback a publish of previously reviewed bytes; no DB restoration.
        archive = root / f"{digest}.json"
        if archive.exists():
            require(read_bounded(archive, MAX_BYTES) == raw, "photo_archive_mismatch")
        else:
            atomic(archive, raw)
        atomic(current, raw)
    return digest
