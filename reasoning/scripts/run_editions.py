"""Runs one date's editions for any list of topics: a dry check per topic (the call estimate), the topics shared out
between API keys under a per-key budget, one worker per key, key rotation with --resume when a run drains its key,
one log per run and one status file per topic-date.

    # plan only (the default): dry checks, estimates and the key plan; nothing live is started
    python -X utf8 scripts/run_editions.py --date 2026-10-26 --topics all \
        --keys MODEL_API_KEY,MODEL_API_KEY_2,MODEL_API_KEY_3 --out snapshots/_private \
        --log-dir snapshots/_runs/logs --status-dir snapshots/_runs/status --dry-check-out snapshots/_runs/dry
    # the same command with --live starts the paid runs
    python -X utf8 scripts/run_editions.py ... --live

Topics: the listed ids, each checked against collection's `topics` table (a listed id that is not a row fails), or
`all` = every row (only active rows in collection order once Zetaris registers `active` and `created_at`; until then
`all` plans only and --live with it is refused). Topic ids follow the shared rule (tools/corpus._TOPIC_ID) and are no
Windows device name (con, nul, com1, ...).

Per topic: `scripts/dry_check.py` runs the graph with stand-ins on the day's corpus into --dry-check-out and counts the
model calls per lane; the count, scaled by --estimate-factor, is the estimate. Topics are placed greedily, in the order
given, on the key with the most room under the per-key caps (--max-calls-per-key fast-lane calls, --max-ultra-calls-per-key
Ultra calls); a topic larger than any key's room starts on the key with the most room and continues on the next ones,
also when it is larger than all keys together: what is left when the keys have drained waits for the next window.
Each key runs one live process at a time (`python -m quorum_reasoning.run --model live --corpus zetaris`) with
MODEL_API_KEY set from that key's variable and every other key variable blank, so a process holds exactly one key.
Exit 0 (or 2 with a stored snapshot of this run, i.e. published partial) -> published; exit 3 (route drained) -> the key
is spent for this invocation and the topic is requeued as --resume on another key with at least MIN_SEGMENT_CALLS of
room, else waiting_for_key; any other outcome -> failed with a short reason, the rest continue. A rerun of the same
command skips what is published, resumes what has a checkpoint, and starts the rest.

Without --keys one worker runs every topic on the route in .env as it is (no key is injected): the Meterless route,
or a single direct key. The route counts as one key under the same caps (behind Nightshift it is still one NVIDIA
account), so --max-calls-per-key bounds what one invocation starts there.

Status files (the portal's contract, Issue #2 6411408519): <status-dir>/<topic>/<date>.json with exactly topic, date,
state (queued | running | published | failed | waiting_for_key), run_id, started_at, updated_at, attempts and reason
(a string or null), written atomically (temp file + os.replace) and each followed by <date>.json.sha256
("<sha256>  <date>.json"), which the portal's install command checks. Only a live invocation writes them; while the
live store's newest version of the topic-date is another run id's, the file shows that version as published, and a
rerun that finds its run id published leaves a pair that already says so as it is (decisions at Statuses.save,
Statuses.follow_store and Statuses.keep_published). The runner's own record of each run id (what set the state,
estimates, the plan, key names, runs, versions) is <status-dir>/_runner/<date>/<topic>/<attempt>.json, beside
_summary.json and the lock in <status-dir>/_runner/<date>/, never installed (decision at Statuses). Both hold key
variable names, never values, and file names relative to --log-dir, never paths. A run without --live writes no status
file, never touches the record of another run id, and never changes a live outcome in its own run id's record: it
writes its plan beside it (decisions at Statuses and Statuses.open). Logs: one per run in <log-dir>/
(<date>_<topic>_a<attempt>_run<NN>_<key>.log, NN counting the live runs of that run id: decision at run_log_name;
<date>_<topic>_dry.log, <date>_runner.log); every key and token value the runner knows is replaced by [redacted]
before a byte reaches a log.

Exit code: 0 every topic published (or, without --live, every dry check passed and the plan finishes every topic in
this invocation), 1 a topic failed (a listed id that is not a row, or a row whose id breaks the rule, counts), 3 a
topic is waiting for a key (none failed; without --live: the plan leaves one for the next window), 2 a usage or
preflight refusal, 130 interrupted. Without --live a live outcome kept in a status file counts as it would with it.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import heapq
import json
import math
import os
import queue
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date as Date
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCRIPTS = Path(__file__).resolve().parent
REASONING = SCRIPTS.parent
ROOT = REASONING.parent
if str(REASONING) not in sys.path:
    sys.path.insert(0, str(REASONING))

DEFAULT_ENV_FILE = ROOT / ".env"  # where key values are read from; the live run itself reads the same file (llm._env)
FAST_CAP = 650  # fast-lane calls per key per >= 6 h window (reasoning/README.md, budget rules)
ULTRA_CAP = 250  # Ultra calls (fact-checker + reviewer) per key per window
# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): the estimate is the dry check's count times 1.6, and the Ultra part
# is at least 10% of the scaled fast-lane part. Why: on the rehearsal DB the dry check of russia-ukraine-war 2026-10-24
# counts 924 fast-lane and 0 Ultra calls; the live attempt 3 of that day (50 documents vs 49) made 1467 fast-lane and
# 134 Ultra calls (attempt 5: 1574 and 100): the stand-ins extract fewer claims (604 stance calls vs 1286) and their
# rubric gates every event, so no fact-check is counted. One day of evidence; both numbers are options.
ESTIMATE_FACTOR = 1.6
ULTRA_FLOOR_SHARE = 0.1
# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a topic that fits no key whole starts only on a key with at least
# 25 calls of room on each lane it needs, and a lane whose estimate is used up while the run still drains is taken to
# need 25 more; when no live key has that room the topic waits for a key. Why: a resume first replays its journal,
# then needs room for real calls; starting it on a near-empty key only adds refused requests to an empty bucket.
MIN_SEGMENT_CALLS = 25
PACE_S = {"fast": 6.0, "ultra": 10.0}  # base pacing per call (README): the plan's duration is pacing only
TOPIC_RULE = "^[a-z0-9][a-z0-9-]{0,63}$"  # printed in messages; the rule itself is tools/corpus._TOPIC_ID
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD", re.I)
EXTRA_KEY_NAME = re.compile(r"^MODEL_API_KEY_\w+$")
FAST_LANES = ("default",)
ULTRA_LANES = ("fact_checker", "reviewer")
MIN_KEY_CHARS = 8
REASON_MAX = 300
ROUTE = "route"  # the pseudo-key name without --keys: the route in .env as it is


# ---------------------------------------------------------------------------------------------------------------------
# small helpers


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


WINDOWS_DEVICE = re.compile(r"^(?:con|prn|aux|nul|com[0-9¹²³]|lpt[0-9¹²³])$", re.IGNORECASE)  # decision at topic_id_problem
DEVICE_REASON = "a Windows reserved device name (con, prn, aux, nul, com0-9, lpt0-9): as a status, log or store name it opens a device"


def topic_id_problem(topic: Any) -> str | None:
    """Why `topic` cannot be run, or None: the shared topic-id rule, then no Windows device name.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): the runner, the dry check and resume_with_next_key.sh take topic
    ids by the shared rule (fullmatch, so not even a trailing newline passes), not a stricter slug of their own. Why: a
    row such as `ai--jobs` is collected and run.py runs it; the stricter rule refused it when listed and dropped it from
    `all` without a trace. The rule has no dots or slashes, so status and log names stay inside their folders
    (superseded 2026-10-26, review round 2: not on Windows; see the next decision).
    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): an id that is a Windows reserved device name (con, prn, aux, nul,
    com0-9, lpt0-9, any case, superscript digits too) is refused like one that breaks the rule: a listed one is a
    refusal, a row under `--topics all` is a skipped row. Why: the shared rule admits them, and on Windows
    <status-dir>/<date>/con.json, _estimates/<date>/con.json and <out>/con/ are the console device in every folder:
    reading the status file blocked the runner and saving it raised FileExistsError, which aborted every topic of the
    date (review round 2 probes). collection's CHECK and tools/corpus._TOPIC_ID still admit them (not this module's)."""
    from quorum_reasoning.tools.corpus import _TOPIC_ID

    if not isinstance(topic, str) or _TOPIC_ID.fullmatch(topic) is None:
        return f"not a topic id by the shared rule {TOPIC_RULE}"
    if WINDOWS_DEVICE.fullmatch(topic):
        return DEVICE_REASON
    return None


def topic_id_ok(topic: Any) -> bool:
    """The shared topic-id rule (collection's CHECK on topics.id, tools/corpus._TOPIC_ID, the collectors) and no
    Windows device name (decisions at topic_id_problem)."""
    return topic_id_problem(topic) is None


def edition_cut_utc(edition_date: str) -> datetime:
    """05:30 America/New_York on the edition day, in UTC (docs/DECISIONS.md › Daily editions; tools/corpus does the same)."""
    from zoneinfo import ZoneInfo

    d = Date.fromisoformat(edition_date)
    return datetime(d.year, d.month, d.day, 5, 30, tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)


def json_bytes(obj: Any) -> bytes:
    """The bytes a JSON file of the runner holds (UTF-8, LF line ends on every system)."""
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha256_line(name: str, data: bytes) -> bytes:
    """A sha256sum line for a file named `name` holding `data`: "<64 hex>  <name>\\n"."""
    return f"{hashlib.sha256(data).hexdigest()}  {name}\n".encode("utf-8")


def write_json_atomic(path: Path, obj: Any) -> None:
    write_bytes_atomic(path, json_bytes(obj))


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Temp file in the same folder, fsync, then os.replace: a reader sees the old file or the new one, never part of
    one. os.replace is retried briefly on Windows, where a reader holding the file open makes it fail for a moment."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        for attempt in range(10):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.05 * (attempt + 1))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Redactor:
    """Replaces every known secret value with [redacted], longest first, in bytes and in text."""

    MARK = "[redacted]"

    def __init__(self, secrets: Iterable[str]):
        vals = sorted({s for s in secrets if isinstance(s, str) and len(s) >= MIN_KEY_CHARS}, key=len, reverse=True)
        self._text = vals
        self._bytes = [v.encode("utf-8") for v in vals]

    def text(self, s: str) -> str:
        for v in self._text:
            s = s.replace(v, self.MARK)
        return s

    def raw(self, b: bytes) -> bytes:
        for v in self._bytes:
            b = b.replace(v, self.MARK.encode())
        return b


_WIN_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\)[^\s'\"<>|]*")
_POSIX_PATH = re.compile(r"(?<![\w.~-])/(?:[^\s/'\"]+/)+[^\s'\"]*")


def clean_reason(text: str | None, redactor: Redactor) -> str | None:
    """A status reason: secrets redacted, absolute paths replaced by <path>, one line, at most REASON_MAX characters."""
    if not text:
        return None
    s = redactor.text(str(text))
    s = _WIN_PATH.sub("<path>", s)
    s = _POSIX_PATH.sub("<path>", s)
    s = " ".join(s.split())
    return s[: REASON_MAX - 1] + "…" if len(s) > REASON_MAX else s


def run_id(topic: str, edition_date: str, attempt: int) -> str:
    return f"{edition_date}-{topic}-{attempt}"  # quorum_reasoning.ids.run_id


def run_log_name(edition_date: str, topic: str, attempt: int, n: int, key_name: str) -> str:
    """The log file (relative to --log-dir) of live run `n` of run id <date>-<topic>-<attempt> on key `key_name`.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a live run's log is <date>_<topic>_a<attempt>_run<NN>_<key>.log,
    and both live_run (the file it writes) and _drive (the name the record keeps in `log` and `runs[].log`) take it
    from here. Why: NN counts the runs of one run id (its record's `attempts` + 1), so the first run of attempt 1 and
    the first run of attempt 2 on the same key were both run01_<key>.log, opened for appending: one file held both
    runs and both records named it (closing review round 4). Topic ids have no underscore, so the parts stay apart.
    Supersedes <date>_<topic>_run<NN>_<key>.log."""
    return f"{edition_date}_{topic}_a{attempt}_run{n:02d}_{key_name}.log"


def journal_counts(out: Path, rid: str) -> tuple[int, int]:
    """(fast-lane, Ultra) rows in the run's private journal: every live call of the run, across resumes; replayed
    answers add no row. Payloads and replies are parsed and dropped, never kept or printed."""
    path = out / "_journal" / f"{rid}.jsonl"
    fast = ultra = 0
    if not path.is_file():
        return 0, 0
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                lane = json.loads(line).get("lane")
            except (json.JSONDecodeError, AttributeError):
                continue
            if lane in ULTRA_LANES:
                ultra += 1
            else:
                fast += 1
    return fast, ultra


def checkpoint_has_thread(out: Path, rid: str) -> bool:
    """True when <out>/_checkpoints/<rid>.sqlite holds a checkpoint of thread <rid> (opened read-only): a fresh run
    would be refused there, a resume continues it. A file with an unknown layout counts as a checkpoint."""
    path = out / "_checkpoints" / f"{rid}.sqlite"
    if not path.is_file():
        return False
    try:
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT 1 FROM checkpoints WHERE thread_id = ? LIMIT 1", (rid,)).fetchone()
        finally:
            conn.close()
        return row is not None
    except sqlite3.Error:
        return True


def published_by(out: Path, topic: str, edition_date: str, rid: str, after: int = 0) -> tuple[int, str | None] | None:
    """(version, snapshot status) of the newest stored version above `after` whose run_id is `rid`, or None."""
    from quorum_reasoning import store

    for v in reversed(store.versions(out, topic, edition_date)):
        if v <= after:
            break
        try:
            snap = store.load(out, topic, edition_date, v)
        except (OSError, ValueError):
            continue
        if snap.get("run_id") == rid:
            return v, snap.get("status")
    return None


def latest_version(out: Path, topic: str, edition_date: str) -> int:
    from quorum_reasoning import store

    found = store.versions(out, topic, edition_date)
    return found[-1] if found else 0


def latest_snapshot(out: Path, topic: str, edition_date: str) -> tuple[int, dict[str, Any]] | None:
    """(version, snapshot) of the newest readable stored version of the topic-date, what latest.json serves, or None."""
    from quorum_reasoning import store

    for v in reversed(store.versions(out, topic, edition_date)):
        try:
            snap = store.load(out, topic, edition_date, v)
        except (OSError, ValueError):
            continue
        if isinstance(snap, dict):
            return v, snap
    return None


def _overlaps(a: Path, b: Path) -> bool:
    a, b = a.resolve(), b.resolve()
    return a == b or a in b.parents or b in a.parents


# ---------------------------------------------------------------------------------------------------------------------
# the plan: keys, work items and the greedy placement (pure; the live driver and the simulation share it)


@dataclass
class Key:
    name: str
    cap_fast: int = FAST_CAP
    cap_ultra: int = ULTRA_CAP
    inject: bool = True  # False for the ROUTE pseudo-key: the route in .env as it is
    used_fast: int = 0
    used_ultra: int = 0
    busy: bool = False
    drained: bool = False

    @property
    def room(self) -> tuple[int, int]:
        return max(0, self.cap_fast - self.used_fast), max(0, self.cap_ultra - self.used_ultra)

    def share(self) -> float:
        rf, ru = self.room
        return min(rf / self.cap_fast, ru / self.cap_ultra)


def _remaining(est: int, done: int) -> int:
    left = est - done
    if left > 0:
        return left
    return MIN_SEGMENT_CALLS if done > 0 else 0  # decision at MIN_SEGMENT_CALLS


@dataclass
class Item:
    topic: str
    est_fast: int
    est_ultra: int
    done_fast: int = 0
    done_ultra: int = 0
    resume: bool = False

    def need(self) -> tuple[int, int]:
        return _remaining(self.est_fast, self.done_fast), _remaining(self.est_ultra, self.done_ultra)


def _most_room(keys: list[Key]) -> Key:
    return max(keys, key=lambda k: (k.share(), k.room[0], k.room[1]))  # max() keeps the first of equals: key order


class Planner:
    """Greedy placement under the per-key caps.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): topics are taken in the order given (a resumed topic goes back to
    the front); each goes to the idle key with the most room that fits its whole estimate on both lanes; when only a
    busy key could fit it, it waits for that key and later topics may use the idle keys; when no key fits it whole, it
    starts on the idle key with the most room (at least MIN_SEGMENT_CALLS on each lane it needs) if all live keys
    together have its room, or, once every live key is idle, whatever they have; it continues with --resume on the
    next key once that one drains, and the rest of its estimate is held on the other keys (most room first) so later
    topics cannot take it. What is left when every key has drained waits for the next window's rerun, which resumes
    it from its checkpoint and journal with a smaller need (state waiting_for_key, also when no live key has
    MIN_SEGMENT_CALLS of room). A key that drained (exit 3) takes nothing more in this invocation. A reservation is
    replaced by the calls the journal shows once the run ends; a topic's holds are given back when it is placed again
    or ends. Why: one live topic-day is 1 500-1 600 fast-lane calls (2026-10-24 attempts 3 and 5) against ~650 per key
    per window, so most topics span keys, and on one key or the route nearly every topic is larger than all keys
    together; finishing a started topic before starting the next publishes whole editions instead of several half-done
    ones, and the journal plus checkpoint make a split lossless. Supersedes (review round 1, 2026-10-26) the first
    rule that a topic larger than all keys together waits without starting: no rerun could ever start it.
    """

    def __init__(self, keys: list[Key], items: Iterable[Item]):
        self.keys = keys
        self.pending: list[Item] = list(items)
        self.waiting: list[tuple[Item, str]] = []
        self.holds: dict[str, list[tuple[Key, tuple[int, int]]]] = {}

    def _release(self, item: Item) -> list[tuple[Key, tuple[int, int]]]:
        held = self.holds.pop(item.topic, [])
        for k, (f, u) in held:
            k.used_fast -= f
            k.used_ultra -= u
        return held

    def _hold(self, item: Item, held: list[tuple[Key, tuple[int, int]]]) -> None:
        for k, (f, u) in held:
            k.used_fast += f
            k.used_ultra += u
        if held:
            self.holds[item.topic] = held

    def _hold_rest(self, item: Item, start: Key, rest: tuple[int, int]) -> None:
        """Holds the part of a split topic's estimate its first key cannot take on the other live keys."""
        rf, ru = rest
        held: list[tuple[Key, tuple[int, int]]] = []
        for k in sorted((k for k in self.keys if k is not start and not k.drained), key=lambda k: (-k.share(), -k.room[0], -k.room[1])):
            if rf <= 0 and ru <= 0:
                break
            take = (min(rf, k.room[0]), min(ru, k.room[1]))
            if take != (0, 0):
                held.append((k, take))
                rf -= take[0]
                ru -= take[1]
        self._hold(item, held)

    def _choose(self, item: Item) -> tuple[str, Key | None, str]:
        alive = [k for k in self.keys if not k.drained]
        if not alive:
            return "none", None, "every key is drained for this invocation; rerun the same command once the keys have rested (>= 6 h)"
        nf, nu = item.need()
        idle = [k for k in alive if not k.busy]
        busy = [k for k in alive if k.busy]

        def fits(k: Key) -> bool:
            return nf <= k.room[0] and nu <= k.room[1]

        fit_idle = [k for k in idle if fits(k)]
        if fit_idle:
            return "start", _most_room(fit_idle), ""
        if any(fits(k) for k in busy):
            return "wait", None, ""
        starters = [k for k in idle if k.room[0] >= min(MIN_SEGMENT_CALLS, nf) and k.room[1] >= min(MIN_SEGMENT_CALLS, nu)]
        total_f = sum(k.room[0] for k in alive)
        total_u = sum(k.room[1] for k in alive)
        if starters and ((total_f >= nf and total_u >= nu) or not busy):
            return "start", _most_room(starters), ""  # all idle: whatever the keys have; the rest waits for a rerun
        if busy:
            return "wait", None, ""  # a running reservation may come back when its run ends
        most_f = max(k.room[0] for k in alive)
        most_u = max(k.room[1] for k in alive)
        return "none", None, (f"needs about {nf} fast-lane and {nu} Ultra calls; no key left has {MIN_SEGMENT_CALLS} calls of room "
                              f"on each lane it needs (most: {most_f} fast-lane, {most_u} Ultra): rerun the same command once the "
                              "keys have rested (>= 6 h), or add a key")

    def place(self) -> list[tuple[Item, Key, tuple[int, int]]]:
        started: list[tuple[Item, Key, tuple[int, int]]] = []
        progress = True
        while progress:
            progress = False
            for item in list(self.pending):
                held = self._release(item)  # its own holds are room for itself
                verdict, key, reason = self._choose(item)
                if verdict == "wait":
                    self._hold(item, held)
                    continue
                self.pending.remove(item)
                if verdict == "none":
                    self.waiting.append((item, reason))
                    continue
                assert key is not None
                nf, nu = item.need()
                rf, ru = key.room
                res = (min(nf, rf), min(nu, ru))
                key.used_fast += res[0]
                key.used_ultra += res[1]
                key.busy = True
                if res != (nf, nu):
                    self._hold_rest(item, key, (nf - res[0], nu - res[1]))
                started.append((item, key, res))
                progress = True
                break  # the keys changed: rescan from the first pending item
        return started

    def take_waiting(self) -> list[tuple[Item, str]]:
        out, self.waiting = self.waiting, []
        return out

    def finish(self, item: Item, key: Key, res: tuple[int, int], outcome: str, used: tuple[int, int]) -> None:
        """outcome: published | drained | failed; `used` = the run's live calls (journal rows added)."""
        key.busy = False
        key.used_fast += used[0] - res[0]
        key.used_ultra += used[1] - res[1]
        item.done_fast += used[0]
        item.done_ultra += used[1]
        if outcome == "drained":
            key.drained = True
            item.resume = True
            self.pending.insert(0, item)  # its holds stay until it is placed again
        else:
            self._release(item)


def simulate(keys: list[Key], items: list[Item]) -> dict[str, dict[str, Any]]:
    """The plan the placement gives if every estimate is right: per topic its segments (key, calls it is expected to
    make there, resume) and outcome, with run times from the base pacing only (model latency comes on top). A segment
    that cannot hold the rest of its topic is taken to progress on both lanes in step until its tighter lane runs out
    (the fast-lane nodes come first in the graph, so a drained key has rarely reached the fact-check)."""
    keys = [dataclasses.replace(k, busy=False) for k in keys]
    items = [dataclasses.replace(i) for i in items]
    planner = Planner(keys, items)
    plan: dict[str, dict[str, Any]] = {i.topic: {"segments": [], "outcome": None} for i in items}
    heap: list[tuple[float, int, Item, Key, tuple[int, int], tuple[int, int], bool]] = []
    t, seq = 0.0, 0
    while True:
        for item, key, res in planner.place():
            nf, nu = item.need()
            drains = nf > res[0] or nu > res[1]
            used = res
            if drains:
                frac = min(res[0] / nf if nf else 1.0, res[1] / nu if nu else 1.0)
                used = (min(res[0], round(nf * frac)), min(res[1], round(nu * frac)))
            dur = used[0] * PACE_S["fast"] + used[1] * PACE_S["ultra"]
            plan[item.topic]["segments"].append({"key": key.name, "fast": used[0], "ultra": used[1], "resume": item.resume,
                                                 "starts_after_min": round(t / 60)})
            heapq.heappush(heap, (t + dur, seq, item, key, res, used, drains))
            seq += 1
        for item, reason in planner.take_waiting():
            plan[item.topic]["outcome"] = "waiting_for_key"
            plan[item.topic]["reason"] = reason
        if not heap:
            break
        t, _, item, key, res, used, drains = heapq.heappop(heap)
        planner.finish(item, key, res, "drained" if drains else "published", used)
        if not drains:
            plan[item.topic]["outcome"] = "published"
            plan[item.topic]["ends_after_min"] = round(t / 60)
    return plan


def describe_plan(entry: dict[str, Any]) -> str:
    segs = " -> ".join(f"{s['key']} ({s['fast']}/{s['ultra']}{', resume' if s['resume'] else ''})" for s in entry["segments"])
    if entry["outcome"] == "published":
        return f"{segs}; done after ~{entry.get('ends_after_min', 0)} min of pacing"
    return (segs + "; then " if segs else "") + f"waits for a key: {entry.get('reason', '')}"


# ---------------------------------------------------------------------------------------------------------------------
# status files


LIVE_ONLY_STATES = ("running", "published", "waiting_for_key")  # states no plan run (without --live) ever sets


def holds_live_outcome(doc: dict[str, Any]) -> bool:
    """True when a status document records what live runs did: a run row, a state only a live invocation (or the live
    store) sets, or another state a live invocation set (`state_mode` live, e.g. failed). `queued` alone is not one."""
    state = doc.get("state")
    return bool(doc.get("runs")) or state in LIVE_ONLY_STATES or (doc.get("state_mode") == "live" and state not in (None, "queued"))


RUNNER_DIR = "_runner"  # <status-dir>/_runner/<date>/: the runner's records, _summary.json, the lock (decision at Statuses)
PUBLIC_FIELDS = ("topic", "date", "state", "run_id", "started_at", "updated_at", "attempts", "reason")
STATES = ("queued", "running", "published", "failed", "waiting_for_key")
PLAN_FIELDS = ("plan", "plan_outcome", "plan_reason")


def runner_dir(status_dir: Path, edition_date: str) -> Path:
    return status_dir / RUNNER_DIR / edition_date


def record_file(status_dir: Path, edition_date: str, topic: str, attempt: int) -> Path:
    """The runner's own record of run id <date>-<topic>-<attempt> (decision at Statuses)."""
    return runner_dir(status_dir, edition_date) / topic / f"{attempt}.json"


class Statuses:
    """Per topic-date, the portal's status file <status-dir>/<topic>/<date>.json (+ <date>.json.sha256); per run id, the
    runner's own record <status-dir>/_runner/<date>/<topic>/<attempt>.json. Only the main thread writes them.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): the status file holds exactly PUBLIC_FIELDS (`reason` null when
    there is none) at <status-dir>/<topic>/<date>.json, and <date>.json.sha256 beside it holds the sha256sum line of its
    bytes; both are written atomically, the hash after the file. Everything else the runner keeps (`state_mode`, the
    estimates, the plan, key names, `runs`, versions, exit codes) is in its record under <status-dir>/_runner/<date>/,
    with _summary.json and the lock; the record is what the runner reads back (one per run id since closing review
    round 3: see the next decision). Why: the contract agreed with the portal
    in Issue #2 (6411408519, 6411653104): one folder per topic, the file named by the edition date, these eight fields
    and the five STATES (save refuses any other state before writing), installed by a `reasoning_status --file
    --sha256` command of the same shape as `reasoning_snapshot`; the portal does not ignore unknown fields. `_runner`
    can never be a topic id (the shared rule starts with a letter or digit), while a date such as 2026-10-26 is one, so
    no runner folder is named like a topic.
    Between the two writes a reader can see the new file with the old hash: the install refuses it and is retried.
    Supersedes (2026-10-26) the layout <status-dir>/<date>/<topic>.json with every field in one file.
    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): the runner keeps one record per run id,
    <status-dir>/_runner/<date>/<topic>/<attempt>.json (record_file), and an invocation reads and writes only its own
    run id's record (follow_store also reads the shown run id's). Why: one record per topic-date was replaced by any
    invocation of another run id, plans included: after the README's plan without --attempt (attempt 1) behind a live
    attempt 2, the next live attempt 2 started `attempts` again at 1 with `started_at` = now, lost its `runs` and appended
    its second log to run01, and a rerun of an attempt already published rewrote its file with attempts 0 (closing review
    round 3). Supersedes the layout <status-dir>/_runner/<date>/<topic>.json (closing review round 1); records written in
    it are not read (a live invocation recovers `attempts` and `started_at` from the status file: decision at open).

    `state_mode` in a record says what set its `state`: `live` (a live invocation, or a snapshot of the run id in the
    live store), or `dry` (a plan run)."""

    def __init__(self, status_dir: Path, edition_date: str, redactor: Redactor, mode: str = "live", attempt: int = 1):
        self.root = status_dir
        self.date = edition_date
        self.attempt = attempt  # --attempt: the run id is <date>-<topic>-<attempt>
        self.redactor = redactor
        self.mode = mode
        self.docs: dict[str, dict[str, Any]] = {}
        self.kept: set[str] = set()  # dry mode: topics whose record keeps its live outcome (decision at open)
        # live mode: topic -> the run id whose published version the file shows and keeps in this invocation (another
        # run id: decision at follow_store; this one, found published at the start: decision at keep_published)
        self.pinned: dict[str, str] = {}

    def path(self, topic: str) -> Path:
        """The portal's status file of `topic` on this date."""
        return self.root / topic / f"{self.date}.json"

    def record_path(self, topic: str, attempt: int | None = None) -> Path:
        """The runner's own record of `topic`'s run id on this date (this invocation's --attempt unless `attempt`)."""
        return record_file(self.root, self.date, topic, attempt or self.attempt)

    def load(self, topic: str, attempt: int | None = None) -> dict[str, Any] | None:
        try:
            doc = json.loads(self.record_path(topic, attempt).read_text(encoding="utf-8"))
            return doc if isinstance(doc, dict) else None
        except (OSError, ValueError):
            return None

    def _record_of(self, topic: str, rid: str) -> dict[str, Any] | None:
        """The runner's record of run id `rid` of `topic` on this date, or None (not a run id the runner names, or none)."""
        m = re.fullmatch(re.escape(f"{self.date}-{topic}-") + r"([1-9][0-9]{0,8})", rid)
        doc = self.load(topic, int(m.group(1))) if m else None
        return doc if doc and doc.get("run_id") == rid else None

    def open(self, topic: str, rid: str) -> dict[str, Any]:
        """The topic's document for this invocation: an earlier one of the same run id keeps its history.

        DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a plan run (no --live) whose status file already holds a live
        outcome of the same run id (holds_live_outcome) keeps the whole document: `state`, `reason`, `exit_code` and the
        live fields stay, and the plan's verdict goes to `plan`, `plan_outcome`, `plan_reason` and the estimates only;
        its exit code counts the kept state (failed -> 1; waiting_for_key, queued or running -> 3). Why: the README says
        to run the plan any time into the same --status-dir; it turned a live `failed` (exit 7) or `waiting_for_key`
        into `queued` with exit 0, so neither the file, _summary.json nor the exit code showed the failure or the wait.
        A state an earlier plan run set (`state_mode` dry) is replaced as before; a live run replaces everything.
        DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): in a live invocation a record's `started_at` is kept only when
        a live invocation set it (`started_mode` live: the run id's first live start, or, before one, when a live
        invocation first queued it) or the record has a `runs` row; otherwise, a plan run's time included, it becomes
        now. Why: the portal shows `waiting_for_key` as "being prepared since started_at", and a topic that a live
        invocation left waiting without ever starting it kept the plan run's time, hours before the cut (closing review
        round 2). Supersedes the closing-round-1 decision at _drive that only the first live start replaces it.
        DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a live invocation whose record of its run id holds no live
        history (no record, or only a plan run's: no `runs` row, `started_mode` not live) while the status file names
        that run id and its .sha256 matches takes `started_at` and `attempts` from the file (`started_mode` live).
        Why: only a live invocation writes the file, so it is the run's live history when the record lost it (a record
        of the layout before closing review round 3, or a deleted _runner folder, perhaps followed by a plan); without
        it the run would start `attempts` again at 1, date itself now and append its next log to run01."""
        old = self.load(topic)
        now = now_iso()
        same = bool(old) and old.get("run_id") == rid
        if same and self.mode == "dry" and holds_live_outcome(old):
            doc = dict(old)
            self.kept.add(topic)
        elif same:
            doc = {k: v for k, v in old.items() if k in ("started_at", "started_mode", "attempts", "runs")}
        else:
            doc = {}
        if self.mode == "live" and not doc.get("runs") and doc.get("started_mode") != "live":
            shown, verified = self._read_public(topic)
            if shown and verified and shown.get("run_id") == rid and isinstance(shown.get("started_at"), str) \
                    and isinstance(shown.get("attempts"), int) and shown["attempts"] >= 0:
                doc.update(started_at=shown["started_at"], started_mode="live", attempts=shown["attempts"])
            else:
                doc["started_at"], doc["started_mode"] = now, "live"
        doc.setdefault("started_at", now)
        doc.setdefault("started_mode", self.mode)
        doc.setdefault("attempts", 0)
        doc.setdefault("runs", [])
        doc.update({"topic": topic, "date": self.date, "run_id": rid})
        self.docs[topic] = doc
        return doc

    def _read_public(self, topic: str) -> tuple[dict[str, Any] | None, bool]:
        """The status file's document (None when it is missing or unreadable) and whether its .sha256 matches it."""
        path = self.path(topic)
        try:
            data = path.read_bytes()
            doc = json.loads(data.decode("utf-8"))
        except (OSError, ValueError):
            return None, False
        try:
            ok = path.with_name(path.name + ".sha256").read_bytes() == sha256_line(path.name, data)
        except OSError:
            ok = False
        return (doc, ok) if isinstance(doc, dict) else (None, False)

    def _write_public(self, topic: str, doc: dict[str, Any]) -> None:
        data = json_bytes({k: doc.get(k) for k in PUBLIC_FIELDS})  # decision at Statuses
        path = self.path(topic)
        write_bytes_atomic(path, data)
        write_bytes_atomic(path.with_name(path.name + ".sha256"), sha256_line(path.name, data))

    def follow_store(self, topic: str, latest: tuple[int, dict[str, Any]] | None) -> str | None:
        """Live mode: points the topic's status file at the store's newest version (`latest`, from latest_snapshot).
        Returns the other run id while the file shows that run's published version, else None.

        DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): while the live store's newest version of the topic-date
        belongs to another run id (an earlier --attempt, or one run outside the runner), the status file shows it:
        `published` with that run id, left byte-identical when it already says so and its .sha256 matches, else
        written once (started_at, attempts and reason from the runner's record or the status file of that run id, else
        the snapshot's published_at, 0 and null); this invocation's states go to its record only, until its own run
        publishes a newer version. Why: there is one status file per topic and date, and readers are served the newest
        version (latest.json); a later attempt turned a published topic into `queued` ("Waiting for its first brief") or
        `failed` ("Could not be prepared") next to the edition they were reading (closing review round 2)."""
        if self.mode != "live":
            return None
        rid = self.docs[topic]["run_id"]
        shown = latest[1].get("run_id") if latest else None
        if not isinstance(shown, str) or shown == rid:
            self.pinned.pop(topic, None)
            return None
        on_disk, verified = self._read_public(topic)
        if on_disk and verified and on_disk.get("state") == "published" and on_disk.get("run_id") == shown:
            self.pinned[topic] = shown
            return shown
        base: dict[str, Any] = {}
        for cand in (self._record_of(topic, shown), on_disk):  # that run id's own record first (decision at Statuses)
            if isinstance(cand, dict) and cand.get("run_id") == shown and cand.get("state") == "published":
                base = cand
                break
        published_at = latest[1].get("published_at") if latest else None
        attempts = base.get("attempts")
        started = base.get("started_at")
        self._write_public(topic, {
            "topic": topic, "date": self.date, "state": "published", "run_id": shown,
            "started_at": started if isinstance(started, str) else (published_at if isinstance(published_at, str) else now_iso()),
            "updated_at": now_iso(), "attempts": attempts if isinstance(attempts, int) else 0,
            "reason": clean_reason(base.get("reason"), self.redactor)})
        self.pinned[topic] = shown
        return shown

    def keep_published(self, topic: str) -> bool:
        """Live mode, for a run id found already published: True when this invocation leaves the status pair as it is,
        because it already shows this run id `published` with a matching .sha256 (or another run's newer version:
        follow_store).

        DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a rerun that finds its run id published ("already published
        by an earlier run") leaves a status pair that already says so byte-identical, as follow_store does for another
        run id, and writes its record only; a pair that is missing, says otherwise or fails its hash is written from the
        record. Why: the rewrite changed `updated_at` and `reason` of a correct file, and after a plan of another
        attempt had replaced the record it wrote `attempts` 0 and `started_at` = the rerun's time (closing review round 3)."""
        if self.mode != "live":
            return False
        if topic in self.pinned:  # the file shows another run's newer version (follow_store) and stays as it is
            return True
        rid = self.docs[topic]["run_id"]
        on_disk, verified = self._read_public(topic)
        if on_disk and verified and on_disk.get("state") == "published" and on_disk.get("run_id") == rid:
            self.pinned[topic] = rid
            return True
        return False

    def verdict(self, topic: str, state: str, reason: str | None, **more: Any) -> dict[str, Any]:
        """A verdict of this invocation that is not a live run's outcome (not a row, a dry check, the plan): into `state`
        and `reason`, or, when the file keeps a live outcome, into `plan_outcome` and `plan_reason` (decision at open)."""
        if topic in self.kept:
            more.setdefault("plan_outcome", state)
            return self.save(topic, plan_reason=reason, **more)
        return self.save(topic, state=state, reason=reason, **more)

    def save(self, topic: str, **changes: Any) -> dict[str, Any]:
        """Applies `changes` (None removes a field), then writes the record and, in a live invocation, the status file
        with its hash.

        DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): only a live invocation writes the status file and its hash;
        a plan run (no --live) writes its record only, whatever the run id, and so does a live invocation while the
        file shows another run's published version (decision at follow_store) or already shows this run id published
        (decision at keep_published). Why: for the portal no file and `queued`
        read the same ("Waiting for its first brief"), so a plan has nothing to tell readers, while its writes turned a
        published edition into `queued` (another --attempt, or the README's plan without --attempt after attempt 2)
        and a dry check that failed into `failed` ("Could not be prepared") for an edition nobody had tried to run
        (closing review round 2). Supersedes, for the status file, the review-round-2 decision at open (a plan run kept
        only a live outcome of the same run id); the record still follows it."""
        doc = self.docs[topic]
        if (changes.get("state") or doc.get("state")) not in STATES:  # decision at Statuses: nothing else is written
            raise ValueError(f"status state {changes.get('state') or doc.get('state')!r} is not one of {', '.join(STATES)}")
        if "state" in changes:
            changes.setdefault("state_mode", self.mode)
            if changes["state"] == "published":
                # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): `published` clears plan, plan_outcome and
                # plan_reason. Why: they predict what an invocation would do; once the run id is published the
                # prediction is void, and a stale `waiting_for_key` made the next plan run exit 3 for a published topic.
                for name in PLAN_FIELDS:
                    changes.setdefault(name, None)
        for name in ("reason", "plan_reason"):
            if name in changes:
                changes[name] = clean_reason(changes[name], self.redactor)
        for k, v in changes.items():
            if v is None:
                doc.pop(k, None)
            else:
                doc[k] = v
        doc["updated_at"] = now_iso()
        ordered = {k: doc[k] for k in ("topic", "date", "state", "state_mode", "run_id", "started_at", "updated_at", "attempts") if k in doc}
        ordered.update({k: v for k, v in doc.items() if k not in ordered})
        write_json_atomic(self.record_path(topic), ordered)
        if self.mode == "live" and topic not in self.pinned:  # decision above
            self._write_public(topic, ordered)
        return ordered


# ---------------------------------------------------------------------------------------------------------------------
# running child processes


@dataclass
class Ctx:
    date: str
    attempt: int
    out: Path
    log_dir: Path
    status_dir: Path
    dry_out: Path
    live_cmd: list[str]
    dry_cmd: list[str]
    workdir: Path
    env_file: Path | None
    key_values: dict[str, str]
    blank: list[str]
    redactor: Redactor
    timeout_s: float | None
    factor: float
    procs: dict[int, subprocess.Popen] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    stopping: threading.Event = field(default_factory=threading.Event)

    def say(self, msg: str) -> None:
        line = self.redactor.text(f"{datetime.now(timezone.utc).strftime('%H:%M:%SZ')} {msg}")
        with self.lock:
            print(line, flush=True)
            try:
                self.log_dir.mkdir(parents=True, exist_ok=True)
                with (self.log_dir / f"{self.date}_runner.log").open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                pass


def _child_env(ctx: Ctx, key: Key | None) -> dict[str, str]:
    """The environment of one child process.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): every key variable the runner knows (the --keys names and every
    MODEL_API_KEY_* in the environment or the .env) is set to "" in a child's environment, and a live child on a key
    gets MODEL_API_KEY = that key's value; the child's own load_dotenv(override=False) then cannot fill them back in.
    Why: one key per process (reasoning/README.md budget rules): a run must not hold another account's key, and the
    value never goes through a command line, a log or a status file."""
    env = dict(os.environ)
    for name in ctx.blank:
        env[name] = ""
    if key is not None and key.inject:
        env["MODEL_API_KEY"] = ctx.key_values[key.name]
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def _reap(proc: subprocess.Popen, wait_s: float = 30.0) -> None:
    """Kills `proc` and waits (at most `wait_s`) until it has exited."""
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=wait_s)
    except subprocess.TimeoutExpired:
        pass


def stop_children(ctx: Ctx, grace_s: float = 10.0) -> None:
    """Stops every running child and waits until each has exited (killed when it has not after `grace_s`).

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): `ctx.stopping` is set first and a child registered after the
    listing kills itself (_pump), so no child starts behind the stop. Why: a worker may be between its thread start and
    its Popen when the main thread fails; that child would run unsupervised after the runner has gone."""
    ctx.stopping.set()
    with ctx.lock:
        procs = list(ctx.procs.values())
    for p in procs:
        try:
            p.terminate()
        except OSError:
            pass
    deadline = time.monotonic() + grace_s
    for p in procs:
        try:
            p.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            _reap(p, 5.0)


def _pump(ctx: Ctx, argv: list[str], env: dict[str, str], log_path: Path, header: str,
          timeout_s: float | None = None) -> tuple[int | None, list[str], str | None]:
    """Runs one child, its stdout+stderr redacted into `log_path`. Returns (exit code or None, last lines, why it did
    not end on its own: could not start, timed out, interrupted)."""
    tail: deque[str] = deque(maxlen=60)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        log.write(ctx.redactor.raw(header.encode("utf-8")) + b"\n")
        log.flush()
        try:
            proc = subprocess.Popen(argv, cwd=str(ctx.workdir), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        except OSError as exc:
            log.write(f"could not start: {type(exc).__name__}\n".encode())
            return None, [], f"could not start the run: {type(exc).__name__}"
        with ctx.lock:
            ctx.procs[proc.pid] = proc
            late = ctx.stopping.is_set()
        if late:  # the runner began stopping its children while this one started (decision at stop_children)
            _reap(proc)
        timer = None
        timed_out = threading.Event()
        if timeout_s:
            def _kill() -> None:
                timed_out.set()
                proc.kill()
            timer = threading.Timer(timeout_s, _kill)
            timer.daemon = True
            timer.start()
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                clean = ctx.redactor.raw(raw)
                log.write(clean)
                log.flush()
                text = clean.decode("utf-8", "replace").rstrip()
                if text:
                    tail.append(text)
            rc = proc.wait()
        except BaseException:
            # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a fault while pumping a child's output (a log write,
            # the redaction) kills the child and waits for it before the error goes on. Why: the caller records the
            # topic failed and frees its key; a child left alive went on spending on that key next to the next run.
            _reap(proc)
            raise
        finally:
            if timer:
                timer.cancel()
            with ctx.lock:
                ctx.procs.pop(proc.pid, None)
        log.write(f"--- exit {rc} at {now_iso()}\n".encode())
        if timed_out.is_set():
            return rc, list(tail), f"timed out after {timeout_s / 60:g} min and was stopped (the checkpoint is kept)"
        if ctx.stopping.is_set():
            return rc, list(tail), "interrupted with the runner (the checkpoint is kept)"
    return rc, list(tail), None


def failure_line(tail: list[str]) -> str | None:
    for line in reversed(tail):
        if line.startswith(("refusing to run:", "refusing to continue:")):
            return line
    for line in reversed(tail):
        if re.match(r"^[A-Za-z_][\w.]*(Error|Exception|Abort|Exit|Interrupt)\b", line):
            return line
    return tail[-1] if tail else None


def dry_check(ctx: Ctx, topic: str) -> dict[str, Any]:
    """Runs scripts/dry_check.py for one topic; returns its report (or {"error": ...})."""
    report_path = ctx.dry_out / "_estimates" / ctx.date / f"{topic}.json"
    try:
        report_path.unlink()
    except OSError:
        pass
    argv = ctx.dry_cmd + ["--topic", topic, "--date", ctx.date, "--out", str(ctx.dry_out), "--report", str(report_path)]
    if ctx.blank:
        argv += ["--blank", ",".join(ctx.blank)]
    if ctx.env_file:
        argv += ["--env-file", str(ctx.env_file)]
    env = _child_env(ctx, None)
    env["QUORUM_DRY_RUN"] = "1"
    for name in ("MODEL_API_KEY", "METERLESS_TOKEN", "METERLESS_RUNTIME_TOKEN"):
        env[name] = ""
    log_name = f"{ctx.date}_{topic}_dry.log"
    rc, tail, start_error = _pump(ctx, argv, env, ctx.log_dir / log_name, f"=== dry check {topic} {ctx.date} at {now_iso()} ===")
    if start_error:
        return {"error": start_error, "log": log_name}
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report = {"error": f"dry check exit {rc}: {failure_line(tail) or 'no report'}"}
    if rc != 0 and "error" not in report:
        report["error"] = f"dry check exit {rc}: {failure_line(tail) or 'no output'}"
    report["log"] = log_name
    return report


def scaled_estimate(calls: dict[str, Any], factor: float) -> tuple[int, int]:
    """(fast, ultra) estimate from a dry check's counts (decision at ESTIMATE_FACTOR)."""
    fast = math.ceil(int(calls.get("fast") or 0) * factor)
    ultra = math.ceil(int(calls.get("ultra") or 0) * factor)
    return fast, max(ultra, math.ceil(fast * ULTRA_FLOOR_SHARE))


@dataclass
class RunResult:
    exit_code: int | None
    used: tuple[int, int]
    published: tuple[int, str | None] | None
    reason: str | None
    log: str
    resume: bool
    started_at: str
    ended_at: str


def live_args(topic: str, edition_date: str, out: Path, attempt: int, resume: bool) -> list[str]:
    """The run.py arguments of one live run (`python -m quorum_reasoning.run` + these)."""
    args = ["--topic", topic, "--date", edition_date, "--model", "live", "--corpus", "zetaris", "--out", str(out),
            "--attempt", str(attempt), "--verbose"]
    return args + (["--resume"] if resume else [])


def live_run(ctx: Ctx, item: Item, key: Key, n: int) -> RunResult:
    rid = run_id(item.topic, ctx.date, ctx.attempt)
    resume = item.resume or checkpoint_has_thread(ctx.out, rid)
    before_rows = journal_counts(ctx.out, rid)
    before_version = latest_version(ctx.out, item.topic, ctx.date)
    argv = ctx.live_cmd + live_args(item.topic, ctx.date, ctx.out, ctx.attempt, resume)
    log_name = run_log_name(ctx.date, item.topic, ctx.attempt, n, key.name)  # decision at run_log_name
    started = now_iso()
    header = f"=== run {n} of {rid} on {key.name}{' (resume)' if resume else ''} at {started} ==="
    try:
        rc, tail, error = _pump(ctx, argv, _child_env(ctx, key), ctx.log_dir / log_name, header, ctx.timeout_s)
    except Exception as exc:  # noqa: BLE001 — a runner fault fails this topic, not the others
        rc, tail, error = None, [], f"runner error: {type(exc).__name__}: {exc}"
    after_rows = journal_counts(ctx.out, rid)
    used = (max(0, after_rows[0] - before_rows[0]), max(0, after_rows[1] - before_rows[1]))
    published = None
    if rc in (0, 2) and not error:
        published = published_by(ctx.out, item.topic, ctx.date, rid, after=before_version)
        if published is None and rc == 0:
            published = published_by(ctx.out, item.topic, ctx.date, rid)  # "had already finished and published"
    reason = error
    if reason is None and published is None and rc != 3:
        line = failure_line(tail)
        if rc == 0:
            reason = f"exit 0 but the store holds no snapshot of run {rid}"
        else:
            reason = f"exit {rc}: {line}" if line else f"exit {rc}"
    return RunResult(rc, used, published, reason, log_name, resume, started, now_iso())


# ---------------------------------------------------------------------------------------------------------------------
# the CLI


def parse_keys(spec: str | None, fast_cap: int, ultra_cap: int) -> list[Key]:
    """NAME[=FAST[/ULTRA]], comma-separated; NAME is an environment variable name, never a value."""
    if not spec:
        return [Key(ROUTE, fast_cap, ultra_cap, inject=False)]
    keys: list[Key] = []
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        name, _, caps = part.partition("=")
        name = name.strip()
        if not ENV_NAME.match(name):
            raise ValueError("--keys takes environment variable NAMES (letters, digits, underscores); one entry is not a name "
                             "(not echoed, in case it is a key value)")
        cf, cu = fast_cap, ultra_cap
        if caps:
            f, _, u = caps.partition("/")
            try:
                cf = int(f)
                cu = int(u) if u else ultra_cap
            except ValueError:
                raise ValueError(f"--keys {name}=FAST[/ULTRA]: the caps must be integers") from None
        if cf < 1 or cu < 1:
            raise ValueError(f"--keys {name}: caps must be at least 1")
        if any(k.name == name for k in keys):
            raise ValueError(f"--keys lists {name} twice")
        keys.append(Key(name, cf, cu))
    if not keys:
        raise ValueError("--keys is empty")
    return keys


def read_env_file(path: Path | None) -> dict[str, str]:
    if not path or not path.is_file():
        return {}
    from dotenv import dotenv_values

    return {k: v for k, v in dotenv_values(path).items() if isinstance(v, str)}


def resolve_value(name: str, file_values: dict[str, str]) -> str:
    """An exported variable wins over .env, as in llm._env (load_dotenv with override=False)."""
    return (os.environ.get(name) or "").strip() or (file_values.get(name) or "").strip()


def list_db_topics(ctx: Ctx) -> dict[str, Any]:
    """collection's topics table through `dry_check.py --list-topics`: {"topics": [ids], "filtered": bool (active rows in
    collection order), "skipped": [{"id", "reason"}]}. A listed id that breaks the shared rule or is a Windows device name
    moves to skipped (decisions at topic_id_problem)."""
    argv = ctx.dry_cmd + ["--list-topics"] + (["--env-file", str(ctx.env_file)] if ctx.env_file else [])
    env = _child_env(ctx, None)
    for name in ("MODEL_API_KEY", "METERLESS_TOKEN", "METERLESS_RUNTIME_TOKEN"):
        env[name] = ""
    proc = subprocess.run(argv, cwd=str(ctx.workdir), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(clean_reason(proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else f"exit {proc.returncode}", ctx.redactor))
    lines = proc.stdout.strip().splitlines()
    doc = json.loads(lines[-1]) if lines else None
    if not isinstance(doc, dict) or not isinstance(doc.get("topics"), list):
        raise RuntimeError("dry_check.py --list-topics printed no topic listing")
    topics: list[str] = []
    skipped = [s for s in (doc.get("skipped") or []) if isinstance(s, dict)]
    for t in doc["topics"]:
        problem = topic_id_problem(t)
        if problem is None:
            if t not in topics:
                topics.append(t)
        else:
            skipped.append({"id": str(t)[:64], "reason": problem})
    return {"topics": topics, "filtered": doc.get("filtered") is True, "skipped": skipped}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Run one date's editions for a list of topics with key rotation (dry checks only unless --live).")
    ap.add_argument("--date", required=True, help="edition date, YYYY-MM-DD")
    ap.add_argument("--topics", required=True, help="comma-separated topic ids (each must be a row of collection's topics table), or 'all' "
                                                    "for every row (plan only until Zetaris registers topics.active and created_at)")
    ap.add_argument("--keys", default=None, help="comma-separated environment variable NAMES holding direct-route keys, each NAME[=FAST[/ULTRA]] "
                                                 "to set its caps; omit to run every topic on the route in .env as it is (one worker, nothing injected)")
    ap.add_argument("--out", required=True, help="the live snapshot store (run.py --out)")
    ap.add_argument("--log-dir", required=True)
    ap.add_argument("--status-dir", required=True)
    ap.add_argument("--dry-check-out", required=True, help="scratch store for the dry checks' stand-in snapshots (never inside --out)")
    ap.add_argument("--max-calls-per-key", type=int, default=FAST_CAP, help=f"fast-lane calls per key and invocation (default {FAST_CAP})")
    ap.add_argument("--max-ultra-calls-per-key", type=int, default=ULTRA_CAP, help=f"Ultra calls per key and invocation (default {ULTRA_CAP})")
    ap.add_argument("--estimate-factor", type=float, default=ESTIMATE_FACTOR, help=f"dry-check count x this = the estimate (default {ESTIMATE_FACTOR})")
    ap.add_argument("--attempt", type=int, default=1, help="run.py --attempt for every topic (default 1)")
    ap.add_argument("--live", action="store_true", help="start the live runs (paid); without it only the dry checks and the plan run")
    ap.add_argument("--allow-before-cut", action="store_true", help="with --live: allow a start before the edition cut (05:30 New York); rehearsals only")
    ap.add_argument("--env-file", default=None, help="the .env the key values (and the dry checks' Zetaris settings) come from; default <repo>/.env. "
                                                     "A live run always reads <repo>/.env itself, so --live refuses another file")
    ap.add_argument("--dry-jobs", type=int, default=2, help="dry checks in parallel (default 2)")
    ap.add_argument("--run-timeout-min", type=float, default=0.0, help="stop a live run after this many minutes (0 = no limit); its checkpoint is kept")
    ap.add_argument("--python", default=sys.executable, help="interpreter for the child processes (default: this one)")
    return ap


def main(argv: list[str] | None = None, *, live_cmd: list[str] | None = None, dry_cmd: list[str] | None = None) -> int:
    """`live_cmd` / `dry_cmd` replace the child command prefixes (tests inject fakes); the runner appends the arguments."""
    ap = build_parser()
    args = ap.parse_args(argv)

    def refuse(msg: str) -> int:
        print(f"refusing to run: {msg}", file=sys.stderr)
        return 2

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        return refuse("--date must be YYYY-MM-DD")
    try:
        Date.fromisoformat(args.date)
    except ValueError:
        return refuse("--date is not a calendar date")
    if args.attempt < 1:
        return refuse("--attempt must be at least 1")
    if args.max_calls_per_key < 1 or args.max_ultra_calls_per_key < 1:
        return refuse("the per-key caps must be at least 1")
    if not (args.estimate_factor > 0 and math.isfinite(args.estimate_factor)):
        return refuse("--estimate-factor must be a positive number")
    try:
        keys = parse_keys(args.keys, args.max_calls_per_key, args.max_ultra_calls_per_key)
    except ValueError as exc:
        return refuse(str(exc))
    topics_arg = args.topics.strip()
    topics: list[str] = []
    if topics_arg != "all":
        for t in [t.strip() for t in topics_arg.split(",") if t.strip()]:
            problem = topic_id_problem(t)
            if problem == DEVICE_REASON:
                return refuse(f"--topics {t[:64]!r} is {DEVICE_REASON}")
            if problem:
                return refuse(f"a topic id follows the shared rule {TOPIC_RULE} (lower-case letters, digits, hyphens; "
                              f"at most 64 characters): {t[:64]!r}")
            if t not in topics:
                topics.append(t)
        if not topics:
            return refuse("--topics is empty")
    # absolute: the children run with cwd = reasoning/, the runner wherever it was started
    out, log_dir, status_dir, dry_out = (Path(p).resolve() for p in (args.out, args.log_dir, args.status_dir, args.dry_check_out))
    # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): --dry-check-out may not be, contain or sit inside --out. Why: the
    # dry checks publish stand-in snapshots; in the live store they would become a "latest" version the portal reads,
    # and a dry run labelled live is the one outcome that passes for integration evidence (run.live_mode_problem).
    if _overlaps(out, dry_out):
        return refuse("--dry-check-out must be a separate scratch folder, neither --out nor inside it (dry checks publish stand-in snapshots)")
    env_file = (Path(args.env_file) if args.env_file else Path(DEFAULT_ENV_FILE)).resolve()
    if args.live and env_file.resolve() != Path(DEFAULT_ENV_FILE).resolve():
        return refuse(f"a live run reads the repository's .env itself; --env-file is for dry checks only (drop it with --live)")
    file_values = read_env_file(env_file)

    # key values: read here, handed to one child each, never printed (decision at _child_env)
    key_values: dict[str, str] = {}
    unusable: list[str] = []
    for k in keys:
        if not k.inject:
            continue
        v = resolve_value(k.name, file_values)
        if len(v) < MIN_KEY_CHARS:
            unusable.append(k.name)
        else:
            key_values[k.name] = v
    blank = sorted({k.name for k in keys if k.inject}
                   | {n for n in (*os.environ.keys(), *file_values.keys()) if EXTRA_KEY_NAME.match(n)})
    secrets = set(key_values.values())
    for source in (file_values, os.environ):
        secrets |= {v for n, v in source.items() if SECRET_NAME.search(n) and isinstance(v, str)}
    redactor = Redactor(secrets)

    if args.live:
        if unusable:
            return refuse(f"no usable value for {', '.join(unusable)} (exported or in .env); list only keys that are set")
        if any(k.inject for k in keys):
            from quorum_reasoning import llm

            base = resolve_value("MODEL_BASE_URL", file_values)
            if not base or not llm._is_direct_url(base):
                return refuse("--keys sets MODEL_API_KEY, which only the direct NVIDIA route uses (MODEL_BASE_URL on nvidia.com); "
                              "on the Meterless route run without --keys")
        cut = edition_cut_utc(args.date)
        if datetime.now(timezone.utc) < cut and not args.allow_before_cut:
            return refuse(f"the edition {args.date} is cut at {cut.strftime('%Y-%m-%dT%H:%MZ')} (05:30 New York); a run before it misses part "
                          "of the day (pass --allow-before-cut for a rehearsal)")

    ctx = Ctx(date=args.date, attempt=args.attempt, out=out, log_dir=log_dir, status_dir=status_dir, dry_out=dry_out,
              live_cmd=live_cmd or [args.python, "-X", "utf8", "-m", "quorum_reasoning.run"],
              dry_cmd=dry_cmd or [args.python, "-X", "utf8", str(SCRIPTS / "dry_check.py")],
              workdir=REASONING, env_file=env_file if env_file.is_file() else None, key_values=key_values, blank=blank,
              redactor=redactor, timeout_s=args.run_timeout_min * 60 if args.run_timeout_min > 0 else None,
              factor=args.estimate_factor)

    lock = runner_dir(status_dir, args.date) / ".runner.lock"
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return refuse(f"another runner holds the lock for {args.date} in --status-dir (or a crashed one left it): "
                      f"delete {RUNNER_DIR}/{args.date}/.runner.lock there once no runner is running")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"pid": os.getpid(), "started_at": now_iso(), "live": bool(args.live)}, fh)
    try:
        return _run(ctx, args, keys, topics, unusable)
    except KeyboardInterrupt:
        stop_children(ctx)
        print("interrupted: running children stopped; their checkpoints are kept (rerun the same command to resume)", file=sys.stderr)
        return 130
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def _run(ctx: Ctx, args: argparse.Namespace, keys: list[Key], topics: list[str], unusable: list[str]) -> int:
    mode = "live" if args.live else "dry"
    started_at = now_iso()
    try:
        listing = list_db_topics(ctx)
    except Exception as exc:  # noqa: BLE001
        print(f"refusing to run: could not read collection's topics table: {exc}", file=sys.stderr)
        return 2
    rows: list[str] = listing["topics"]
    skipped: list[dict[str, Any]] = listing["skipped"]
    row_word = "an active row" if listing["filtered"] else "a row"
    not_rows: set[str] = set()
    if not topics:  # --topics all
        # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): `--topics all --live` is refused while the listing is
        # unfiltered (decision at dry_check.list_topics). Why: retired rows would each get a paid ~1 500-call run, in
        # no set order, while the order given decides what is finished first.
        if args.live and not listing["filtered"]:
            print("refusing to run: --topics all with --live needs topics.active and topics.created_at through Zetaris (retired "
                  "topics, collection order), which are not registered there yet; list the topics in priority order instead, "
                  "or drop --live to plan", file=sys.stderr)
            return 2
        topics = list(rows)
        if not topics and not skipped:
            print("refusing to run: collection's topics table is empty", file=sys.stderr)
            return 2
    else:
        not_rows = {t for t in topics if t not in set(rows)}
    ctx.say(f"run_editions {mode}: {args.date}, {len(topics)} topics ({', '.join(topics)}); keys: "
            + ", ".join(f"{k.name} {k.cap_fast}/{k.cap_ultra}" for k in keys)
            + (f"; not usable (no value): {', '.join(unusable)}" if unusable else ""))
    if datetime.now(timezone.utc) < edition_cut_utc(args.date):
        ctx.say(f"note: before the edition cut ({edition_cut_utc(args.date).strftime('%Y-%m-%dT%H:%MZ')}): the day's corpus is not complete yet")
    if args.topics.strip() == "all" and not listing["filtered"]:
        ctx.say("note: Zetaris shows no topics.active / created_at: 'all' is every row in no set order, retired topics included")
    for s in skipped:
        ctx.say(f"skipped a topics row {s.get('id')!r}: {s.get('reason')}")
    statuses = Statuses(ctx.status_dir, ctx.date, ctx.redactor, mode, attempt=ctx.attempt)
    usable_keys = [k for k in keys if not k.inject or k.name in ctx.key_values]  # live mode refused unusable ones already

    # 1. what is not a row, what is already published, and the dry checks for the rest
    todo: list[str] = []
    final: dict[str, dict[str, Any]] = {}
    for topic in topics:
        rid = run_id(topic, ctx.date, ctx.attempt)
        statuses.open(topic, rid)
        shown = statuses.follow_store(topic, latest_snapshot(ctx.out, topic, ctx.date))  # live mode only
        if shown:
            ctx.say(f"{topic}: its status file keeps the published version of run {shown} until run {rid} publishes; "
                    "this run's states go to the runner's record")
        if topic in statuses.kept:
            ctx.say(f"{topic}: its status keeps the live outcome {statuses.docs[topic].get('state')!r}; the plan goes to plan / plan_outcome")
        if topic in not_rows:
            final[topic] = statuses.verdict(topic, "failed", f"not {row_word} in collection's topics table: nothing is "
                                            "collected under it (add the row, e.g. with topics --suggest --sql, then rerun)", plan=None)
            ctx.say(f"{topic}: failed, not {row_word} in collection's topics table")
            continue
        done = published_by(ctx.out, topic, ctx.date, rid)
        if done:  # a snapshot of this run id in the live store is a live outcome, whichever mode found it
            statuses.keep_published(topic)  # live mode: a pair that already says so stays byte-identical
            final[topic] = statuses.save(topic, state="published", state_mode="live", version=done[0], snapshot_status=done[1],
                                         reason="already published by an earlier run", exit_code=None)
            ctx.say(f"{topic}: already published (version {done[0]}), skipped")
            continue
        if topic not in statuses.kept:
            statuses.save(topic, state="queued", reason="dry check running")
        todo.append(topic)

    reports: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.dry_jobs)) as pool:
        for topic, report in zip(todo, pool.map(lambda t: dry_check(ctx, t), todo)):
            reports[topic] = report

    items: list[Item] = []
    for topic in todo:
        report = reports[topic]
        rid = run_id(topic, ctx.date, ctx.attempt)
        if report.get("error") or not isinstance(report.get("calls"), dict):
            final[topic] = statuses.verdict(topic, "failed", f"dry check failed: {report.get('error') or 'no counts'}",
                                            dry_check_log=report.get("log"), plan=None)
            ctx.say(f"{topic}: dry check failed ({final[topic].get('plan_reason' if topic in statuses.kept else 'reason')})")
            continue
        est_f, est_u = scaled_estimate(report["calls"], ctx.factor)
        done_f, done_u = journal_counts(ctx.out, rid)
        item = Item(topic, est_f, est_u, done_f, done_u, resume=checkpoint_has_thread(ctx.out, rid))
        items.append(item)
        statuses.save(topic, calls_estimate=est_f + est_u, calls_estimate_lanes={"fast": est_f, "ultra": est_u},
                      calls_dry_check={"fast": report["calls"].get("fast"), "ultra": report["calls"].get("ultra")},
                      calls_done={"fast": done_f, "ultra": done_u} if (done_f or done_u) else None,
                      dry_check_log=report.get("log"))
        ctx.say(f"{topic}: dry check {report['calls'].get('fast')}/{report['calls'].get('ultra')} calls (fast/Ultra), "
                f"estimate {est_f}/{est_u}" + (f", {done_f}/{done_u} already done" if (done_f or done_u) else "")
                + (", resumes its checkpoint" if item.resume else ""))

    # 2. the plan
    plan = simulate(usable_keys, items) if usable_keys else {i.topic: {"segments": [], "outcome": "waiting_for_key", "reason": "no usable key"} for i in items}
    for item in items:
        entry = plan[item.topic]
        ctx.say(f"plan {item.topic}: {describe_plan(entry)}")
        if mode == "dry":
            final[item.topic] = statuses.verdict(item.topic, "queued", f"dry check only (no --live); plan: {describe_plan(entry)}",
                                                 plan=entry["segments"], plan_outcome=entry["outcome"])
        else:
            statuses.save(item.topic, state="queued", plan=entry["segments"], plan_outcome=entry["outcome"], reason=None)

    if mode == "live":
        _drive(ctx, statuses, usable_keys, items, final)
    return _summary(ctx, args, mode, started_at, topics, final, keys, plan, skipped)


def _drive(ctx: Ctx, statuses: Statuses, keys: list[Key], items: list[Item], final: dict[str, dict[str, Any]]) -> None:
    """One process per key at a time; the main thread places work and writes every status, workers only run children."""
    planner = Planner(keys, items)
    done_q: queue.Queue[tuple[Item, Key, tuple[int, int], RunResult]] = queue.Queue()
    running = 0

    def worker(item: Item, key: Key, res: tuple[int, int], n: int) -> None:
        try:
            result = live_run(ctx, item, key, n)
        except Exception as exc:  # noqa: BLE001
            result = RunResult(None, (0, 0), None, f"runner error: {type(exc).__name__}: {exc}", "", item.resume, now_iso(), now_iso())
        done_q.put((item, key, res, result))

    try:
        while True:
            for item, key, res in planner.place():
                doc = statuses.docs[item.topic]
                n = int(doc.get("attempts") or 0) + 1
                resume = item.resume or checkpoint_has_thread(ctx.out, run_id(item.topic, ctx.date, ctx.attempt))
                log_name = run_log_name(ctx.date, item.topic, ctx.attempt, n, key.name)  # the file live_run writes
                # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): `started_at` is the first live start of the run
                # id; until then it is when its status was first written. Why: the portal shows `running` and
                # `waiting_for_key` as "being prepared since started_at"; a plan run hours earlier must not date it.
                # (superseded 2026-10-26, closing review round 2: "until then" is when a live invocation first queued
                # the run id, never a plan run's time; decision at Statuses.open)
                first = {"started_at": now_iso(), "started_mode": "live"} if n == 1 and not doc.get("runs") else {}
                statuses.save(item.topic, state="running", attempts=n, key=key.name, log=log_name, reason=None,
                              reserved={"fast": res[0], "ultra": res[1]}, **first)
                ctx.say(f"start {item.topic} on {key.name}{' (resume)' if resume else ''}, reserved {res[0]}/{res[1]}, log {log_name}")
                threading.Thread(target=worker, args=(item, key, res, n), daemon=True).start()
                running += 1
            for item, reason in planner.take_waiting():
                final[item.topic] = statuses.save(item.topic, state="waiting_for_key", reason=reason, key=None, reserved=None)
                ctx.say(f"{item.topic}: waiting for a key ({final[item.topic].get('reason')})")
            if running == 0:
                break
            try:
                got = done_q.get(timeout=1.0)
            except queue.Empty:
                continue
            running -= 1
            _record(ctx, statuses, planner, final, *got)
    except BaseException:
        # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): every way out of this loop (Ctrl-C, a status write that
        # fails, a bug) stops the live children and waits for them, then records what they left (their checkpoints
        # stay; a rerun resumes them) and lets the error go on. Why: only Ctrl-C did; any other error left paid children
        # running unsupervised, their status on `running` and the lock gone, so a rerun resumed the run id beside them.
        stop_children(ctx)
        deadline = time.monotonic() + 30
        while running and time.monotonic() < deadline:
            try:
                got = done_q.get(timeout=1.0)
            except queue.Empty:
                continue
            running -= 1
            try:
                _record(ctx, statuses, planner, final, *got, requeue=False)
            except Exception:  # noqa: BLE001 — the fault that ended the loop may fail this write too; the stop came first
                pass
        raise


def _record(ctx: Ctx, statuses: Statuses, planner: Planner, final: dict[str, dict[str, Any]],
            item: Item, key: Key, res: tuple[int, int], result: RunResult, requeue: bool = True) -> None:
    """One finished run: its outcome into the planner and the topic's status file.

    DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): exit 2 counts as published when the store holds a new version of
    this run id (run.py exits 2 for a `partial` snapshot after publishing it), with snapshot_status and a reason saying
    partial; exit 2 without one (a refusal) is failed. Why: the partial version is already latest.json for the portal,
    so "failed" would misreport what readers see; the brief's "exit 2 -> failed" holds for refusals."""
    if result.exit_code == 3 and not result.reason:
        outcome = "drained"
    elif result.published:
        outcome = "published"
    else:
        outcome = "failed"
    planner.finish(item, key, res, outcome, result.used)
    doc = statuses.docs[item.topic]
    runs = list(doc.get("runs") or [])
    runs.append({"n": doc.get("attempts"), "key": key.name, "resume": result.resume, "started_at": result.started_at,
                 "ended_at": result.ended_at, "exit_code": result.exit_code, "outcome": outcome,
                 "calls": {"fast": result.used[0], "ultra": result.used[1]}, "log": result.log})
    common = {"runs": runs, "reserved": None, "calls_done": {"fast": item.done_fast, "ultra": item.done_ultra}}
    if outcome == "published":
        version, snap_status = result.published  # type: ignore[misc]
        statuses.follow_store(item.topic, latest_snapshot(ctx.out, item.topic, ctx.date))  # its own version is the newest now
        partial = result.exit_code == 2 or snap_status == "partial"
        final[item.topic] = statuses.save(item.topic, state="published", version=version, snapshot_status=snap_status,
                                          reason="published as partial: a node recorded an error (see the snapshot's errors)" if partial else None, **common)
        ctx.say(f"{item.topic}: published version {version} ({snap_status}) on {key.name}, {result.used[0]}/{result.used[1]} calls")
    elif outcome == "drained" and not requeue:
        final[item.topic] = statuses.save(item.topic, state="waiting_for_key", reason=f"{key.name} drained (exit 3) while the runner was "
                                          "interrupted; rerun the same command to resume", **common)
    elif outcome == "drained":
        statuses.save(item.topic, state="queued", reason=f"{key.name} drained (exit 3) after {result.used[0]}/{result.used[1]} calls; "
                                                         "queued to resume on another key", **common)
        ctx.say(f"{item.topic}: {key.name} drained after {result.used[0]}/{result.used[1]} calls; requeued with --resume")
    else:
        final[item.topic] = statuses.save(item.topic, state="failed", reason=result.reason, exit_code=result.exit_code, **common)
        ctx.say(f"{item.topic}: failed on {key.name} ({final[item.topic].get('reason')})")


def _summary(ctx: Ctx, args: argparse.Namespace, mode: str, started_at: str, topics: list[str],
             final: dict[str, dict[str, Any]], keys: list[Key], plan: dict[str, dict[str, Any]],
             skipped: list[dict[str, Any]] | None = None) -> int:
    rows = []
    for t in topics:
        doc = final.get(t) or ctx_status(ctx, t)
        rows.append({"topic": t, "state": doc.get("state"), "state_mode": doc.get("state_mode"), "calls_estimate": doc.get("calls_estimate_lanes"),
                     "version": doc.get("version"), "attempts": doc.get("attempts"), "reason": doc.get("reason"),
                     "plan_outcome": doc.get("plan_outcome")})
    for s in skipped or []:  # no status file: the id is not safe as a file name
        rows.append({"topic": str(s.get("id"))[:64], "state": "failed", "state_mode": mode, "calls_estimate": None, "version": None, "attempts": None,
                     "reason": f"topics row skipped, not run: {s.get('reason')}", "plan_outcome": None, "skipped_row": True})
    summary = {"date": ctx.date, "mode": mode, "started_at": started_at, "ended_at": now_iso(),
               "keys": [{"name": k.name, "cap_fast": k.cap_fast, "cap_ultra": k.cap_ultra, "used_fast": k.used_fast,
                         "used_ultra": k.used_ultra, "drained": k.drained, "usable": (not k.inject) or k.name in ctx.key_values} for k in keys],
               "topics": rows}
    write_json_atomic(runner_dir(ctx.status_dir, ctx.date) / "_summary.json", summary)
    ctx.say(f"summary ({mode}, {ctx.date}):")
    for r in rows:
        est = r["calls_estimate"] or {}
        name = repr(r["topic"]) if r.get("skipped_row") else r["topic"]
        ctx.say(f"  {name:<32} {r['state'] or '-':<16} est {est.get('fast', '-')}/{est.get('ultra', '-')}"
                + (f"  v{r['version']}" if r["version"] else "") + (f"  ({r['reason']})" if r["reason"] else ""))
    states = [r["state"] for r in rows]
    if "failed" in states or (mode == "dry" and any(r["plan_outcome"] == "failed" for r in rows)):
        return 1
    if mode == "dry":  # a kept live outcome counts as it would in live mode (decision at Statuses.open)
        live_open = any(r["state_mode"] == "live" and r["state"] in ("waiting_for_key", "queued", "running") for r in rows)
        return 3 if live_open or any(r["plan_outcome"] == "waiting_for_key" for r in rows) else 0
    if "waiting_for_key" in states or "queued" in states or "running" in states:
        return 3
    return 0


def ctx_status(ctx: Ctx, topic: str) -> dict[str, Any]:
    try:
        doc = json.loads(record_file(ctx.status_dir, ctx.date, topic, ctx.attempt).read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


if __name__ == "__main__":
    sys.exit(main())
