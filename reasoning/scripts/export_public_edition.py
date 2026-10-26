"""Copy an installed edition's snapshot into the public samples, with a run summary that holds counts only.

    cd reasoning
    python -X utf8 scripts/export_public_edition.py snapshots/_private/<topic>/<date>/v<N>.json \
        --sha256 snapshots/_private/<topic>/<date>/v<N>.json.sha256 \
        --ledger snapshots/_private/<topic>/<date>/v<N>.ledger.json \
        --out ../docs/examples/editions [--sidecar <v<N>.json.sidecar.json>] [--replace] [--repo <git dir>]

Writes, each atomically (temporary file + replace):

    <out>/<edition_date>/<topic_id>.json               the snapshot, byte for byte
    <out>/<edition_date>/<topic_id>.run-summary.json   counts only (RUN_SUMMARY_KEYS), UTF-8, stable key order, LF

Run it only once the edition is installed on the site (docs/DECISIONS.md › Demo for the judges, Public edition
samples). Before anything is written it checks, and refuses (exit 2, nothing written) on the first failure:

  - the snapshot's sha256 equals the hand-over hash in --sha256 (a sha256sum line naming the snapshot file, or a bare
    hash);
  - the repository's own snapshot checks pass: scripts/edition_sidecar.py `check_snapshot` (the portal's
    `parse_reasoning`, mirrored) and `genuine_problem` (genuine model output, not a fixture or stand-ins);
  - the sidecar (default <snapshot>.sidecar.json) passes `validate_sidecar` for this snapshot (it binds the snapshot's
    sha256; its producer commit and config hash are checked in --repo), and its own .sha256 beside it, when present,
    matches; the sidecar gives `producer_commit` and `corpus_as_of_utc`;
  - the ledger is this snapshot's: the same topic, date, version and run id, and its rows give the snapshot's
    provenance counts (model_calls, answered_by, model_errors);
  - no string of the snapshot holds a secret-shaped value, a value of a key/token variable (exported or in the repo's
    .env), a receipt id, request key or reply hash of the ledger, or a local path (decision at unsafe_strings);
  - the summary holds exactly the allowlisted fields with the allowlisted value shapes, and none of the ledger's
    receipt ids, request keys, reply hashes, error texts or other private strings (decisions at check_allowlist);
  - neither destination exists, unless --replace.

The ledger (*.ledger.json), the call journals and the logs stay private: this tool reads the ledger and writes
counts derived from it, never a row of it.

DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): the run summary holds counts only: calls in total and by node,
lane, answering model and requested model route, failed calls, route_substituted, lane_unverified, calls with H-MEM
memories injected, cache hits, Meterless receipts (a count), memory trace rows by kind, plus the identity of the
snapshot (topic_id, edition_date, version, run_id, status), its `generated_at` and sha256, the producer commit,
`corpus_as_of_utc` and `provider_route` (which route answered, read from the rows' Meterless receipt evidence). Why:
Yelysei's D2 (2026-10-26); `generated_at` is the snapshot's own, so a rerun of the export writes the same bytes;
`provider_route` and the derivation of `by_node` from the ledger's task and lane (the ledger has no node field) are
Claude Code's, to confirm.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
REASONING = SCRIPTS.parent
for path in (str(SCRIPTS), str(REASONING)):
    if path not in sys.path:
        sys.path.insert(0, path)

import edition_sidecar as es  # noqa: E402  the repository's own snapshot and sidecar checks
from run_editions import SECRET_NAME, read_env_file, topic_id_problem  # noqa: E402

REPO = es.REPO
DEFAULT_ENV_FILE = REPO / ".env"  # secret values are read from it only to make sure none is published
SCHEMA = "quorum.run-summary.v1"
LEDGER_MAX_BYTES = 64 * 1024 * 1024
HASH_FILE_MAX_BYTES = 4096
MIN_SECRET_CHARS = 8

# the graph's nodes (graph.py) and the lanes (llm._route)
NODES = ("plan", "cluster", "score_importance", "extract_claims", "research", "verify", "fact_check", "adjudicate",
         "review_disputed", "escalate", "frame", "write", "critique", "roundup", "publish")
LANES = ("default", "fact_checker", "reviewer")
OTHER = "other"
# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a ledger row's node is read from its task (nodes/*.py:
# llm.json_task calls) and, for the stance tasks, its lane: research asks on the default lane, fact_check on the
# fact_checker lane; an unknown task or lane counts as "other". Why: the ledger keeps task and lane, not the node.
TASK_NODE = {"event_key": "cluster", "merge_confirm": "cluster", "rubric": "score_importance",
             "extract_claims": "extract_claims", "review_disputed": "review_disputed", "frame": "frame",
             "write": "write", "roundup_line": "roundup", "summary": "publish"}
STANCE_TASKS = ("stance", "stance_document")
MEMORY_KINDS = ("stored", "recalled", "write_unavailable", "recall_unavailable", OTHER)
PROVIDER_ROUTES = ("meterless", "nvidia", "mixed", "unknown")
MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,99}")
EDITION_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
HASH_LINE = re.compile(r"([0-9a-f]{64})(?:[ ]\*?|  )?(.*)")

RUN_SUMMARY_KEYS = ("schema", "topic_id", "edition_date", "version", "run_id", "status", "generated_at",
                    "snapshot_sha256", "producer_commit", "corpus_as_of_utc", "provider_route", "calls",
                    "route_substituted", "lane_unverified", "hmem_injected", "cache_hits", "meterless_receipts",
                    "memory_trace_rows")
CALLS_KEYS = ("total", "failed", "by_node", "by_lane", "by_model", "by_route")
COUNT_KEYS = ("route_substituted", "lane_unverified", "hmem_injected", "cache_hits", "meterless_receipts")
# ledger fields whose values may appear in the summary (as count keys or identity); every other string is private
LEDGER_PUBLIC_FIELDS = ("task", "lane", "route", "served", "answered_model", "run_id", "finish_reason")
LEDGER_ID_FIELDS = ("receipt_id", "request_key", "reply_sha256")  # never in the summary, nor in the snapshot


class ExportError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


def _require(ok: object, code: str, message: str) -> None:
    if not ok:
        raise ExportError(code, message)


# ---------------------------------------------------------------- inputs


def read_bounded(path: Path, limit: int, what: str) -> bytes:
    """A regular file (not a link), at most `limit` bytes."""
    try:
        info = os.lstat(path)
    except OSError:
        raise ExportError(f"{what}_unreadable", f"{what} {path} does not exist or cannot be read") from None
    _require(stat.S_ISREG(info.st_mode), f"unsafe_{what}_file", f"{what} {path} is not a regular file")
    _require(info.st_size <= limit, f"{what}_too_large", f"{what} {path} is larger than {limit} bytes")
    try:
        raw = Path(path).read_bytes()
    except OSError:
        raise ExportError(f"{what}_unreadable", f"{what} {path} cannot be read") from None
    _require(len(raw) <= limit, f"{what}_too_large", f"{what} {path} is larger than {limit} bytes")
    return raw


def hash_of_file(path: Path, expected_name: str, what: str) -> str:
    """The sha256 in a sha256sum line ("<64 hex>  <name>"; the name, when given, must be `expected_name`) or a bare
    hash, one line."""
    raw = read_bounded(path, HASH_FILE_MAX_BYTES, what)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ExportError("invalid_hash_file", f"{what} {path} is not UTF-8") from None
    lines = [line for line in text.splitlines() if line.strip()]
    _require(len(lines) == 1, "invalid_hash_file", f"{what} {path} does not hold exactly one hash line")
    m = HASH_LINE.fullmatch(lines[0].strip())
    _require(m is not None, "invalid_hash_file", f"{what} {path} is not a sha256sum line")
    name = m.group(2).strip()
    _require(not name or name == expected_name, "hash_file_names_another_file",
             f"{what} {path} names another file than {expected_name}")
    return m.group(1)


def load_ledger(path: Path) -> dict[str, Any]:
    raw = read_bounded(path, LEDGER_MAX_BYTES, "ledger")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            _require(key not in out, "invalid_ledger", "the ledger repeats a JSON key")
            out[key] = value
        return out

    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ExportError("invalid_ledger", f"ledger {path} is not valid UTF-8 JSON") from None
    _require(isinstance(doc, dict) and isinstance(doc.get("calls"), list)
             and all(isinstance(row, dict) for row in doc["calls"]),
             "invalid_ledger", f"ledger {path} is not an object with a list of call rows")
    return doc


def check_ledger(ledger: dict[str, Any], p: dict[str, Any]) -> None:
    """The ledger is this snapshot's: identity and the provenance counts the snapshot was built from."""
    for key in ("topic_id", "edition_date", "version", "run_id"):
        _require(ledger.get(key) == p[key] and type(ledger.get(key)) is type(p[key]), "ledger_mismatch",
                 f"the ledger's {key} differs from the snapshot's: it is another run's ledger")
    calls = ledger["calls"]
    prov = p["provenance"]
    if "model_calls" in prov:
        _require(len(calls) == prov["model_calls"], "ledger_mismatch",
                 "the ledger's row count differs from the snapshot's provenance.model_calls")
    if "answered_by" in prov:
        _require(dict(Counter(str(row.get("served")) for row in calls)) == prov["answered_by"], "ledger_mismatch",
                 "the ledger's answering models differ from the snapshot's provenance.answered_by")
    if "model_errors" in prov:
        _require(sum(1 for row in calls if row.get("error")) == prov["model_errors"], "ledger_mismatch",
                 "the ledger's failed rows differ from the snapshot's provenance.model_errors")


def secret_values(env_file: Path | None) -> set[str]:
    """Values of key/token/secret/password variables, exported or in the repo's .env, at least MIN_SECRET_CHARS long:
    compared against what would be published, never printed."""
    values: set[str] = set()
    for source in (read_env_file(env_file) if env_file else {}, os.environ):
        values |= {v.strip() for n, v in source.items() if SECRET_NAME.search(n) and isinstance(v, str)
                   and len(v.strip()) >= MIN_SECRET_CHARS}
    return values


def ledger_ids(calls: list[dict[str, Any]]) -> set[str]:
    return {row[k] for row in calls for k in LEDGER_ID_FIELDS if isinstance(row.get(k), str) and len(row[k]) >= MIN_SECRET_CHARS}


def ledger_private_strings(calls: list[dict[str, Any]]) -> set[str]:
    """Every string the ledger holds outside LEDGER_PUBLIC_FIELDS (receipt ids, request keys, reply hashes, error texts,
    rate headers, ...), at least MIN_SECRET_CHARS long."""
    found: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, str):
            if len(value) >= MIN_SECRET_CHARS:
                found.add(value)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for row in calls:
        for key, value in row.items():
            if key not in LEDGER_PUBLIC_FIELDS:
                walk(value)
    return found


# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): the export refuses a snapshot any of whose strings holds a
# secret-shaped value (edition_sidecar.UNSAFE_CONTENT), a value of a key/token variable, a receipt id, request key or
# reply hash of its ledger, or a local path (a drive path such as C:\ or D:/, a UNC path, file:, or /home/, /Users/,
# /root/ standing alone); it names the field, never the text. Why: the snapshot is copied byte for byte, so nothing can
# be redacted, and its `errors[].message` keeps raw diagnostics (reasoning/README.md › Public failure projection, the
# reason that note kept snapshot files private); refusing leaves the decision to a person. Proposed by Claude Code.
LOCAL_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]|\\\\[A-Za-z0-9._$-]+\\|\bfile:/|(?<![\w.:/~-])/(?:home|Users|root)/")


def unsafe_strings(value: Any, deny: set[str], where: str = "snapshot") -> list[str]:
    """The paths (snapshot.errors[0].message, ...) of strings that must not be published."""
    found: list[str] = []
    if isinstance(value, str):
        if es.UNSAFE_CONTENT.search(value) or LOCAL_PATH.search(value) or any(d in value for d in deny):
            found.append(where)
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and (LOCAL_PATH.search(key) or any(d in key for d in deny)):
                found.append(f"{where} (a key)")
            found.extend(unsafe_strings(item, deny, f"{where}.{key}"))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            found.extend(unsafe_strings(item, deny, f"{where}[{i}]"))
    return found


# ---------------------------------------------------------------- the summary


def node_of(row: dict[str, Any]) -> str:
    task, lane = row.get("task"), row.get("lane")
    if task in STANCE_TASKS:
        return {"default": "research", "fact_checker": "fact_check"}.get(lane, OTHER)
    return TASK_NODE.get(task, OTHER)


def _id_key(value: Any) -> str:
    return value if isinstance(value, str) and MODEL_ID.fullmatch(value) and not es.UNSAFE_CONTENT.search(value) else OTHER


def _counts(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items(), key=lambda kv: (-kv[1], kv[0])))


def hmem_injected(row: dict[str, Any]) -> bool:
    count = row.get("receipt_hmem_injected")
    return bool(row.get("hmem_rejected") or row.get("hmem_unreadable")) or (count is not None and (type(count) is not int or count > 0))


def provider_route(calls: list[dict[str, Any]]) -> str:
    """meterless: every row that got a response carries Meterless receipt evidence (an H-MEM count or a receipt id);
    nvidia: none does; mixed: some do; unknown: no row got a response."""
    answered = [row for row in calls if type(row.get("http_status")) is int]
    if not answered:
        return "unknown"
    marked = sum(1 for row in answered if "receipt_hmem_injected" in row or row.get("receipt_id"))
    return "meterless" if marked == len(answered) else ("nvidia" if marked == 0 else "mixed")


def memory_kind(decision: Any) -> str:
    text = decision if isinstance(decision, str) else ""
    if text.startswith("stored "):
        return "stored"
    if text.startswith("recalled "):
        return "recalled"
    return {"memory write unavailable": "write_unavailable", "memory recall unavailable": "recall_unavailable"}.get(text, OTHER)


def build_summary(p: dict[str, Any], calls: list[dict[str, Any]], snapshot_sha256: str, producer_commit: str,
                  corpus_as_of_utc: str) -> dict[str, Any]:
    memory = Counter(memory_kind(t.get("decision")) for t in p.get("trace") or [] if isinstance(t, dict) and t.get("node") == "memory")
    return {
        "schema": SCHEMA,
        "topic_id": p["topic_id"],
        "edition_date": p["edition_date"],
        "version": p["version"],
        "run_id": p["run_id"],
        "status": p["status"],
        "generated_at": p["generated_at"],
        "snapshot_sha256": snapshot_sha256,
        "producer_commit": producer_commit,
        "corpus_as_of_utc": corpus_as_of_utc,
        "provider_route": provider_route(calls),
        "calls": {
            "total": len(calls),
            "failed": sum(1 for row in calls if row.get("error")),
            "by_node": _counts([node_of(row) for row in calls]),
            "by_lane": _counts([row.get("lane") if row.get("lane") in LANES else OTHER for row in calls]),
            "by_model": _counts([_id_key(row.get("served")) for row in calls]),
            "by_route": _counts([_id_key(row.get("route")) for row in calls]),
        },
        "route_substituted": sum(1 for row in calls if row.get("route_substituted")),
        "lane_unverified": sum(1 for row in calls if row.get("lane_unverified")),
        "hmem_injected": sum(1 for row in calls if hmem_injected(row)),
        "cache_hits": sum(1 for row in calls if row.get("cache_refused") or row.get("receipt_from_cache") is True),
        "meterless_receipts": sum(1 for row in calls if isinstance(row.get("receipt_id"), str) and row["receipt_id"]),
        "memory_trace_rows": {kind: memory.get(kind, 0) for kind in MEMORY_KINDS},
    }


def _count(value: Any) -> bool:
    return type(value) is int and value >= 0


def _count_map(value: Any, keys: tuple[str, ...] | None) -> bool:
    return isinstance(value, dict) and all(
        isinstance(k, str) and (k in keys if keys is not None else (k == OTHER or MODEL_ID.fullmatch(k) is not None))
        and _count(v) for k, v in value.items())


def check_allowlist(summary: Any, private: set[str]) -> None:
    """The run summary holds exactly RUN_SUMMARY_KEYS, each of its allowed shape, and no private string.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): the summary is checked before it is written: exactly the
    allowlisted keys in order, identity and hashes matching their formats, every other value a non-negative integer or
    a map of counts whose keys are a node, a lane, a memory kind or a model id, and its serialized text holds none of
    the ledger's private strings (receipt ids, request keys, reply hashes, error texts, rate headers) or key/token
    values. Why: D2 (Yelysei, 2026-10-26): never a receipt id, prompt, reply, request key, page text or token in the
    public summary; an allowlist fails closed when a new field is added by mistake."""
    _require(isinstance(summary, dict) and list(summary) == list(RUN_SUMMARY_KEYS), "summary_not_allowlisted",
             "the run summary's keys are not exactly the allowlisted ones")
    checks = {
        "schema": lambda v: v == SCHEMA,
        "topic_id": lambda v: isinstance(v, str) and topic_id_problem(v) is None,
        "edition_date": lambda v: isinstance(v, str) and EDITION_DATE.fullmatch(v) is not None,
        "version": lambda v: type(v) is int and v > 0,
        "run_id": lambda v: isinstance(v, str) and es.IDENTIFIER.fullmatch(v) is not None,
        "status": lambda v: v in ("ok", "partial", "empty"),
        "generated_at": lambda v: isinstance(v, str) and es.TIMESTAMP.fullmatch(v) is not None,
        "snapshot_sha256": lambda v: isinstance(v, str) and es.SHA256.fullmatch(v) is not None,
        "producer_commit": lambda v: isinstance(v, str) and es.FULL_COMMIT.fullmatch(v) is not None,
        "corpus_as_of_utc": lambda v: isinstance(v, str) and es.CAPTURE.fullmatch(v) is not None,
        "provider_route": lambda v: v in PROVIDER_ROUTES,
        "memory_trace_rows": lambda v: isinstance(v, dict) and list(v) == list(MEMORY_KINDS) and all(_count(x) for x in v.values()),
        "calls": lambda v: (isinstance(v, dict) and list(v) == list(CALLS_KEYS) and _count(v["total"]) and _count(v["failed"])
                            and _count_map(v["by_node"], NODES + (OTHER,)) and _count_map(v["by_lane"], LANES + (OTHER,))
                            and _count_map(v["by_model"], None) and _count_map(v["by_route"], None)),
    }
    checks.update({key: _count for key in COUNT_KEYS})
    for key in RUN_SUMMARY_KEYS:
        _require(checks[key](summary[key]), "summary_not_allowlisted", f"the run summary's {key} is not of its allowed shape")
    text = serialize(summary).decode("utf-8")
    _require(not es.UNSAFE_CONTENT.search(text) and not any(s in text for s in private), "summary_leaks_private_data",
             "the run summary holds a private string of the ledger or a key/token value")


def serialize(summary: dict[str, Any]) -> bytes:
    return (json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


# ---------------------------------------------------------------- the export


def _inside(child: Path, parent: Path) -> bool:
    child, parent = child.resolve(), parent.resolve()
    return child == parent or parent in child.parents


def export(snapshot: Path, sha256_file: Path, ledger_file: Path, out: Path, sidecar: Path | None = None,
           replace: bool = False, repo: Path = REPO, env_file: Path | None = None) -> dict[str, Any]:
    """Checks everything, then writes the two files. Raises ExportError (or edition_sidecar.SidecarError)."""
    raw = es.read_snapshot_file(snapshot)
    sha = hashlib.sha256(raw).hexdigest()
    _require(hash_of_file(sha256_file, snapshot.name, "hash file") == sha, "snapshot_hash_mismatch",
             f"the snapshot's sha256 is not the hand-over hash in {sha256_file}")
    p = es.check_snapshot(raw)
    problem = es.genuine_problem(p)
    _require(problem is None, "genuine_model_output_required", problem or "")
    _require(topic_id_problem(p["topic_id"]) is None, "invalid_topic_id",
             "the snapshot's topic_id cannot be a file name in the public folder")

    sidecar = sidecar or snapshot.with_name(snapshot.name + ".sidecar.json")
    sidecar_raw = read_bounded(sidecar, es.MAX_BYTES, "sidecar")
    side_hash = sidecar.with_name(sidecar.name + ".sha256")
    if side_hash.exists():
        _require(hash_of_file(side_hash, sidecar.name, "sidecar hash file") == hashlib.sha256(sidecar_raw).hexdigest(),
                 "sidecar_hash_mismatch", f"the sidecar's sha256 is not the one in {side_hash}")
    s = es.strict_json(sidecar_raw, "sidecar")
    try:
        producer_commit = s["producer"]["commit"]
        corpus_as_of_utc = s["corpus_as_of_utc"]
    except (KeyError, TypeError):
        raise ExportError("invalid_sidecar", "the sidecar lacks producer.commit or corpus_as_of_utc") from None
    es.validate_sidecar(sidecar_raw, snapshot, producer_commit, repo)  # binds this snapshot's sha256

    ledger = load_ledger(ledger_file)
    check_ledger(ledger, p)
    calls = ledger["calls"]
    secrets = secret_values(env_file)
    bad = unsafe_strings(p, secrets | ledger_ids(calls))
    _require(not bad, "unsafe_snapshot_content",
             f"the snapshot cannot be published byte for byte: {', '.join(bad[:5])}{' …' if len(bad) > 5 else ''} hold "
             "a secret-shaped value, a key/token value, a ledger id or a local path")

    summary = build_summary(p, calls, sha, producer_commit, corpus_as_of_utc)
    check_allowlist(summary, secrets | ledger_private_strings(calls))
    data = serialize(summary)

    where = snapshot.resolve()
    if where.parent.name == p["edition_date"] and where.parent.parent.name == p["topic_id"]:  # <root>/<topic>/<date>/v<N>.json
        _require(not _inside(out, where.parents[2]), "out_inside_private_store",
                 f"--out {out} is inside the private snapshot store; point it at docs/examples/editions")
    day = out / p["edition_date"]
    targets = [day / f"{p['topic_id']}.json", day / f"{p['topic_id']}.run-summary.json"]
    existing = [t for t in targets if t.exists()]
    _require(not existing or replace, "destination_exists",
             f"{', '.join(map(str, existing))} already exist: pass --replace to overwrite")
    _require(es.read_snapshot_file(snapshot) == raw, "snapshot_changed", f"snapshot {snapshot} changed while it was read")
    day.mkdir(parents=True, exist_ok=True)
    replaced: list[Path] = []
    try:
        es.write_atomically([(targets[0], raw), (targets[1], data)], replaced)
    except OSError as exc:
        undone = es._undo_write(replaced, targets) if replaced else "nothing written"
        raise ExportError("write_failed", f"could not write the public files ({exc.strerror or type(exc).__name__}); {undone}") from None
    if hashlib.sha256(targets[0].read_bytes()).hexdigest() != sha:  # both are replaced in: remove them again
        raise ExportError("write_failed", f"{targets[0]} on disk differs from the snapshot; {es._undo_write(replaced, targets)}")
    return {"snapshot": targets[0], "summary": targets[1], "sha256": sha, "run_summary": summary}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("snapshot", type=Path, help="the installed edition's snapshot file (v<N>.json)")
    ap.add_argument("--sha256", required=True, type=Path, help="the hand-over hash file of the snapshot (<snapshot>.sha256)")
    ap.add_argument("--ledger", required=True, type=Path, help="the run's private call ledger (v<N>.ledger.json); read, never copied")
    ap.add_argument("--out", required=True, type=Path, help="the public samples folder, docs/examples/editions")
    ap.add_argument("--sidecar", type=Path, default=None, help="the hand-over sidecar (default <snapshot>.sidecar.json)")
    ap.add_argument("--replace", action="store_true", help="overwrite existing public files of this edition")
    ap.add_argument("--repo", type=Path, default=REPO, help="git checkout holding the producer commit (default: this one)")
    args = ap.parse_args(argv)
    try:
        result = export(args.snapshot, args.sha256, args.ledger, args.out, args.sidecar, args.replace, args.repo,
                        env_file=DEFAULT_ENV_FILE)
    except (ExportError, es.SidecarError) as exc:
        outcome = "" if exc.code == "write_failed" else "; nothing written"  # a write failure says what it left
        print(f"export_public_edition: refused ({exc.code}): {exc.message}{outcome}", file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"export_public_edition: refused (unreadable_input): {type(exc).__name__}; nothing written", file=sys.stderr)
        return 2
    s = result["run_summary"]
    print(f"snapshot {result['snapshot']}  sha256 {result['sha256']}")
    print(f"summary  {result['summary']}")
    print(f"calls {s['calls']['total']} (failed {s['calls']['failed']}), provider route {s['provider_route']}, "
          f"route_substituted {s['route_substituted']}, lane_unverified {s['lane_unverified']}, hmem_injected "
          f"{s['hmem_injected']}, cache_hits {s['cache_hits']}, meterless_receipts {s['meterless_receipts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
