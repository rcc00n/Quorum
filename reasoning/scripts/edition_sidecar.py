"""Write the provisional sidecar the portal needs to accept a new (non-closed) edition.

    cd reasoning
    python scripts/edition_sidecar.py --snapshot snapshots/_private/<topic>/<date>/v<N>.json \
        --corpus-as-of 2026-10-26T10:30Z --producer-commit <full 40-hex commit> [--out <path>] [--repo <git dir>]

Writes, next to each other and each atomically (temporary file + replace):

    <out>                 the sidecar (default <snapshot>.sidecar.json), UTF-8, stable key order, LF
    <out>.sha256          "<sha256>  <sidecar file name>"
    <snapshot>.sha256     "<sha256>  <snapshot file name>"

The hand-over for one edition is then the snapshot file, its sidecar, both sha256 values and the producer commit:
what the portal's read-only `python manage.py reasoning_snapshot --file --sha256 --sidecar --sidecar-sha256
--producer-commit` validates and `portal_snapshot publish` installs once the gate is open (Issue #2 6411686793,
6412178189). The portal resolves the producer commit in its own checkout, so that commit must be reachable there.

The shape is the provisional ("preview") binding of master's `backend/portal/reasoning_preview.py ›
bind_preview_sidecar`, as Anastasia read it (Issue #2 6411686793):

    {"snapshot": {"sha256", "topic_id", "edition_date", "version", "run_id", "status", "bytes"},
     "provisional": true, "corpus_as_of_utc": "YYYY-MM-DDTHH:MM[:SS]Z", "edition_window_utc": [start, end],
     "producer": {"commit": <40 hex>, "config_sha256": <sha256 of git show <commit>:reasoning/config/reasoning.toml>}}

DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): reasoning writes only this provisional form, never the closed
form (`snapshot.sha256_file_bytes`, `producer.commit_of_the_publishing_process`, the LF/CRLF config pair), and refuses
(exit 2, nothing written) unless `validate_sidecar` passes: a re-implementation of every check of master's
`bind_preview_sidecar` and `reasoning_snapshot` (genuine model output: `fictional` false, a model other than
stand-ins, `model_calls` > 0; producer commit and config hash; the editorial hold on the v4 run) plus the snapshot
envelope those checks read (strict JSON, identity fields, timestamps, edition window, provenance counts). The
portal still validates story, roundup, trace and error content itself. Why: the portal accepts a non-closed edition
only with a hash-bound provisional sidecar; the closed form binds three historical pairs only and attests a closed
edition, which a new run cannot claim. A sidecar that would fail in the portal is refused here, where it is cheap.

DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): `corpus_as_of_utc` is the time of the post-cut dump the run read
(agreed in Issue #2 6412178189). A time after the window end is clamped to min(window.end, generated_at) and said so
on stderr; a time before window.start is refused (that dump cannot hold the edition's documents), and so is a time
after the snapshot's `generated_at` (the run cannot have read a dump that did not exist yet: the input is wrong).
Why: a post-cut dump holds the whole window, so its window end is the honest capture bound the portal accepts
(start <= capture <= min(end, generated_at)); clamping an earlier or a later-than-generation time would invent one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

REPO = Path(__file__).resolve().parents[2]
CONFIG_PATH = "reasoning/config/reasoning.toml"

# Mirrored from master's backend/portal (snapshot_validation.py, reasoning_preview.py, reasoning_snapshot.py).
MAX_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 25
HISTORICAL_V3_SHA256 = "c223bc156b7d80049db24483140f45a1ee065f20106062d69bb249171fa07a30"
GENUINE_V4_SHA256 = "ef231a4f0797c1128869ed5bd69d4d2869771766f634e754aa02dbf375756d79"
HELD_RUN_ID = "2026-10-24-russia-ukraine-war-5"
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+]00:00)")
CAPTURE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,199}")
FULL_COMMIT = re.compile(r"[0-9a-f]{40}")
COMMIT_PREFIX = re.compile(r"^([0-9a-f]{7,40})(?:\s|$)")
SHA256 = re.compile(r"[0-9a-f]{64}")
UNSAFE_CONTENT = re.compile(r"-----BEGIN .*PRIVATE KEY|(?:gh[pousr]_|nvapi-)[A-Za-z0-9_-]{20,}|Bearer [A-Za-z0-9_.-]{20,}")
TOP_REQUIRED = (
    "schema_version", "topic_id", "edition_date", "run_id", "version", "status", "summary", "sources_missing",
    "stories", "roundup", "generated_at", "published_at", "expires_at", "edition_timezone", "window", "provenance",
)
TOP_OPTIONAL = ("bar", "errors", "trace", "summary_source")
PROVENANCE_REQUIRED = ("corpus", "model", "fictional")
PROVENANCE_OPTIONAL = ("fact_checker_model", "model_calls", "answered_by", "model_errors")
IDENTITY_KEYS = ("topic_id", "edition_date", "version", "run_id", "status")
CUT = time(5, 30)

# The provisional form this tool writes, in this order (our contract: exactly these keys, nothing else).
SIDECAR_KEYS = ("snapshot", "provisional", "corpus_as_of_utc", "edition_window_utc", "producer")
BINDING_KEYS = ("sha256",) + IDENTITY_KEYS + ("bytes",)
PRODUCER_KEYS = ("commit", "config_sha256")
CLOSED_FORM_KEYS = ("sha256_file_bytes", "commit_of_the_publishing_process")


class SidecarError(Exception):
    """A refusal: `code` is the portal's code where one exists, `message` says what to fix. Never carries secrets."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.message = message or code


def _require(ok: object, code: str, message: str = "") -> None:
    if not ok:
        raise SidecarError(code, message)


# ---------------------------------------------------------------- portal mirrors: parsing and the snapshot envelope


def strict_json(raw: bytes, what: str) -> Any:
    """`parse_preview_json`: size bound, duplicate keys and non-finite numbers refused, nesting and content bounded."""
    _require(len(raw) <= MAX_BYTES, "payload_too_large", f"{what} is larger than {MAX_BYTES} bytes")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            _require(key not in result, "duplicate_json_key", f"{what} repeats a JSON key")
            result[key] = value
        return result

    def non_finite(_: str) -> Any:
        raise SidecarError("non_finite_number", f"{what} holds NaN or Infinity")

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=non_finite)
    except SidecarError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise SidecarError("invalid_reasoning_json", f"{what} is not valid UTF-8 JSON") from None
    _bounded(value, what)
    return value


def _bounded(value: Any, what: str, depth: int = 0) -> None:
    """`bounded_structure`: depth <= 25, finite floats, no key-, token- or private-key-like strings."""
    _require(depth <= MAX_DEPTH, "excessive_nesting", f"{what} nests deeper than {MAX_DEPTH}")
    if isinstance(value, float):
        _require(math.isfinite(value), "non_finite_number", f"{what} holds a non-finite number")
    if isinstance(value, str):
        _require(not UNSAFE_CONTENT.search(value), "unsafe_public_content", f"{what} holds a key- or token-like string")
    if isinstance(value, dict):
        for child in value.values():
            _bounded(child, what, depth + 1)
    if isinstance(value, list):
        for child in value:
            _bounded(child, what, depth + 1)


def timestamp(value: Any) -> datetime:
    """The portal's `timestamp`: seconds required, optional fraction, Z or +00:00 only."""
    _require(isinstance(value, str) and TIMESTAMP.fullmatch(value), "invalid_reasoning_timestamp",
             f"timestamp {value!r} is not YYYY-MM-DDTHH:MM:SS[.ffffff]Z")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SidecarError("invalid_reasoning_timestamp", f"timestamp {value!r} is not a real instant") from None


def _text(value: Any) -> bool:
    return isinstance(value, str) and len(value) <= 20000


def _keys(value: Any, required: tuple[str, ...], optional: tuple[str, ...], what: str) -> None:
    _require(isinstance(value, dict), "invalid_reasoning_1_0", f"{what} is not a JSON object")
    missing = [k for k in required if k not in value]
    _require(not missing, "missing_reasoning_field", f"{what} lacks {', '.join(missing)}")
    extra = sorted(set(value) - set(required) - set(optional))
    _require(not extra, "unsupported_reasoning_field", f"{what} has unsupported fields {', '.join(extra)}")


def _edition_date_ok(value: Any) -> bool:
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def check_snapshot(raw: bytes) -> dict[str, Any]:
    """The part of `parse_reasoning` the sidecar binds: identity, envelope (timestamps, window, provenance)."""
    p = strict_json(raw, "snapshot")
    _keys(p, TOP_REQUIRED, TOP_OPTIONAL, "snapshot")
    _require(p["schema_version"] == "1.0", "unsupported_reasoning_version", "snapshot schema_version is not 1.0")
    for key in ("topic_id", "run_id"):
        _require(isinstance(p[key], str) and IDENTIFIER.fullmatch(p[key]), "invalid_reasoning_id",
                 f"snapshot {key} is not a portal identifier")
    _require(_edition_date_ok(p["edition_date"]), "invalid_reasoning_date", "snapshot edition_date is not YYYY-MM-DD")
    generated = timestamp(p["generated_at"])
    expires = timestamp(p["expires_at"])
    if p["published_at"] is not None:
        _require(timestamp(p["published_at"]) >= generated, "publication_before_generation",
                 "snapshot published_at precedes generated_at")
    _require(_text(p["edition_timezone"]), "invalid_reasoning_1_0", "snapshot edition_timezone is not text")
    try:
        zone = ZoneInfo(p["edition_timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        raise SidecarError("invalid_edition_timezone", "snapshot edition_timezone is not a known zone") from None
    _keys(p["window"], ("start", "end"), (), "snapshot window")
    start, end = timestamp(p["window"]["start"]), timestamp(p["window"]["end"])
    day = datetime.strptime(p["edition_date"], "%Y-%m-%d").date()
    expected_end = datetime.combine(day, CUT, zone)
    try:
        expected_start = datetime.combine(day - timedelta(days=1), CUT, zone)
    except OverflowError:
        raise SidecarError("invalid_reasoning_date", "snapshot edition_date has no previous day") from None
    _require(start == expected_start and end == expected_end, "inconsistent_edition_window",
             "snapshot window is not 05:30 to 05:30 local in edition_timezone")
    _require(expires > end, "expiry_before_edition_end", "snapshot expires_at is not after the window end")
    prov = p["provenance"]
    _keys(prov, PROVENANCE_REQUIRED, PROVENANCE_OPTIONAL, "snapshot provenance")
    for key in ("corpus", "model"):
        _require(_text(prov[key]), "invalid_reasoning_1_0", f"provenance {key} is not text")
        _require(prov[key], "missing_reasoning_provenance", f"provenance {key} is empty")
    _require(type(prov["fictional"]) is bool, "invalid_reasoning_1_0", "provenance fictional is not a boolean")
    if "fact_checker_model" in prov:
        _require(_text(prov["fact_checker_model"]), "invalid_reasoning_1_0", "provenance fact_checker_model is not text")
        _require(prov["fact_checker_model"], "missing_reasoning_provenance", "provenance fact_checker_model is empty")
    for key in ("model_calls", "model_errors"):
        if key in prov:
            _require(type(prov[key]) is int and 0 <= prov[key] <= 100000, "invalid_model_call_count",
                     f"provenance {key} is not an integer 0..100000")
    if "answered_by" in prov:
        answered = prov["answered_by"]
        _require(isinstance(answered, dict) and len(answered) <= 100, "invalid_answered_by",
                 "provenance answered_by is not an object of at most 100 models")
        for model, count in answered.items():
            _require(_text(model) and model and type(count) is int and 0 < count <= 100000, "invalid_answered_by",
                     "provenance answered_by holds an empty model or a count outside 1..100000")
        if "model_calls" in prov:
            _require(sum(answered.values()) == prov["model_calls"], "inconsistent_model_call_count",
                     "provenance answered_by does not sum to model_calls")
        if "model_errors" in prov:
            _require(answered.get("error", 0) == prov["model_errors"]
                     or (hashlib.sha256(raw).hexdigest() == HISTORICAL_V3_SHA256
                         and answered.get("error") == 61 and prov["model_errors"] == 63),
                     "inconsistent_model_error_count", "provenance answered_by.error differs from model_errors")
    if "model_calls" in prov and "model_errors" in prov:
        _require(prov["model_errors"] <= prov["model_calls"], "inconsistent_model_error_count",
                 "provenance model_errors exceeds model_calls")
    _require(type(p["version"]) is int and p["version"] > 0, "invalid_reasoning_1_0", "snapshot version is not a positive integer")
    _require(p["status"] in ("ok", "partial", "empty"), "invalid_reasoning_1_0", "snapshot status is not ok, partial or empty")
    return p


def genuine_problem(p: dict[str, Any]) -> str | None:
    """`reasoning_snapshot`'s precondition: genuine model output, not a fixture and not stand-ins, with calls."""
    prov = p["provenance"]
    if prov["fictional"] is not False:
        return "the snapshot is fictional (a fixture corpus): only a run on the collected corpus gets a sidecar"
    if prov["model"] == "stand-ins":
        return "the snapshot was answered by stand-ins (a dry run): only a live model run gets a sidecar"
    if not prov.get("model_calls", 0) > 0:
        return "the snapshot records no model call (provenance.model_calls missing or 0)"
    return None


def capture_time(value: Any) -> datetime:
    """The sidecar's capture format, `YYYY-MM-DDTHH:MM[:SS]Z`, as the portal parses it."""
    _require(isinstance(value, str) and CAPTURE.fullmatch(value), "invalid_sidecar",
             f"corpus time {value!r} is not YYYY-MM-DDTHH:MM[:SS]Z")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SidecarError("invalid_sidecar", f"corpus time {value!r} is not a real instant") from None


# ---------------------------------------------------------------- files and git


def read_snapshot_file(path: Path) -> bytes:
    """`read_bounded`: a regular file, not a link, one hard link only, at most MAX_BYTES."""
    try:
        info = os.lstat(path)
    except OSError:
        raise SidecarError("snapshot_unreadable", f"snapshot {path} does not exist or cannot be read") from None
    _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "unsafe_snapshot_file",
             f"snapshot {path} is not a regular file with a single link (a symlink, directory or hard link)")
    _require(info.st_size <= MAX_BYTES, "payload_too_large", f"snapshot {path} is larger than {MAX_BYTES} bytes")
    try:
        raw = Path(path).read_bytes()
    except OSError:
        raise SidecarError("snapshot_unreadable", f"snapshot {path} cannot be read") from None
    _require(len(raw) <= MAX_BYTES, "payload_too_large", f"snapshot {path} is larger than {MAX_BYTES} bytes")
    return raw


def _git(repo: Path, *args: str) -> bytes | None:
    try:
        return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def commit_known(repo: Path, commit: str) -> bool:
    return _git(repo, "cat-file", "-e", f"{commit}^{{commit}}") is not None


def config_sha256_at(repo: Path, commit: str) -> str | None:
    """sha256 of the config blob exactly as the portal reads it: `git show <commit>:reasoning/config/reasoning.toml`."""
    blob = _git(repo, "show", f"{commit}:{CONFIG_PATH}")
    return None if blob is None else hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------- the sidecar


def resolve_corpus_as_of(value: str, p: dict[str, Any]) -> tuple[str, str | None]:
    """(corpus_as_of_utc, a note for stderr or None). See the second DECISION in the module docstring."""
    captured = capture_time(value)
    start, end = timestamp(p["window"]["start"]), timestamp(p["window"]["end"])
    generated = timestamp(p["generated_at"])
    _require(captured >= start, "corpus_before_window",
             f"corpus time {value} is before the edition window start {p['window']['start']}: "
             "that dump cannot hold this edition's documents")
    _require(captured <= generated, "corpus_after_generation",
             f"corpus time {value} is after the snapshot's generated_at {p['generated_at']}: "
             "the run cannot have read that dump; pass the time of the dump the run read")
    if captured <= end:
        return value, None
    # whole seconds, floored: the capture format has no fraction, and a floor never passes the bound
    clamped = min(end, generated).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    note = (f"corpus time {value} is after the edition window end {p['window']['end']}; corpus_as_of_utc "
            f"clamped to min(window.end, generated_at) = {clamped}")
    return clamped, note


def build_sidecar(snapshot_raw: bytes, p: dict[str, Any], corpus_as_of_utc: str, producer_commit: str,
                  config_sha256: str) -> dict[str, Any]:
    """The provisional sidecar, keys in the order of SIDECAR_KEYS / BINDING_KEYS / PRODUCER_KEYS."""
    binding = {"sha256": hashlib.sha256(snapshot_raw).hexdigest()}
    binding.update((key, p[key]) for key in IDENTITY_KEYS)  # values (and so JSON types) taken from the snapshot itself
    binding["bytes"] = len(snapshot_raw)
    return {
        "snapshot": binding,
        "provisional": True,
        "corpus_as_of_utc": corpus_as_of_utc,
        "edition_window_utc": [p["window"]["start"], p["window"]["end"]],
        "producer": {"commit": producer_commit, "config_sha256": config_sha256},
    }


def serialize(sidecar: dict[str, Any]) -> bytes:
    return (json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def validate_sidecar(sidecar: bytes | dict[str, Any], snapshot_path: Path | str, producer_commit: str,
                     repo: Path | str = REPO) -> dict[str, Any]:
    """Re-implements the portal's acceptance checks for a provisional sidecar; raises SidecarError on the first failure.

    Order and codes follow master's `reasoning_snapshot.Command.handle` and `bind_preview_sidecar` (inside the latter
    the portal reports every failure as `invalid_sidecar`; the inner code is kept here because it says what to fix).
    Checks marked "ours" are this tool's own contract on top of the portal's: exactly the provisional keys, `bytes`
    present, `provisional` true, the full commit, the commit present in the repository. Returns the two hashes.
    """
    repo = Path(repo)
    # reasoning_snapshot: the producer commit is full 40 hex; both files are bounded regular files
    _require(isinstance(producer_commit, str) and FULL_COMMIT.fullmatch(producer_commit),
             "expected_full_producer_commit_required", "the producer commit must be the full 40-hex lowercase commit")
    snapshot_raw = read_snapshot_file(Path(snapshot_path))
    raw = sidecar if isinstance(sidecar, (bytes, bytearray)) else serialize(sidecar)
    raw = bytes(raw)
    _require(len(raw) <= MAX_BYTES, "payload_too_large", f"sidecar is larger than {MAX_BYTES} bytes")
    snapshot_sha256 = hashlib.sha256(snapshot_raw).hexdigest()
    # present_reasoning(raw) -> parse_reasoning: the snapshot envelope
    p = check_snapshot(snapshot_raw)
    # bind_preview_sidecar
    s = strict_json(raw, "sidecar")
    try:
        _require(isinstance(s, dict), "invalid_sidecar", "sidecar is not a JSON object")
        closed = [k for k in CLOSED_FORM_KEYS if isinstance(s.get("snapshot"), dict) and k in s["snapshot"]
                  or isinstance(s.get("producer"), dict) and k in s["producer"]]
        _require(not closed, "closed_form_not_produced",
                 f"sidecar carries closed-form keys {', '.join(closed)}: reasoning writes the provisional form only")
        binding = s["snapshot"]
        _require(isinstance(binding, dict), "invalid_sidecar", "sidecar snapshot is not an object")
        _require(binding["sha256"] == snapshot_sha256, "sidecar_snapshot_mismatch",
                 "sidecar snapshot.sha256 is not the sha256 of the snapshot file")
        for key in IDENTITY_KEYS:
            expected = p[key]
            _require(type(binding[key]) is type(expected) and binding[key] == expected, "sidecar_snapshot_mismatch",
                     f"sidecar snapshot.{key} differs from the snapshot's own {key} (value or JSON type)")
        _require("bytes" in binding, "sidecar_size_mismatch", "sidecar snapshot.bytes is missing")  # ours
        _require(type(binding["bytes"]) is int and binding["bytes"] == len(snapshot_raw), "sidecar_size_mismatch",
                 "sidecar snapshot.bytes is not the snapshot file size")
        _require(type(s["provisional"]) is bool, "invalid_sidecar", "sidecar provisional is not a boolean")
        snapshot_provisional = True if snapshot_sha256 == HISTORICAL_V3_SHA256 else None
        _require(snapshot_provisional is not True or s["provisional"], "sidecar_provisional_mismatch",
                 "the snapshot is provisional, so the sidecar must say provisional true")
        _require(s["provisional"] is True, "provisional_required", "this tool writes provisional sidecars only")  # ours
        captured = capture_time(s["corpus_as_of_utc"])
        bound = min(timestamp(p["window"]["end"]), timestamp(p["generated_at"]))
        _require(timestamp(p["window"]["start"]) <= captured <= bound, "sidecar_capture_outside_window",
                 "sidecar corpus_as_of_utc is not between window.start and min(window.end, generated_at)")
        _require(s["edition_window_utc"] == [p["window"][k] for k in ("start", "end")], "sidecar_window_mismatch",
                 "sidecar edition_window_utc is not [window.start, window.end] verbatim")
        # ours: exactly the provisional keys, nothing private or extra
        for value, keys, what in ((s, SIDECAR_KEYS, "sidecar"), (binding, BINDING_KEYS, "sidecar snapshot"),
                                  (s.get("producer"), PRODUCER_KEYS, "sidecar producer")):
            _require(isinstance(value, dict) and list(value) == list(keys), "unexpected_sidecar_field",
                     f"{what} keys are not exactly {', '.join(keys)} in that order")
        # reasoning_snapshot: genuine model output
        problem = genuine_problem(p)
        _require(problem is None, "genuine_model_output_required", problem or "")
        # reasoning_snapshot: producer commit and config (non-closed branch)
        producer = s["producer"]
        prefix = COMMIT_PREFIX.match(producer["commit"])
        _require(prefix is not None and producer_commit.startswith(prefix[1]), "producer_commit_mismatch",
                 "sidecar producer.commit is not a prefix of the producer commit")
        _require(producer["commit"] == producer_commit, "producer_commit_mismatch",
                 "sidecar producer.commit is not the full producer commit")  # ours
        declared = producer["config_sha256"]
        _require(isinstance(declared, str) and SHA256.fullmatch(declared), "invalid_config_sha256",
                 "sidecar producer.config_sha256 is not 64 lowercase hex")
        _require(commit_known(repo, producer_commit), "producer_commit_unknown",
                 f"commit {producer_commit} is not in the repository at {repo}")  # ours
        actual = config_sha256_at(repo, producer_commit)
        _require(actual is not None, "producer_config_unavailable",
                 f"{CONFIG_PATH} does not exist at commit {producer_commit}")
        _require(actual == declared, "producer_config_mismatch",
                 f"sidecar producer.config_sha256 is not the sha256 of {CONFIG_PATH} at {producer_commit}")
        # reasoning_snapshot: artifact_review_issues (the editorial hold on the original v4)
        _require(not (snapshot_sha256 == GENUINE_V4_SHA256 or p["run_id"] == HELD_RUN_ID), "impact_score_review_required",
                 "this snapshot is under the portal's editorial impact hold")
    except (KeyError, TypeError, ValueError):
        raise SidecarError("invalid_sidecar", "sidecar lacks a required field or holds a wrong type") from None
    return {"snapshot_sha256": snapshot_sha256, "sidecar_sha256": hashlib.sha256(raw).hexdigest()}


# ---------------------------------------------------------------- writing


def _same(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def write_atomically(files: list[tuple[Path, bytes]]) -> None:
    """Every file goes to a temporary file in its own directory first; only when all exist are they replaced in."""
    temps: list[tuple[str, Path]] = []
    try:
        for path, data in files:
            fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
            temps.append((tmp, path))
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        for tmp, path in temps:
            os.replace(tmp, path)
    finally:
        for tmp, _ in temps:
            if os.path.exists(tmp):
                os.unlink(tmp)


def hash_line(data: bytes, name: str) -> bytes:
    return f"{hashlib.sha256(data).hexdigest()}  {name}\n".encode("utf-8")


def make(snapshot: Path, corpus_as_of: str, producer_commit: str, out: Path | None, repo: Path) -> dict[str, Any]:
    """Checks every precondition, builds and validates the sidecar, then writes the three files. Raises SidecarError."""
    _require(isinstance(producer_commit, str) and FULL_COMMIT.fullmatch(producer_commit),
             "expected_full_producer_commit_required",
             f"--producer-commit {producer_commit!r} is not a full 40-hex lowercase commit")
    raw = read_snapshot_file(snapshot)
    p = check_snapshot(raw)
    problem = genuine_problem(p)
    _require(problem is None, "genuine_model_output_required", problem or "")
    _require(commit_known(repo, producer_commit), "producer_commit_unknown",
             f"commit {producer_commit} is not in the repository at {repo}")
    config_sha256 = config_sha256_at(repo, producer_commit)
    _require(config_sha256 is not None, "producer_config_unavailable",
             f"{CONFIG_PATH} does not exist at commit {producer_commit}")
    corpus_as_of_utc, note = resolve_corpus_as_of(corpus_as_of, p)
    out = Path(out) if out else snapshot.with_name(snapshot.name + ".sidecar.json")
    out_hash = out.with_name(out.name + ".sha256")
    snapshot_hash = snapshot.with_name(snapshot.name + ".sha256")
    paths = [snapshot, out, out_hash, snapshot_hash]
    _require(all(not _same(a, b) for i, a in enumerate(paths) for b in paths[i + 1:]), "out_path_conflict",
             f"--out {out} would overwrite the snapshot or a hash file")
    _require(out.parent.is_dir(), "out_dir_missing", f"the directory of --out {out} does not exist")
    data = serialize(build_sidecar(raw, p, corpus_as_of_utc, producer_commit, config_sha256))
    hashes = validate_sidecar(data, snapshot, producer_commit, repo)
    _require(read_snapshot_file(snapshot) == raw, "snapshot_changed", f"snapshot {snapshot} changed while it was read")
    try:
        write_atomically([(out, data), (out_hash, hash_line(data, out.name)), (snapshot_hash, hash_line(raw, snapshot.name))])
    except OSError as exc:
        raise SidecarError("write_failed", f"could not write the sidecar files: {exc.strerror or type(exc).__name__}") from None
    _require(hashlib.sha256(out.read_bytes()).hexdigest() == hashes["sidecar_sha256"], "write_failed",
             f"sidecar {out} on disk differs from the validated bytes")
    return {**hashes, "sidecar": out, "sidecar_hash_file": out_hash, "snapshot_hash_file": snapshot_hash,
            "corpus_as_of_utc": corpus_as_of_utc, "note": note}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", required=True, type=Path, help="the snapshot file the run wrote")
    parser.add_argument("--corpus-as-of", required=True,
                        help="time of the post-cut dump the run read, YYYY-MM-DDTHH:MM[:SS]Z")
    parser.add_argument("--producer-commit", required=True, help="the full 40-hex commit the run was produced by")
    parser.add_argument("--out", type=Path, help="sidecar path (default <snapshot>.sidecar.json)")
    parser.add_argument("--repo", type=Path, default=REPO, help="git checkout holding the commit (default: this one)")
    args = parser.parse_args(argv)
    try:
        result = make(args.snapshot, args.corpus_as_of, args.producer_commit, args.out, args.repo)
    except SidecarError as exc:
        print(f"edition_sidecar: refused ({exc.code}): {exc.message}; nothing written", file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError) as exc:  # the portal's catch-all code, no payload values
        print(f"edition_sidecar: refused (acceptance_input_unavailable_or_invalid): {type(exc).__name__}; "
              "nothing written", file=sys.stderr)
        return 2
    if result["note"]:
        print(f"edition_sidecar: {result['note']}", file=sys.stderr)
    print(f"sidecar {result['sidecar']}  sha256 {result['sidecar_sha256']}")
    print(f"snapshot {args.snapshot}  sha256 {result['snapshot_sha256']}")
    print(f"corpus_as_of_utc {result['corpus_as_of_utc']}  producer {args.producer_commit}")
    print("portal check: python manage.py reasoning_snapshot --file <snapshot> --sha256 <snapshot sha256> "
          "--sidecar <sidecar> --sidecar-sha256 <sidecar sha256> --producer-commit <producer>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
