"""Local-only immutable revisions. No network listener or processing credentials."""

import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from django.conf import settings
from .snapshot_validation import (
    MAX_BYTES,
    SnapshotError,
    parse_snapshot,
    require,
    instant,
)

REVISION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")


def now():
    return datetime.now(timezone.utc)


def iso():
    return now().isoformat().replace("+00:00", "Z")


def read_bounded(path, limit=MAX_BYTES):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "unsafe_snapshot_file"
        )
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, "payload_too_large")
    return raw


def atomic(path, data):
    fd, name = tempfile.mkstemp(prefix=".publish-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def encoded(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


class SnapshotStore:
    def __init__(self, root=None):
        configured = root or os.getenv("QUORUM_SNAPSHOT_ROOT")
        self.root = Path(configured).absolute() if configured else None

    def prepare(self):
        require(self.root is not None, "snapshot_root_unconfigured")
        root = self.root
        auth = Path(settings.DATA_DIR).resolve()
        repo = Path(settings.BASE_DIR).resolve().parent
        require(
            not root.is_symlink()
            and root.resolve() == root
            and root != Path("/")
            and root not in auth.parents
            and not root.is_relative_to(auth)
            and root not in repo.parents
            and not root.is_relative_to(repo),
            "unsafe_snapshot_root",
        )
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        require(
            root.stat().st_uid == os.geteuid()
            and stat.S_IMODE(root.stat().st_mode) == 0o700,
            "unsafe_snapshot_permissions",
        )
        for name in ("staging", "revisions"):
            p = root / name
            require(not p.is_symlink(), "unsafe_snapshot_directory")
            p.mkdir(mode=0o700, exist_ok=True)
            require(
                p.stat().st_uid == os.geteuid()
                and stat.S_IMODE(p.stat().st_mode) == 0o700,
                "unsafe_snapshot_permissions",
            )

    @contextmanager
    def locked(self):
        self.prepare()
        fd = os.open(
            self.root / "publication.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(fd, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def audit(self, action, revision=None, code=None):
        record = {"at": iso(), "action": action, "revision": revision, "code": code}
        fd = os.open(
            self.root / "audit.jsonl",
            os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(fd, "ab") as stream:
            stream.write(encoded(record) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def heads(self, filename="current.json"):
        try:
            result = json.loads(read_bounded(self.root / filename, 65536))
            require(
                isinstance(result, dict) and len(result) <= 366,
                "invalid_snapshot_index",
            )
            for day, revision in result.items():
                from .snapshot_validation import edition_date

                require(
                    edition_date(day)
                    and isinstance(revision, str)
                    and REVISION.fullmatch(revision),
                    "invalid_snapshot_index",
                )
            return result
        except FileNotFoundError:
            return {}

    def revision(self, revision):
        require(
            isinstance(revision, str) and REVISION.fullmatch(revision),
            "invalid_revision",
        )
        raw = read_bounded(self.root / "revisions" / f"{revision}.json")
        meta = json.loads(
            read_bounded(self.root / "revisions" / f"{revision}.meta.json", 65536)
        )
        require(isinstance(meta, dict), "invalid_revision_metadata")
        require(
            meta.get("sha256") == hashlib.sha256(raw).hexdigest(), "integrity_mismatch"
        )
        payload = parse_snapshot(raw)
        require(
            meta.get("revision") == revision
            and meta.get("edition") == payload["edition"]
            and isinstance(meta.get("published_at"), str),
            "invalid_revision_metadata",
        )
        from .snapshot_validation import timestamp

        require(timestamp(meta["published_at"]), "invalid_revision_metadata")
        require(payload["revision"] == revision, "revision_mismatch")
        return payload, meta

    def publish(self, staged, digest, allow_demo=False):
        require(
            os.getenv("QUORUM_ENABLE_SNAPSHOT_PUBLICATION") == "1",
            "publication_disabled",
        )
        with self.locked():
            try:
                require(
                    isinstance(digest, str) and re.fullmatch("[a-f0-9]{64}", digest),
                    "invalid_integrity_digest",
                )
                staged = Path(staged).absolute()
                require(
                    staged.parent == self.root / "staging" and not staged.is_symlink(),
                    "unsafe_staging_path",
                )
                raw = read_bounded(staged)
                require(hashlib.sha256(raw).hexdigest() == digest, "integrity_mismatch")
                payload = parse_snapshot(raw)
                rev = payload["revision"]
                require(
                    payload["mode"] == "live" or allow_demo and settings.DEBUG,
                    "demo_publication_forbidden",
                )
                require(
                    instant(payload["generated_at"]) <= now() + timedelta(minutes=5),
                    "future_generation",
                )
                require(instant(payload["expires_at"]) > now(), "expired_publication")
                heads = self.heads()
                parent = heads.get(payload["edition"])
                destination = self.root / "revisions" / f"{rev}.json"
                if destination.exists():
                    previous, meta = self.revision(rev)
                    require(
                        hashlib.sha256(read_bounded(destination)).hexdigest() == digest,
                        "immutable_revision_conflict",
                    )
                    require(parent == rev, "existing_revision_requires_rollback")
                    return meta
                require(
                    payload["parent_revision"] == parent, "parent_revision_mismatch"
                )
                for event in payload["events"]:
                    for correction in event["analysis"]["corrections"]:
                        old, _ = self.revision(correction["previous_revision"])
                        require(
                            old["edition"] == payload["edition"]
                            and any(
                                c["id"] == correction["supersedes_claim_id"]
                                for e in old["events"]
                                if e["id"] == event["id"]
                                for c in e["analysis"]["claims"]
                            ),
                            "invalid_correction_history",
                        )
                meta = {
                    "revision": rev,
                    "edition": payload["edition"],
                    "published_at": iso(),
                    "sha256": digest,
                    "parent_revision": parent,
                    "event_ids": [e["id"] for e in payload["events"]],
                }
                atomic(destination, raw)
                atomic(self.root / "revisions" / f"{rev}.meta.json", encoded(meta))
                self.audit("validated", rev)
                atomic(self.root / "previous.json", encoded(heads))
                heads[payload["edition"]] = rev
                require(len(heads) <= 366, "edition_limit")
                self.audit("publication_ready", rev)
                atomic(self.root / "current.json", encoded(heads))
                return meta
            except (SnapshotError, OSError, ValueError, RecursionError) as exc:
                code = (
                    str(exc)
                    if isinstance(exc, SnapshotError)
                    else "publication_io_error"
                )
                self.audit("rejected", code=code)
                raise SnapshotError(code) from None

    def rollback(self, revision):
        require(
            os.getenv("QUORUM_ENABLE_SNAPSHOT_PUBLICATION") == "1",
            "publication_disabled",
        )
        with self.locked():
            payload, meta = self.revision(revision)
            require(
                payload["mode"] == "live" or settings.DEBUG,
                "demo_publication_forbidden",
            )
            heads = self.heads()
            atomic(self.root / "previous.json", encoded(heads))
            heads[payload["edition"]] = revision
            self.audit("rollback_requested", revision)
            atomic(self.root / "current.json", encoded(heads))
            return meta

    def read(self, day="", revision=None):
        if not self.root or not self.root.exists():
            return None, {"status": "pending", "error_code": None}
        fallback = False
        error = None
        for index in ("current.json", "previous.json"):
            try:
                heads = self.heads(index)
                selected = (
                    revision or heads.get(day)
                    if day
                    else revision or (heads[max(heads)] if heads else None)
                )
                if not selected:
                    if fallback:
                        continue
                    return None, {"status": "pending", "error_code": None}
                payload, meta = self.revision(selected)
                require(
                    not day or payload["edition"] == day, "revision_edition_mismatch"
                )
                require(
                    payload["mode"] == "live" or settings.DEBUG,
                    "demo_publication_forbidden",
                )
                state = (
                    "error"
                    if payload["errors"] and not payload["events"]
                    else (
                        "stale"
                        if instant(payload["expires_at"]) <= now()
                        else (
                            "partial"
                            if payload["completeness"] == "partial"
                            else "available"
                        )
                    )
                )
                return payload, {
                    "status": state,
                    "revision": selected,
                    "edition": payload["edition"],
                    "run_id": payload["run_id"],
                    "generated_at": payload["generated_at"],
                    "expires_at": payload["expires_at"],
                    "published_at": meta["published_at"],
                    "source_revision": payload["source_revision"],
                    "previous_revision": payload["parent_revision"],
                    "fallback": fallback,
                    "error_code": error,
                    "mode": payload["mode"],
                }
            except (
                SnapshotError,
                OSError,
                ValueError,
                KeyError,
                TypeError,
                RecursionError,
            ):
                if revision:
                    return None, {
                        "status": "error",
                        "error_code": "revision_unavailable",
                    }
                fallback = True
                error = "current_revision_unavailable"
        return None, {"status": "error", "error_code": error}

    def status(self):
        payload, publication = self.read()
        result = {
            "publication": publication,
            "event_count": len(payload["events"]) if payload else None,
            "validation_failures": None,
            "last_error": None,
            "processing_error": (
                payload["errors"][-1] if payload and payload["errors"] else None
            ),
        }
        if not self.root:
            return result
        try:
            path = self.root / "audit.jsonl"
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                size = os.fstat(stream.fileno()).st_size
                stream.seek(max(0, size - 65536))
                lines = stream.read(65536).splitlines()
                if size > 65536:
                    lines = lines[1:]
            records = [json.loads(line) for line in lines]
            require(all(isinstance(r, dict) for r in records), "invalid_audit_record")
            rejected = [r for r in records if r.get("action") == "rejected"]
            result.update(
                validation_failures=len(rejected),
                last_error=rejected[-1] if rejected else None,
            )
        except (OSError, ValueError):
            pass
        return result
