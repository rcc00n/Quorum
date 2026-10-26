"""scripts/run_editions.py, scripts/dry_check.py and scripts/resume_with_next_key.sh, fully offline: fake child commands
stand in for run.py and the dry check (exit 0 / 2 / 3 / 1, slow, crash); no model, no Zetaris, no control plane is ever
reached. Every live test runs with QUORUM_DRY_RUN=1 and the model credentials blank, so a real run.py reached by
mistake refuses (exit 2) instead of spending anything."""

from __future__ import annotations

import _thread
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

REASONING = Path(__file__).resolve().parents[1]
SCRIPTS = REASONING / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


re_mod = _load("run_editions")
dc_mod = _load("dry_check")

PUBLIC_FIELDS = ("topic", "date", "state", "run_id", "started_at", "updated_at", "attempts", "reason")  # the portal's contract
DATE = "2026-10-20"  # its cut (2026-10-20 09:30Z) has passed, so --live needs no --allow-before-cut
VALUE_A = "fake-key-value-AAAA-0001"
VALUE_B = "fake-key-value-BBBB-0002"
VALUE_C = "fake-key-value-CCCC-0003"

FAKE_RUN = r'''
import json, os, sqlite3, sys, time
from pathlib import Path
args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
topic, date, out, attempt = opt("--topic"), opt("--date"), Path(opt("--out")), int(opt("--attempt", "1"))
rid = f"{date}-{topic}-{attempt}"
sc = json.loads(Path(os.environ["FAKE_SCENARIO"]).read_text())
rec_dir = Path(sc["records"])
rec_dir.mkdir(parents=True, exist_ok=True)
prior = [json.loads(p.read_text()) for p in rec_dir.glob("*.json")]
n = sum(1 for r in prior if r["topic"] == topic)
steps = sc["live"].get(topic, [{"exit": 0}])
step = steps[min(n, len(steps) - 1)]
# what run.py does first: llm._env() loads the repo .env with load_dotenv(override=False)
for line in Path(sc["env_file"]).read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        if k not in os.environ:
            os.environ[k] = v
key = os.environ.get("MODEL_API_KEY", "")
seen = None
sd = os.environ.get("FAKE_STATUS_DIR")
if sd:
    try:
        seen = json.loads((Path(sd) / topic / f"{date}.json").read_text())["state"]  # the portal's status file
    except Exception:
        seen = "unreadable"
rec = {"topic": topic, "argv": args, "resume": "--resume" in args, "key_name": sc["values"].get(key, "?" if key else ""),
       "blank_ok": all(os.environ.get(nm, "") == "" for nm in sc.get("blank_expected", [])), "status_seen": seen,
       "dry_env": os.environ.get("QUORUM_DRY_RUN"), "start": time.time()}
if sc.get("echo_key"):
    print(f"stdout sees MODEL_API_KEY={key}", flush=True)
    print(f"stderr sees {key}", file=sys.stderr, flush=True)
if step.get("echo"):
    print(step["echo"], flush=True)
journal = out / "_journal" / f"{rid}.jsonl"
journal.parent.mkdir(parents=True, exist_ok=True)
with journal.open("a") as fh:
    for lane, k in (("default", step.get("fast", 0)), ("fact_checker", step.get("ultra", 0))):
        for _ in range(k):
            fh.write(json.dumps({"lane": lane, "served": "m", "payload": {"text": "x"}}) + "\n")
if step.get("checkpoint", True):
    cp = out / "_checkpoints" / f"{rid}.sqlite"
    cp.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(cp)
    c.execute("CREATE TABLE IF NOT EXISTS checkpoints (thread_id TEXT)")
    c.execute("INSERT INTO checkpoints VALUES (?)", (rid,))
    c.commit()
    c.close()
time.sleep(step.get("sleep", 0))
rec["end"] = time.time()
tmp = rec_dir / f"{time.time_ns()}-{os.getpid()}.tmp"
tmp.write_text(json.dumps(rec))
os.replace(tmp, rec_dir / f"{time.time_ns()}-{os.getpid()}.json")
if step.get("crash"):
    raise RuntimeError("boom in the fake run")
if step.get("publish", step.get("exit", 0) == 0):
    d = out / topic / date
    d.mkdir(parents=True, exist_ok=True)
    v = 1 + max([int(p.stem[1:]) for p in d.glob("v*.json") if p.stem[1:].isdigit()] or [0])
    snap = {"run_id": rid, "topic_id": topic, "edition_date": date, "status": step.get("status", "ok"), "version": v}
    (d / f"v{v}.json").write_text(json.dumps(snap))
    (d / "latest.json").write_text(json.dumps(snap))
if step.get("say"):
    print(step["say"], file=sys.stderr)
sys.exit(step.get("exit", 0))
'''

FAKE_DRY = r'''
import json, os, sys, time
from pathlib import Path
args = sys.argv[1:]
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
sc = json.loads(Path(os.environ["FAKE_SCENARIO"]).read_text())
if "--list-topics" in args:
    if sc.get("db_error"):
        print("listing topics failed: RuntimeError: Zetaris REST HTTP 503; body withheld", file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"topics": sc["db_topics"], "filtered": sc.get("db_filtered", False), "skipped": sc.get("db_skipped", [])}))
    sys.exit(0)
topic, date, report = opt("--topic"), opt("--date"), opt("--report")
d = sc["dry"].get(topic, {"fast": 100, "ultra": 0})
dry_dir = Path(sc["dry_records"])
dry_dir.mkdir(parents=True, exist_ok=True)
(dry_dir / f"{time.time_ns()}-{os.getpid()}.json").write_text(json.dumps(
    {"topic": topic, "dry_env": os.environ.get("QUORUM_DRY_RUN"), "model_key": os.environ.get("MODEL_API_KEY"),
     "blank": opt("--blank"), "env_file": opt("--env-file")}))
if sc.get("echo_key"):
    print("dry sees " + " ".join(sc["values"]))
if d.get("crash"):
    raise RuntimeError("dry boom")
if d.get("error"):
    rep = {"topic": topic, "date": date, "error": "ConnectionError: zetaris unreachable"}
else:
    rep = {"topic": topic, "date": date, "snapshot_status": "ok",
           "calls": {"total": d["fast"] + d["ultra"], "fast": d["fast"], "ultra": d["ultra"]}}
Path(report).parent.mkdir(parents=True, exist_ok=True)
Path(report).write_text(json.dumps(rep))
sys.exit(1 if d.get("error") else 0)
'''


class Env:
    """One test's world: fake commands, a scenario file, an env file with fake keys, the four directories."""

    def __init__(self, tmp: Path, monkeypatch: pytest.MonkeyPatch):
        self.tmp = tmp
        self.out = tmp / "store"
        self.logs = tmp / "logs"
        self.status = tmp / "status"
        self.dry = tmp / "dry"
        self.records = tmp / "records"  # one file per fake process: parallel appends are not atomic on Windows
        self.dry_records = tmp / "dry_records"
        (tmp / "fake_run.py").write_text(FAKE_RUN)
        (tmp / "fake_dry.py").write_text(FAKE_DRY)
        self.env_file = tmp / ".env"
        self.env_file.write_text(f"QTEST_KEY_A={VALUE_A}\nQTEST_KEY_B={VALUE_B}\nQTEST_KEY_C={VALUE_C}\nMODEL_API_KEY_9=fake-unlisted-key-9999\n"
                                 "QTEST_KEY_EMPTY=\n"
                                 "MODEL_BASE_URL=https://integrate.api.nvidia.com/v1\n")
        monkeypatch.setattr(re_mod, "DEFAULT_ENV_FILE", self.env_file)
        monkeypatch.setenv("MODEL_BASE_URL", "https://integrate.api.nvidia.com/v1")
        # fail closed: if a test ever loses its fake live command, the real run.py refuses --model live under
        # QUORUM_DRY_RUN=1 (exit 2, run.live_mode_problem) and finds no model credential to load from the repo .env
        monkeypatch.setenv("QUORUM_DRY_RUN", "1")
        for name in ("MODEL_API_KEY", "METERLESS_TOKEN", "METERLESS_RUNTIME_TOKEN"):
            monkeypatch.setenv(name, "")
        for name in ("QTEST_KEY_A", "QTEST_KEY_B", "QTEST_KEY_C"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("MODEL_API_KEY_8", "fake-exported-key-8888")  # an exported extra key: blank in every child too
        monkeypatch.setenv("FAKE_SCENARIO", str(tmp / "scenario.json"))
        monkeypatch.setenv("FAKE_STATUS_DIR", str(self.status))
        self.attempt = 1  # --attempt of the last invocation: status_of reads that run id's record
        self.scenario({})

    def scenario(self, live: dict, dry: dict | None = None, **extra) -> None:
        """db_topics None (the default): collection's table holds exactly the topics each invocation lists."""
        sc = {"live": live, "dry": dry or {}, "records": str(self.records), "dry_records": str(self.dry_records), "env_file": str(self.env_file),
              "values": {VALUE_A: "QTEST_KEY_A", VALUE_B: "QTEST_KEY_B", VALUE_C: "QTEST_KEY_C"},
              "blank_expected": ["QTEST_KEY_A", "QTEST_KEY_B", "MODEL_API_KEY_8", "MODEL_API_KEY_9"],  # the --keys names, MODEL_API_KEY_* exported or in .env
              "db_topics": None}
        sc.update(extra)
        self.sc = sc
        (self.tmp / "scenario.json").write_text(json.dumps(sc))

    def argv(self, topics: str, *more: str, keys: str | None = "QTEST_KEY_A,QTEST_KEY_B", live: bool = True) -> list[str]:
        a = ["--date", DATE, "--topics", topics, "--out", str(self.out), "--log-dir", str(self.logs), "--status-dir", str(self.status),
             "--dry-check-out", str(self.dry), "--estimate-factor", "1"]
        if keys:
            a += ["--keys", keys]
        if live:
            a.append("--live")
        return a + list(more)

    def main(self, argv: list[str], live_cmd: list[str] | None = None) -> int:
        sc = dict(self.sc)
        if sc["db_topics"] is None:
            listed = argv[argv.index("--topics") + 1]
            sc["db_topics"] = [] if listed == "all" else [t.strip() for t in listed.split(",") if t.strip()]
        (self.tmp / "scenario.json").write_text(json.dumps(sc))
        self.attempt = int(argv[argv.index("--attempt") + 1]) if "--attempt" in argv else 1
        # -I -S: the fakes need only the standard library, and a bare interpreter starts several times faster on Windows
        return re_mod.main(argv, live_cmd=live_cmd or [sys.executable, "-I", "-S", str(self.tmp / "fake_run.py")],
                           dry_cmd=[sys.executable, "-I", "-S", str(self.tmp / "fake_dry.py")])

    def runs(self) -> list[dict]:
        """Every fake live run, in the order they started."""
        rows = [json.loads(p.read_text()) for p in self.records.glob("*.json")] if self.records.is_dir() else []
        return sorted(rows, key=lambda r: r["start"])

    def dry_runs(self) -> list[dict]:
        return [json.loads(p.read_text()) for p in self.dry_records.glob("*.json")] if self.dry_records.is_dir() else []

    @property
    def runner(self) -> Path:
        """<status-dir>/_runner/<date>/: the runner's records, _summary.json and the lock."""
        return self.status / "_runner" / DATE

    def record_path(self, topic: str, attempt: int | None = None) -> Path:
        """<status-dir>/_runner/<date>/<topic>/<attempt>.json: the runner's record of one run id."""
        return self.runner / topic / f"{attempt or self.attempt}.json"

    def status_of(self, topic: str, attempt: int | None = None) -> dict:
        """The runner's record of the topic's run id (every field it keeps): that of `attempt`, or else of the
        --attempt the last invocation ran."""
        return json.loads(self.record_path(topic, attempt).read_text(encoding="utf-8"))

    def record_files(self) -> list[str]:
        """Every JSON file under <status-dir>/_runner/<date>/, relative to it."""
        return sorted(p.relative_to(self.runner).as_posix() for p in self.runner.rglob("*.json"))

    def public_of(self, topic: str, record: bool = True) -> dict:
        """The portal's status file <status-dir>/<topic>/<date>.json, checked against the contract (Issue #2
        6411408519): exactly the eight fields, a known state, the sha256 file beside it matching its bytes, and, with
        `record`, the same values as the runner's record (not so while it shows another run's published version)."""
        path = self.status / topic / f"{DATE}.json"
        data = path.read_bytes()
        doc = json.loads(data.decode("utf-8"))
        assert list(doc) == list(PUBLIC_FIELDS), doc
        assert doc["state"] in ("queued", "running", "published", "failed", "waiting_for_key"), doc
        assert doc["topic"] == topic and doc["date"] == DATE and isinstance(doc["attempts"], int)
        assert doc["reason"] is None or isinstance(doc["reason"], str)
        sha = (path.parent / f"{DATE}.json.sha256").read_bytes()
        assert sha == f"{hashlib.sha256(data).hexdigest()}  {DATE}.json\n".encode(), sha
        if record:
            rec = self.status_of(topic)
            assert doc == {k: rec.get(k) for k in PUBLIC_FIELDS}, (doc, rec)
        return doc

    def public_pair(self, topic: str) -> tuple[bytes, bytes]:
        """The bytes of the status file and its .sha256."""
        path = self.status / topic / f"{DATE}.json"
        return path.read_bytes(), (path.parent / f"{DATE}.json.sha256").read_bytes()

    def age_public(self, topic: str, updated_at: str = "2026-10-20T11:00:00Z", **fields) -> tuple[bytes, bytes]:
        """Rewrites the status file with an old `updated_at` (and `fields`) and a matching hash, so any later rewrite
        changes its bytes even within the same second; returns the new pair."""
        path = self.status / topic / f"{DATE}.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["updated_at"] = updated_at
        doc.update(fields)
        data = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        path.write_bytes(data)
        (path.parent / f"{DATE}.json.sha256").write_bytes(f"{hashlib.sha256(data).hexdigest()}  {DATE}.json\n".encode())
        return self.public_pair(topic)

    def set_record(self, topic: str, attempt: int | None = None, **fields) -> None:
        """Changes fields of the runner's record, as if an earlier invocation had written them."""
        rec = self.status_of(topic, attempt)
        rec.update(fields)
        self.record_path(topic, attempt).write_text(json.dumps(rec), encoding="utf-8")

    def summary(self) -> dict:
        return json.loads((self.runner / "_summary.json").read_text(encoding="utf-8"))


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    return Env(tmp_path, monkeypatch)


# ---------------------------------------------------------------------------------------------------------------------
# the placement (pure)


def K(name: str, fast: int = 650, ultra: int = 250) -> "re_mod.Key":
    return re_mod.Key(name, fast, ultra)


def test_assignment_spreads_topics_over_keys_with_most_room():
    keys = [K("A"), K("B")]
    p = re_mod.Planner(keys, [re_mod.Item("t1", 300, 30), re_mod.Item("t2", 300, 30), re_mod.Item("t3", 300, 30)])
    started = p.place()
    assert [(i.topic, k.name, res) for i, k, res in started] == [("t1", "A", (300, 30)), ("t2", "B", (300, 30))]
    assert p.pending[0].topic == "t3"  # fits a busy key: waits instead of splitting
    item, key, res = started[0]
    p.finish(item, key, res, "published", (280, 20))  # the journal showed fewer calls than reserved
    assert keys[0].used_fast == 280 and keys[0].used_ultra == 20
    again = p.place()
    assert [(i.topic, k.name) for i, k, _ in again] == [("t3", "A")]


def test_ultra_cap_counts_too():
    keys = [K("A", 650, 50), K("B", 650, 250)]
    p = re_mod.Planner(keys, [re_mod.Item("t1", 100, 120)])
    assert [(i.topic, k.name) for i, k, _ in p.place()] == [("t1", "B")]


def test_topic_larger_than_a_key_starts_and_continues_on_the_next_key_with_resume():
    keys = [K("A"), K("B")]
    item = re_mod.Item("big", 1000, 0)
    p = re_mod.Planner(keys, [item])
    (i, k, res), = p.place()
    assert (k.name, res) == ("A", (650, 0)) and not i.resume
    p.finish(i, k, res, "drained", (640, 0))
    assert keys[0].drained and i.resume and i.need() == (360, 0)
    (i2, k2, res2), = p.place()
    assert (k2.name, res2, i2.resume) == ("B", (360, 0), True)


def test_a_split_topic_holds_the_rest_of_its_estimate_on_the_other_keys():
    keys = [K("A"), K("B")]
    p = re_mod.Planner(keys, [re_mod.Item("big", 1000, 0), re_mod.Item("next", 400, 0)])
    started = p.place()
    assert [(i.topic, k.name) for i, k, _ in started] == [("big", "A")]  # "next" may not take the room big continues in
    assert keys[1].used_fast == 350 and not keys[1].busy
    i, k, res = started[0]
    p.finish(i, k, res, "drained", (650, 0))
    (i2, k2, res2), = p.place()
    assert (i2.topic, k2.name, res2) == ("big", "B", (350, 0)) and keys[1].used_fast == 350  # the hold became the reservation
    p.finish(i2, k2, res2, "published", (340, 0))
    (i3, k3, res3), = p.place()  # 310 left on B, every live key idle: "next" starts there, its rest waits for a rerun
    assert (i3.topic, k3.name, res3) == ("next", "B", (310, 0)) and p.holds == {}
    assert keys[1].used_fast == 650


def test_a_topic_larger_than_all_keys_together_starts_continues_and_waits_for_the_next_window():
    keys = [K("A"), K("B")]
    p = re_mod.Planner(keys, [re_mod.Item("huge", 2000, 0), re_mod.Item("small", 100, 0)])
    started = p.place()
    assert [(i.topic, k.name, res) for i, k, res in started] == [("huge", "A", (650, 0))]
    assert keys[1].used_fast == 650 and not keys[1].busy  # its rest is held on B: "small" may not take it
    assert [i.topic for i in p.pending] == ["small"] and p.take_waiting() == []
    i, k, res = started[0]
    p.finish(i, k, res, "drained", (650, 0))
    (i2, k2, res2), = p.place()
    assert (i2.topic, k2.name, res2, i2.resume) == ("huge", "B", (650, 0), True)  # never back on the drained key
    p.finish(i2, k2, res2, "drained", (650, 0))
    assert p.place() == []
    waiting = {i.topic: reason for i, reason in p.take_waiting()}
    assert set(waiting) == {"huge", "small"} and all("every key is drained" in r for r in waiting.values())
    # the next window's rerun: fresh caps, 1 300 calls in the journal; it resumes with the rest
    rerun = re_mod.Planner([K("A"), K("B")], [re_mod.Item("huge", 2000, 0, done_fast=1300, resume=True)])
    (i3, k3, res3), = rerun.place()
    assert (k3.name, res3, i3.resume) == ("A", (650, 0), True) and rerun.keys[1].used_fast == 50
    keys[0].drained = keys[1].drained = True
    p2 = re_mod.Planner(keys, [re_mod.Item("x", 1, 0)])
    assert p2.place() == [] and "every key is drained" in p2.take_waiting()[0][1]


def test_one_key_and_an_estimate_above_its_cap_starts_on_it():
    """The route without --keys is one key: a whole topic-day (~1 500 fast-lane calls live) is above its cap."""
    route, = re_mod.parse_keys(None, 650, 250)
    p = re_mod.Planner([route], [re_mod.Item("russia-ukraine-war", 1479, 148)])
    (i, k, res), = p.place()
    assert (k.name, res) == (re_mod.ROUTE, (650, 148)) and p.holds == {}
    p.finish(i, k, res, "drained", (600, 20))
    assert p.place() == [] and "every key is drained" in p.take_waiting()[0][1]
    plan = re_mod.simulate(re_mod.parse_keys(None, 650, 250), [re_mod.Item("russia-ukraine-war", 1479, 148)])
    assert [s["key"] for s in plan["russia-ukraine-war"]["segments"]] == [re_mod.ROUTE]
    assert plan["russia-ukraine-war"]["outcome"] == "waiting_for_key"


def test_three_keys_and_an_estimate_above_their_sum():
    plan = re_mod.simulate([K("A"), K("B"), K("C")], [re_mod.Item("broad", 2100, 210)])
    segs = plan["broad"]["segments"]
    assert [s["key"] for s in segs] == ["A", "B", "C"] and [s["resume"] for s in segs] == [False, True, True]
    assert plan["broad"]["outcome"] == "waiting_for_key" and "every key is drained" in plan["broad"]["reason"]


def test_a_drained_topic_continues_on_a_key_with_less_room_than_its_rest():
    keys = [K("A"), K("B")]
    p = re_mod.Planner(keys, [re_mod.Item("t", 1000, 0)])
    (i, k, res), = p.place()
    p.finish(i, k, res, "drained", (300, 0))  # the key had been used elsewhere: it drained early
    assert i.need() == (700, 0)
    (i2, k2, res2), = p.place()
    assert (k2.name, res2, i2.resume) == ("B", (650, 0), True)


def test_waiting_for_key_only_when_no_live_key_has_the_minimum_room():
    key = K("A")
    key.used_fast = 640  # 10 fast-lane calls of room left
    p = re_mod.Planner([key], [re_mod.Item("t", 300, 0)])
    assert p.place() == []
    (item, reason), = p.take_waiting()
    assert item.topic == "t" and "no key left has 25 calls of room" in reason and "most: 10 fast-lane" in reason


def test_a_resumed_topic_gets_the_freed_key_before_later_topics():
    keys = [K("A"), K("B")]
    t1, t2, t3 = re_mod.Item("t1", 600, 0), re_mod.Item("t2", 600, 0), re_mod.Item("t3", 300, 0)
    p = re_mod.Planner(keys, [t1, t2, t3])
    started = p.place()
    assert [(i.topic, k.name) for i, k, _ in started] == [("t1", "A"), ("t2", "B")]
    (_, ka, ra), (_, kb, rb) = started
    p.finish(t1, ka, ra, "drained", (400, 0))  # t1 needs 200 more and A is spent
    assert p.place() == []  # B is busy: both wait
    p.finish(t2, kb, rb, "published", (300, 0))  # B has 350 left: room for t1 (200) or t3 (300), not both
    (i, k, _), = p.place()
    assert (i.topic, k.name, i.resume) == ("t1", "B", True)
    assert [i.topic for i in p.pending] == ["t3"]


def test_a_split_topic_starts_only_on_a_key_with_the_minimum_room_on_each_lane():
    a, b = K("A"), K("B")
    a.used_ultra = 230  # A: 650 fast-lane and 20 Ultra calls left (more room by share)
    b.used_fast = 610  # B: 40 fast-lane and 250 Ultra calls left
    p = re_mod.Planner([a, b], [re_mod.Item("t", 600, 30)])
    (i, k, res), = p.place()
    assert (k.name, res) == ("B", (40, 30))  # A has fewer than 25 Ultra calls of room


def test_a_topic_that_fits_only_a_busy_key_waits_instead_of_splitting_onto_an_idle_one():
    keys = [K("A"), K("B", 200)]
    p = re_mod.Planner(keys, [re_mod.Item("t1", 100, 10), re_mod.Item("t2", 400, 10)])
    assert [(i.topic, k.name) for i, k, _ in p.place()] == [("t1", "A")]
    assert [i.topic for i in p.pending] == ["t2"] and not keys[1].busy and keys[1].used_fast == 0


def test_unknown_remainder_after_estimate_is_used_up():
    it = re_mod.Item("t", 100, 0, done_fast=150)
    assert it.need() == (re_mod.MIN_SEGMENT_CALLS, 0)


def test_simulated_plan_shows_segments_and_waiting():
    plan = re_mod.simulate([K("A"), K("B")], [re_mod.Item("big", 1000, 50), re_mod.Item("next", 400, 40)])
    assert [s["key"] for s in plan["big"]["segments"]] == ["A", "B"]
    assert [s["resume"] for s in plan["big"]["segments"]] == [False, True]
    assert plan["big"]["outcome"] == "published"
    assert [s["key"] for s in plan["next"]["segments"]] == ["B"]  # after big, on what B has left; the rest waits
    assert plan["next"]["outcome"] == "waiting_for_key"


def test_parse_keys_names_and_caps():
    keys = re_mod.parse_keys("MODEL_API_KEY,MODEL_API_KEY_2=400,MODEL_API_KEY_3=300/100", 650, 250)
    assert [(k.name, k.cap_fast, k.cap_ultra) for k in keys] == [("MODEL_API_KEY", 650, 250), ("MODEL_API_KEY_2", 400, 250), ("MODEL_API_KEY_3", 300, 100)]
    for bad in ("not-a-name$", "A,A", "A=x", "A=0"):
        with pytest.raises(ValueError):
            re_mod.parse_keys(bad, 650, 250)
    route, = re_mod.parse_keys(None, 650, 250)
    assert route.name == re_mod.ROUTE and not route.inject


def test_scaled_estimate_floor_for_ultra():
    assert re_mod.scaled_estimate({"fast": 924, "ultra": 0}, 1.6) == (1479, 148)
    assert re_mod.scaled_estimate({"fast": 100, "ultra": 50}, 1.0) == (100, 50)


def test_clean_reason_drops_paths_and_secrets():
    r = re_mod.Redactor([VALUE_A])
    text = f"FileNotFoundError: C:\\Users\\x\\file.txt and /home/x/y/z.json key {VALUE_A} meterless/fast"
    out = re_mod.clean_reason(text, r)
    assert VALUE_A not in out and "C:\\" not in out and "/home" not in out
    assert "[redacted]" in out and "meterless/fast" in out


def test_topic_ids_follow_the_shared_rule():
    from quorum_reasoning.tools.corpus import _TOPIC_ID

    for good in ("climate-policy", "ai--jobs", "covid-19-", "a", "x" * 64, "con-policy", "console", "com10", "lpt", "nul-hypothesis", "auxiliary"):
        assert re_mod.topic_id_ok(good) and dc_mod.topic_id_ok(good) and _TOPIC_ID.match(good)
    for bad in ("con", "prn", "aux", "nul", "com0", "com1", "com9", "lpt0", "lpt1", "lpt9"):
        # the shared rule admits them; Windows opens a device under each name, in every folder
        assert _TOPIC_ID.fullmatch(bad) and not re_mod.topic_id_ok(bad) and not dc_mod.topic_id_ok(bad), bad
        assert "device" in re_mod.topic_id_problem(bad) and "device" in dc_mod.topic_id_problem(bad)
    for variant in ("CON", "Nul", "COM1", "lpt¹", "com²", "LPT³"):  # any case, superscript digits
        assert re_mod.WINDOWS_DEVICE.fullmatch(variant) and dc_mod.WINDOWS_DEVICE.fullmatch(variant), variant
        assert not re_mod.topic_id_ok(variant) and not dc_mod.topic_id_ok(variant)
    for bad in ("", "-x", "A-topic", "a.b", "../etc", "a/b", "x" * 65, "abc\n", "a b", None):
        assert not re_mod.topic_id_ok(bad) and not dc_mod.topic_id_ok(bad)


# ---------------------------------------------------------------------------------------------------------------------
# status files


def test_status_writes_are_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "s" / "t.json"
    re_mod.write_json_atomic(path, {"state": "queued"})

    def broken_replace(src, dst):
        raise OSError("disk went away")

    monkeypatch.setattr(re_mod.os, "replace", broken_replace)
    with pytest.raises(OSError):
        re_mod.write_json_atomic(path, {"state": "running"})
    monkeypatch.undo()
    with pytest.raises(TypeError):
        re_mod.write_json_atomic(path, {"state": object()})  # fails while writing the temp file
    assert json.loads(path.read_text()) == {"state": "queued"}
    assert [p.name for p in path.parent.iterdir()] == ["t.json"]  # no temp file left behind


def test_status_files_are_saved_through_the_atomic_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    statuses = re_mod.Statuses(tmp_path / "status", DATE, re_mod.Redactor([]))
    statuses.open("t1", f"{DATE}-t1-1")
    statuses.save("t1", state="queued")
    paths = (statuses.path("t1"), statuses.path("t1").with_name(f"{DATE}.json.sha256"), statuses.record_path("t1"))
    assert paths[0] == tmp_path / "status" / "t1" / f"{DATE}.json" and paths[2] == tmp_path / "status" / "_runner" / DATE / "t1" / "1.json"
    before = [p.read_bytes() for p in paths]

    def broken_replace(src, dst):
        raise OSError("disk went away")

    monkeypatch.setattr(re_mod.os, "replace", broken_replace)
    with pytest.raises(OSError):
        statuses.save("t1", state="running")
    assert [p.read_bytes() for p in paths] == before and json.loads(before[0])["state"] == "queued"
    assert sorted(p.name for p in paths[0].parent.iterdir()) == [f"{DATE}.json", f"{DATE}.json.sha256"]  # no temp file left
    assert [p.name for p in paths[2].parent.iterdir()] == ["1.json"]


def test_status_save_refuses_a_state_outside_the_contract(tmp_path: Path):
    statuses = re_mod.Statuses(tmp_path / "status", DATE, re_mod.Redactor([]))
    statuses.open("t1", f"{DATE}-t1-1")
    with pytest.raises(ValueError, match="'drained' is not one of queued, running, published, failed, waiting_for_key"):
        statuses.save("t1", state="drained")
    assert not (tmp_path / "status").exists()  # nothing was written
    statuses.save("t1", state="waiting_for_key", reason="x")
    assert json.loads(statuses.path("t1").read_text(encoding="utf-8"))["state"] == "waiting_for_key"


def test_status_replace_retries_while_a_reader_holds_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "t.json"
    real = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("in use")
        return real(src, dst)

    monkeypatch.setattr(re_mod.os, "replace", flaky)
    re_mod.write_json_atomic(path, {"ok": 1})
    assert json.loads(path.read_text()) == {"ok": 1} and calls["n"] == 3


# ---------------------------------------------------------------------------------------------------------------------
# end to end with fake commands


def _all_text(*dirs: Path) -> str:
    chunks = []
    for d in dirs:
        for p in d.rglob("*"):
            if p.is_file():
                chunks.append(p.read_bytes().decode("utf-8", "replace"))
    return "\n".join(chunks)


def test_rotation_requeues_a_drained_topic_as_resume_on_another_key(world: Env):
    world.scenario({"t1": [{"exit": 3, "fast": 200}, {"exit": 0, "fast": 50, "ultra": 5}]}, {"t1": {"fast": 300, "ultra": 30}})
    rc = world.main(world.argv("t1"))
    assert rc == 0
    runs = world.runs()
    assert [(r["key_name"], r["resume"]) for r in runs] == [("QTEST_KEY_A", False), ("QTEST_KEY_B", True)]
    assert all(r["blank_ok"] for r in runs)  # every other key variable was blank in the child
    assert all(r["dry_env"] == "1" for r in runs)  # the fixture's fail-closed guard reaches the children
    st = world.status_of("t1")
    assert st["state"] == "published" and st["version"] == 1 and st["attempts"] == 2
    assert [r["outcome"] for r in st["runs"]] == ["drained", "published"]
    assert st["runs"][0]["calls"] == {"fast": 200, "ultra": 0}
    assert st["calls_estimate"] == 330 and st["calls_estimate_lanes"] == {"fast": 300, "ultra": 30}
    assert {"topic", "date", "state", "run_id", "started_at", "updated_at", "attempts"} <= set(st)
    assert (world.logs / f"{DATE}_t1_a1_run01_QTEST_KEY_A.log").is_file()
    assert (world.logs / f"{DATE}_t1_a1_run02_QTEST_KEY_B.log").is_file()
    assert [k["drained"] for k in world.summary()["keys"]] == [True, False]


def test_failures_do_not_stop_the_rest_and_have_short_reasons(world: Env):
    world.scenario({
        "ok": [{"exit": 0, "fast": 10}],
        "crash": [{"crash": True, "fast": 5}],
        "refused": [{"exit": 2, "publish": False, "say": "refusing to run: --model live with a mixed model route"}],
        "partial": [{"exit": 2, "publish": True, "status": "partial"}],
        "odd": [{"exit": 7, "publish": False, "say": "something odd"}],
        "long": [{"exit": 1, "publish": False, "say": "ValueError: " + "a\tvery long line " * 125}],  # ~2 000 characters
    })
    rc = world.main(world.argv("ok,crash,refused,partial,odd,long", keys="QTEST_KEY_A,QTEST_KEY_B,QTEST_KEY_C"))
    assert rc == 1
    long_reason = world.public_of("long")["reason"]  # what the portal shows under "Could not be prepared"
    assert len(long_reason) <= re_mod.REASON_MAX and long_reason.endswith("…") and long_reason.startswith("exit 1: ValueError: a very long")
    assert "\n" not in long_reason and "\t" not in long_reason and world.status_of("long")["reason"] == long_reason
    assert world.status_of("ok")["state"] == "published"
    crash = world.status_of("crash")
    assert crash["state"] == "failed" and "RuntimeError: boom in the fake run" in crash["reason"] and crash["exit_code"] == 1
    refused = world.status_of("refused")
    assert refused["state"] == "failed" and refused["reason"].startswith("exit 2: refusing to run: --model live with a mixed")
    partial = world.status_of("partial")
    assert partial["state"] == "published" and partial["snapshot_status"] == "partial" and "partial" in partial["reason"]
    assert world.status_of("odd")["reason"] == "exit 7: something odd"
    assert len(world.runs()) == 6


def test_all_keys_drained_leaves_waiting_for_key(world: Env):
    world.scenario({"t1": [{"exit": 3, "fast": 100}]}, {"t1": {"fast": 300, "ultra": 0}})
    rc = world.main(world.argv("t1"))
    assert rc == 3
    st = world.status_of("t1")
    assert st["state"] == "waiting_for_key" and "every key is drained" in st["reason"]
    assert [(r["key_name"], r["resume"]) for r in world.runs()] == [("QTEST_KEY_A", False), ("QTEST_KEY_B", True)]


def test_a_rerun_skips_published_and_resumes_what_has_a_checkpoint(world: Env):
    world.scenario({"done": [{"exit": 0}], "half": [{"exit": 3, "fast": 100}, {"exit": 3, "fast": 100}, {"exit": 0, "fast": 20}]})
    assert world.main(world.argv("done,half")) == 3
    assert world.status_of("half")["state"] == "waiting_for_key"
    first = len(world.runs())
    assert world.main(world.argv("done,half")) == 0
    later = world.runs()[first:]
    assert [(r["topic"], r["resume"]) for r in later] == [("half", True)]  # a fresh invocation resumes the checkpoint
    assert world.status_of("done")["reason"] == "already published by an earlier run"
    half = world.status_of("half")
    assert half["state"] == "published" and half["attempts"] == 3 and len(half["runs"]) == 3


def test_route_mode_starts_a_topic_larger_than_its_cap_and_the_rerun_resumes_it(world: Env):
    """The documented Meterless path (no --keys): a topic-day above the route's cap runs until the route drains, and
    the next window's rerun of the same command finishes it."""
    world.scenario({"big": [{"exit": 3, "fast": 300}, {"exit": 0, "fast": 200}]}, {"big": {"fast": 2000, "ultra": 0}}, blank_expected=[])
    assert world.main(world.argv("big", keys=None, live=False)) == 3  # the plan: starts now, finishes in a later window
    plan = world.status_of("big")
    assert [s["key"] for s in plan["plan"]] == [re_mod.ROUTE] and plan["plan_outcome"] == "waiting_for_key"
    assert world.main(world.argv("big", keys=None)) == 3
    st = world.status_of("big")
    assert st["state"] == "waiting_for_key" and "every key is drained" in st["reason"]
    assert [r["outcome"] for r in st["runs"]] == ["drained"] and st["runs"][0]["key"] == re_mod.ROUTE
    assert [r["resume"] for r in world.runs()] == [False]
    assert world.main(world.argv("big", keys=None)) == 0
    assert [r["resume"] for r in world.runs()] == [False, True]
    st = world.status_of("big")
    assert st["state"] == "published" and st["calls_done"] == {"fast": 500, "ultra": 0}


def test_dry_mode_exits_3_when_the_plan_leaves_a_topic_for_the_next_window(world: Env):
    world.scenario({}, {"t1": {"fast": 1500, "ultra": 0}})
    assert world.main(world.argv("t1", live=False)) == 3
    st = world.status_of("t1")
    assert st["plan_outcome"] == "waiting_for_key" and [s["key"] for s in st["plan"]] == ["QTEST_KEY_A", "QTEST_KEY_B"]
    assert world.runs() == []


def test_max_calls_per_key_sets_the_caps(world: Env):
    world.scenario({}, {"t1": {"fast": 150, "ultra": 0}})  # estimate 150 / 15 (factor 1, Ultra floor 10 %)
    assert world.main(world.argv("t1", "--max-calls-per-key", "100", "--max-ultra-calls-per-key", "40", live=False)) == 0
    st = world.status_of("t1")
    assert [s["key"] for s in st["plan"]] == ["QTEST_KEY_A", "QTEST_KEY_B"] and st["plan_outcome"] == "published"
    assert [(k["cap_fast"], k["cap_ultra"]) for k in world.summary()["keys"]] == [(100, 40), (100, 40)]
    assert world.main(world.argv("t1", "--max-calls-per-key", "100", keys="QTEST_KEY_A", live=False)) == 3
    st = world.status_of("t1")
    assert [s["key"] for s in st["plan"]] == ["QTEST_KEY_A"] and st["plan_outcome"] == "waiting_for_key"


def test_slow_runs_on_two_keys_overlap_and_the_status_says_running(world: Env):
    world.scenario({"s1": [{"exit": 0, "sleep": 1.2}], "s2": [{"exit": 0, "sleep": 1.2}]})
    assert world.main(world.argv("s1,s2")) == 0
    runs = {r["topic"]: r for r in world.runs()}
    assert runs["s1"]["start"] < runs["s2"]["end"] and runs["s2"]["start"] < runs["s1"]["end"]  # one process per key, in parallel
    assert {r["key_name"] for r in runs.values()} == {"QTEST_KEY_A", "QTEST_KEY_B"}
    assert all(r["status_seen"] == "running" for r in runs.values())


def test_relative_folders_reach_the_children_as_absolute_paths(world: Env, monkeypatch: pytest.MonkeyPatch):
    """The children run with cwd = reasoning/; folders given relative to the operator's cwd must still match."""
    world.scenario({"t1": [{"exit": 0}]})
    monkeypatch.chdir(world.tmp)
    argv = world.argv("t1")
    for flag, rel in (("--out", "store"), ("--log-dir", "logs"), ("--status-dir", "status"), ("--dry-check-out", "dry")):
        argv[argv.index(flag) + 1] = rel
    assert world.main(argv) == 0
    run, = world.runs()
    assert Path(run["argv"][run["argv"].index("--out") + 1]) == (world.tmp / "store").resolve()
    assert world.status_of("t1")["version"] == 1


def test_one_key_runs_its_topics_in_order(world: Env):
    world.scenario({"a": [{"exit": 0, "sleep": 0.3}], "b": [{"exit": 0}]})
    assert world.main(world.argv("a,b", keys="QTEST_KEY_A")) == 0
    runs = world.runs()
    assert [r["topic"] for r in runs] == ["a", "b"] and runs[0]["end"] <= runs[1]["start"] + 0.05


def test_a_run_over_its_time_limit_is_stopped_and_failed(world: Env):
    world.scenario({"slow": [{"exit": 0, "sleep": 20}]})
    t0 = time.monotonic()
    rc = world.main(world.argv("slow", "--run-timeout-min", "0.03"))
    assert rc == 1 and time.monotonic() - t0 < 15
    st = world.status_of("slow")
    assert st["state"] == "failed" and "timed out" in st["reason"]


def test_a_command_that_cannot_start_fails_that_topic(world: Env):
    world.scenario({})
    rc = world.main(world.argv("t1"), live_cmd=[str(world.tmp / "no-such-interpreter.exe")])
    assert rc == 1
    st = world.status_of("t1")
    assert st["state"] == "failed" and st["reason"].startswith("could not start the run")


def test_no_key_value_reaches_a_log_or_a_status_file(world: Env):
    world.scenario({"t1": [{"exit": 3, "fast": 10}, {"exit": 0}], "t2": [{"crash": True}]}, echo_key=True)
    world.main(world.argv("t1,t2", keys="QTEST_KEY_A,QTEST_KEY_B,QTEST_KEY_C"))
    text = _all_text(world.logs, world.status)
    for value in (VALUE_A, VALUE_B, VALUE_C):
        assert value not in text
    assert "MODEL_API_KEY=[redacted]" in (world.logs / f"{DATE}_t1_a1_run01_QTEST_KEY_A.log").read_text(encoding="utf-8")
    assert "stderr sees [redacted]" in text
    for p in world.status.rglob("*.json"):
        doc = p.read_text(encoding="utf-8")
        assert str(world.tmp) not in doc and str(world.tmp).replace("\\", "\\\\") not in doc  # no absolute paths


def test_route_mode_redacts_tokens_from_the_env_file_and_paths_in_reasons(world: Env):
    """No --keys (the Meterless path): the values the runner redacts are the .env's secret-named ones, not key values."""
    token, zkey = "fake-meterless-token-7777", "fake-zetaris-key-8888"
    with world.env_file.open("a") as fh:
        fh.write(f"METERLESS_TOKEN={token}\nZETARIS_API_KEY={zkey}\n")
    where = str(world.tmp / "store" / "_checkpoints" / "x.sqlite")
    world.scenario({"t1": [{"exit": 2, "publish": False, "echo": f"route token {token} zetaris {zkey}",
                            "say": f"refusing to run: {where} {token}"}]}, blank_expected=[])
    assert world.main(world.argv("t1", keys=None)) == 1
    text = _all_text(world.logs, world.status)
    assert token not in text and zkey not in text
    assert "route token [redacted] zetaris [redacted]" in (world.logs / f"{DATE}_t1_a1_run01_{re_mod.ROUTE}.log").read_text(encoding="utf-8")
    reason = world.status_of("t1")["reason"]
    assert reason == "exit 2: refusing to run: <path> [redacted]", reason


def test_without_live_only_dry_checks_run(world: Env):
    world.scenario({"t1": [{"exit": 0}]}, {"t1": {"fast": 900, "ultra": 20}, "t2": {"fast": 100, "ultra": 0}})
    rc = world.main(world.argv("t1,t2", live=False))
    assert rc == 0
    assert world.runs() == [] and not (world.out / "_journal").exists()  # nothing live was started
    dry = world.dry_runs()
    assert sorted(d["topic"] for d in dry) == ["t1", "t2"]
    assert all(d["dry_env"] == "1" and d["model_key"] == "" for d in dry)
    assert all({"QTEST_KEY_A", "QTEST_KEY_B", "MODEL_API_KEY_8", "MODEL_API_KEY_9"} <= set(d["blank"].split(",")) for d in dry)
    st = world.status_of("t1")
    assert st["state"] == "queued" and st["reason"].startswith("dry check only (no --live)")
    assert [s["key"] for s in st["plan"]] == ["QTEST_KEY_A", "QTEST_KEY_B"] and st["plan_outcome"] == "published"
    assert (world.logs / f"{DATE}_t1_dry.log").is_file()


def test_without_live_nothing_live_is_spawned(world: Env, monkeypatch: pytest.MonkeyPatch):
    world.scenario({"t1": [{"exit": 0}]}, {"t1": {"fast": 10, "ultra": 0}})
    spawned: list[list[str]] = []
    real = subprocess.Popen

    def recording(argv, *a, **k):
        spawned.append([str(x) for x in argv])
        return real(argv, *a, **k)

    monkeypatch.setattr(re_mod.subprocess, "Popen", recording)
    assert world.main(world.argv("t1", live=False)) == 0
    assert spawned and all(str(world.tmp / "fake_dry.py") in argv for argv in spawned)
    assert not any(str(world.tmp / "fake_run.py") in argv for argv in spawned)
    assert not any("--live" in argv or "live" in argv for argv in spawned)  # no child got a live model flag


def test_a_failed_dry_check_fails_the_topic_and_starts_no_live_run(world: Env):
    world.scenario({"good": [{"exit": 0}], "bad": [{"exit": 0}]}, {"bad": {"error": True}})
    assert world.main(world.argv("good,bad")) == 1
    assert world.status_of("bad")["state"] == "failed" and "dry check failed" in world.status_of("bad")["reason"]
    assert [r["topic"] for r in world.runs()] == ["good"]


def test_topics_all_plans_every_row_and_reports_a_row_it_cannot_run(world: Env):
    world.scenario({}, {}, db_topics=["alpha-topic", "ai--jobs", "covid-19-", "Not A Slug"],
                   db_skipped=[{"id": "x/y", "reason": "not a topic id by the shared rule"}])
    assert world.main(world.argv("all", live=False)) == 1  # the rows it cannot run count as failed
    assert sorted(d["topic"] for d in world.dry_runs()) == ["ai--jobs", "alpha-topic", "covid-19-"]
    bad = [r for r in world.summary()["topics"] if r.get("skipped_row")]
    assert [r["topic"] for r in bad] == ["x/y", "Not A Slug"] and all(r["state"] == "failed" for r in bad)
    runner_log = (world.logs / f"{DATE}_runner.log").read_text(encoding="utf-8")
    assert "'Not A Slug'" in runner_log and "'x/y'" in runner_log
    assert sorted(p.name for p in world.status.iterdir()) == ["_runner"]  # a plan writes no status file
    assert world.record_files() == ["_summary.json", "ai--jobs/1.json", "alpha-topic/1.json", "covid-19-/1.json"]  # none for x/y


def test_topics_all_with_live_is_refused_until_zetaris_shows_active_rows(world: Env):
    world.scenario({"alpha-topic": [{"exit": 0}]}, {}, db_topics=["alpha-topic"])
    assert world.main(world.argv("all")) == 2
    assert world.runs() == [] and world.dry_runs() == []
    world.scenario({"alpha-topic": [{"exit": 0}]}, {}, db_topics=["alpha-topic"], db_filtered=True)
    assert world.main(world.argv("all")) == 0
    assert [r["topic"] for r in world.runs()] == ["alpha-topic"]


def test_a_listed_topic_that_is_not_a_row_fails_without_a_run(world: Env):
    world.scenario({"real-topic": [{"exit": 0}], "no-such-topic-xyz": [{"exit": 0}]}, db_topics=["real-topic"])
    assert world.main(world.argv("real-topic,no-such-topic-xyz")) == 1
    st = world.status_of("no-such-topic-xyz")
    assert st["state"] == "failed" and "not a row in collection's topics table" in st["reason"]
    assert [r["topic"] for r in world.runs()] == ["real-topic"] and [d["topic"] for d in world.dry_runs()] == ["real-topic"]
    world.scenario({"real-topic": [{"exit": 0}]}, db_topics=["real-topic"], db_filtered=True)
    assert world.main(world.argv("no-such-topic-xyz", live=False)) == 1
    st = world.status_of("no-such-topic-xyz")  # the live invocation's verdict stays; the plan's goes beside it
    assert st["state"] == "failed" and "not a row in" in st["reason"] and "not an active row" in st["plan_reason"]


def test_listed_topics_by_the_shared_rule_are_run(world: Env):
    world.scenario({"ai--jobs": [{"exit": 0}], "covid-19-": [{"exit": 0}]})
    assert world.main(world.argv("ai--jobs,covid-19-")) == 0
    assert sorted(r["topic"] for r in world.runs()) == ["ai--jobs", "covid-19-"]
    assert world.status_of("covid-19-")["state"] == "published"


def test_route_mode_injects_no_key(world: Env):
    world.scenario({"t1": [{"exit": 0}]}, blank_expected=[])
    assert world.main(world.argv("t1", keys=None)) == 0
    run, = world.runs()
    assert run["key_name"] == "?" or run["key_name"] == ""  # whatever the environment holds; the runner set nothing
    assert world.status_of("t1")["key"] == re_mod.ROUTE


@pytest.mark.parametrize("case", ["dry_inside_out", "meterless_with_keys", "before_cut", "unusable_key", "env_file_live", "bad_topic",
                                  "bad_topic_dot", "lock", "listing_fails"])
def test_refusals(world: Env, monkeypatch: pytest.MonkeyPatch, case: str):
    argv = world.argv("t1")
    if case == "dry_inside_out":
        argv[argv.index("--dry-check-out") + 1] = str(world.out / "dry")
    elif case == "meterless_with_keys":
        monkeypatch.setenv("MODEL_BASE_URL", "http://127.0.0.1:8088/v1")
    elif case == "before_cut":
        argv[argv.index("--date") + 1] = "2099-01-01"
    elif case == "unusable_key":
        argv[argv.index("--keys") + 1] = "QTEST_KEY_A,QTEST_KEY_EMPTY"
    elif case == "env_file_live":
        other = world.tmp / "other.env"
        other.write_text("")
        argv += ["--env-file", str(other)]
    elif case == "bad_topic":
        argv[argv.index("--topics") + 1] = "../etc"
    elif case == "bad_topic_dot":
        argv[argv.index("--topics") + 1] = "a.b"
    elif case == "lock":
        world.runner.mkdir(parents=True)
        (world.runner / ".runner.lock").write_text("{}")
    elif case == "listing_fails":
        world.scenario({}, db_error=True)
    assert world.main(argv) == 2
    assert world.runs() == [] and world.dry_runs() == []


def test_dry_mode_may_run_before_the_cut(world: Env):
    world.scenario({}, {"t1": {"fast": 10, "ultra": 0}})
    argv = world.argv("t1", live=False)
    argv[argv.index("--date") + 1] = "2099-01-01"
    assert world.main(argv) == 0


def test_a_plan_run_keeps_a_live_failure_in_the_status_file(world: Env):
    """The README's step 1 (the plan, any time) into the same --status-dir after a live failure: the failure stays."""
    world.scenario({"t1": [{"exit": 7, "publish": False, "say": "something odd"}, {"exit": 0}]}, {"t1": {"fast": 300, "ultra": 30}})
    assert world.main(world.argv("t1")) == 1
    live = world.status_of("t1")
    assert (live["state"], live["exit_code"], live["state_mode"]) == ("failed", 7, "live")
    assert world.main(world.argv("t1", live=False)) == 1  # the plan's exit code still shows the failure
    st = world.status_of("t1")
    assert (st["state"], st["exit_code"], st["reason"], st["state_mode"]) == ("failed", 7, "exit 7: something odd", "live")
    assert st["runs"] == live["runs"] and st["attempts"] == 1 and st["log"] == live["log"]
    assert st["plan_outcome"] == "published" and st["plan_reason"].startswith("dry check only (no --live)") and st["plan"]
    assert [(r["topic"], r["state"]) for r in world.summary()["topics"]] == [("t1", "failed")]
    assert len(world.runs()) == 1  # the plan started nothing
    assert world.main(world.argv("t1")) == 0  # the next live run writes its own outcome
    st = world.status_of("t1")
    assert st["state"] == "published" and "exit_code" not in st and "plan_reason" not in st and len(st["runs"]) == 2


def test_a_plan_run_keeps_waiting_for_key_and_exits_3(world: Env):
    world.scenario({"t1": [{"exit": 3, "fast": 100}]}, {"t1": {"fast": 300, "ultra": 0}})
    assert world.main(world.argv("t1")) == 3
    assert world.status_of("t1")["state"] == "waiting_for_key"
    assert world.main(world.argv("t1", live=False)) == 3  # rested keys would finish it, but it is still waiting for one
    st = world.status_of("t1")
    assert st["state"] == "waiting_for_key" and "every key is drained" in st["reason"] and st["plan_outcome"] == "published"
    assert [r["state"] for r in world.summary()["topics"]] == ["waiting_for_key"]
    world.scenario({"t1": [{"exit": 3, "fast": 100}]}, {"t1": {"error": True}})
    assert world.main(world.argv("t1", live=False)) == 1  # a failed dry check fails the plan, not the live state
    st = world.status_of("t1")
    assert st["state"] == "waiting_for_key" and st["plan_outcome"] == "failed" and "plan" not in st
    assert st["plan_reason"].startswith("dry check failed")


def test_a_plan_run_replaces_what_an_earlier_plan_run_set(world: Env):
    world.scenario({}, {"t1": {"error": True}})
    assert world.main(world.argv("t1", live=False)) == 1
    st = world.status_of("t1")
    assert (st["state"], st["state_mode"]) == ("failed", "dry")
    world.scenario({}, {"t1": {"fast": 100, "ultra": 0}})
    assert world.main(world.argv("t1", live=False)) == 0
    st = world.status_of("t1")
    assert (st["state"], st["state_mode"]) == ("queued", "dry") and st["reason"].startswith("dry check only") and "plan_reason" not in st


@pytest.mark.parametrize("topic", ["con", "nul"])
def test_a_listed_windows_device_name_is_refused(world: Env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], topic: str):
    # on Windows a status file named after a device blocks the runner: fail fast instead if the refusal is gone
    monkeypatch.setattr(re_mod, "_run", lambda *a, **k: pytest.fail("a device name got past the topic-id check"))
    assert world.main(world.argv(f"good-topic,{topic}")) == 2
    assert world.main(world.argv(topic, live=False)) == 2
    assert world.runs() == [] and world.dry_runs() == []
    assert "device name" in capsys.readouterr().err


def test_topics_all_skips_rows_named_after_a_windows_device(world: Env, monkeypatch: pytest.MonkeyPatch):
    for name in ("path", "record_path"):
        real = getattr(re_mod.Statuses, name)

        def guarded(self, topic: str, *more, real=real) -> Path:  # on Windows the real name would block or fail: fail fast instead
            assert not re_mod.WINDOWS_DEVICE.fullmatch(topic), f"{topic!r} reached a status file name"
            return real(self, topic, *more)

        monkeypatch.setattr(re_mod.Statuses, name, guarded)
    world.scenario({}, {}, db_topics=["alpha-topic", "con", "nul"])
    assert world.main(world.argv("all", live=False)) == 1  # the rows it cannot run count as failed
    assert [d["topic"] for d in world.dry_runs()] == ["alpha-topic"]
    bad = [r for r in world.summary()["topics"] if r.get("skipped_row")]
    assert [r["topic"] for r in bad] == ["con", "nul"] and all(r["state"] == "failed" and "device name" in r["reason"] for r in bad)
    assert sorted(p.name for p in world.status.iterdir()) == ["_runner"]  # a plan writes no status file
    assert world.record_files() == ["_summary.json", "alpha-topic/1.json"]
    assert world.status_of("alpha-topic")["state"] == "queued"  # the other topics of the date went on


def test_ctrl_c_stops_the_children_keeps_their_checkpoints_and_releases_the_lock(world: Env):
    """Ctrl-C while a live child runs: exit 130, the child is stopped (a paid run must not go on), its checkpoint stays,
    its status says interrupted, the lock is gone."""
    world.scenario({"slow": [{"exit": 0, "sleep": 20}]})
    rid = f"{DATE}-slow-1"
    stop, fired = threading.Event(), threading.Event()

    def ctrl_c_once_running() -> None:
        deadline = time.monotonic() + 120
        while not stop.is_set() and time.monotonic() < deadline:
            try:
                state = world.status_of("slow").get("state")
            except (OSError, ValueError):
                state = None
            if state == "running" and re_mod.checkpoint_has_thread(world.out, rid):
                time.sleep(0.5)  # the child is in its sleep; the runner waits on its queue
                if not stop.is_set():
                    fired.set()
                    _thread.interrupt_main()
                return
            time.sleep(0.05)

    poker = threading.Thread(target=ctrl_c_once_running, daemon=True)
    poker.start()
    try:
        rc = world.main(world.argv("slow", keys="QTEST_KEY_A"))
    finally:
        stop.set()
        poker.join(5)
    assert fired.is_set() and rc == 130
    assert world.runs() == []  # the fake writes its record after its 20 s sleep: it was stopped before
    st = world.status_of("slow")
    assert st["state"] != "running" and "interrupted" in st["reason"] and st["runs"][0]["key"] == "QTEST_KEY_A"
    assert (world.out / "_checkpoints" / f"{rid}.sqlite").is_file()
    assert not (world.runner / ".runner.lock").exists()


def test_status_files_follow_the_portal_contract(world: Env):
    """Issue #2 6411408519 / 6411653104: <status-dir>/<topic>/<date>.json with exactly the eight fields (public_of checks
    them, the state, the sha256 file beside it and the match with the record), nothing else beside the topic folders
    but the runner's own `_runner` folder, which keeps every other field; a plan run writes its record only."""
    world.scenario({"t1": [{"exit": 3, "fast": 200}, {"exit": 0, "fast": 50}], "t2": [{"crash": True}]}, {"t1": {"fast": 300, "ultra": 30}})
    assert world.main(world.argv("t1,t2")) == 1
    t1, t2 = world.public_of("t1"), world.public_of("t2")
    assert (t1["state"], t1["reason"], t1["attempts"], t1["run_id"]) == ("published", None, 2, f"{DATE}-t1-1")
    assert t2["state"] == "failed" and "boom in the fake run" in t2["reason"]
    assert sorted(p.name for p in world.status.iterdir()) == ["_runner", "t1", "t2"]
    for topic in ("t1", "t2"):
        assert sorted(p.name for p in (world.status / topic).iterdir()) == [f"{DATE}.json", f"{DATE}.json.sha256"]
    assert sorted(p.name for p in world.runner.iterdir()) == ["_summary.json", "t1", "t2"]  # the lock is gone
    assert world.record_files() == ["_summary.json", "t1/1.json", "t2/1.json"]  # one record per run id
    record = world.status_of("t1")
    assert record["runs"] and record["calls_estimate"] == 330 and record["state_mode"] == "live" and record["version"] == 1
    world.scenario({}, {"t3": {"fast": 10, "ultra": 0}})
    assert world.main(world.argv("t3", live=False)) == 0  # for the portal no file reads as queued
    assert not (world.status / "t3").exists() and world.status_of("t3")["state"] == "queued"


def test_started_at_is_the_first_live_start(world: Env):
    """The portal shows `running` and `waiting_for_key` as "being prepared since started_at": a plan run hours before
    does not date it, and a rerun that resumes keeps it."""
    world.scenario({"t1": [{"exit": 3, "fast": 100}, {"exit": 3, "fast": 100}, {"exit": 0}]}, {"t1": {"fast": 300, "ultra": 0}})
    assert world.main(world.argv("t1", live=False)) == 0
    world.set_record("t1", started_at="2026-10-20T06:00:00Z")  # the plan ran at 06:00
    assert world.main(world.argv("t1")) == 3  # both keys drain
    waiting = world.public_of("t1")
    assert waiting["state"] == "waiting_for_key" and waiting["started_at"] > "2026-10-20T06:00:00Z"
    assert world.main(world.argv("t1")) == 0  # the next window resumes it
    done = world.public_of("t1")
    assert done["state"] == "published" and done["started_at"] == waiting["started_at"] and done["attempts"] == 3


def test_a_plan_run_after_a_publish_the_plan_predicted_to_wait_exits_0(world: Env):
    """The x1.6 estimate often predicts a wait for a topic that then publishes: `published` clears the prediction."""
    world.scenario({"t1": [{"exit": 0, "fast": 10}]}, {"t1": {"fast": 1000, "ultra": 0}})
    assert world.main(world.argv("t1", keys="QTEST_KEY_A")) == 0  # 1 000 > 650: the plan said waiting_for_key
    st = world.status_of("t1")
    assert st["state"] == "published" and not set(re_mod.PLAN_FIELDS) & set(st)
    pair = world.age_public("t1")  # any rewrite changes its bytes
    assert world.main(world.argv("t1", keys="QTEST_KEY_A", live=False)) == 0
    row, = world.summary()["topics"]
    assert (row["state"], row["plan_outcome"]) == ("published", None)
    assert world.public_pair("t1") == pair and world.public_of("t1", record=False)["state"] == "published"


def test_attempt_reaches_run_py_and_names_the_run_id(world: Env):
    """--attempt 2: run.py gets --attempt 2, the status names run <date>-t1-2, and attempt 1's snapshot in the store
    does not count as this run id published."""
    d = world.out / "t1" / DATE
    d.mkdir(parents=True)
    old = {"run_id": f"{DATE}-t1-1", "topic_id": "t1", "edition_date": DATE, "status": "ok", "version": 1}
    (d / "v1.json").write_text(json.dumps(old))
    (d / "latest.json").write_text(json.dumps(old))
    world.scenario({"t1": [{"exit": 0, "fast": 10}]})
    assert world.main(world.argv("t1", "--attempt", "2")) == 0
    run, = world.runs()
    assert run["argv"][run["argv"].index("--attempt") + 1] == "2"
    st = world.public_of("t1")
    assert (st["state"], st["run_id"], st["reason"]) == ("published", f"{DATE}-t1-2", None)
    assert world.status_of("t1")["version"] == 2


def test_a_plan_run_writes_no_status_file(world: Env):
    """Only a live invocation writes <topic>/<date>.json (decision at Statuses.save): a plan whose dry check fails is no
    edition anyone tried to run, and a plan of another attempt, or the README's plan without --attempt after a later
    attempt published, leaves the published file byte-identical."""
    world.scenario({}, {"t1": {"error": True}})
    assert world.main(world.argv("t1", live=False)) == 1
    assert not (world.status / "t1").exists()
    assert (world.status_of("t1")["state"], world.status_of("t1")["state_mode"]) == ("failed", "dry")
    world.scenario({"t1": [{"exit": 1, "publish": False, "say": "boom"}, {"exit": 0}]}, {"t1": {"fast": 100, "ultra": 0}})
    assert world.main(world.argv("t1")) == 1  # attempt 1 fails live
    assert world.main(world.argv("t1", "--attempt", "2")) == 0  # attempt 2 publishes
    assert (world.public_of("t1")["state"], world.public_of("t1")["run_id"]) == ("published", f"{DATE}-t1-2")
    pair = world.age_public("t1")
    assert world.main(world.argv("t1", live=False)) == 1  # the README's step 1, attempt 1: its own record keeps its live failure
    assert (world.status_of("t1")["state"], world.status_of("t1")["state_mode"]) == ("failed", "live")
    assert world.main(world.argv("t1", "--attempt", "3", live=False)) == 0
    world.scenario({}, {"t1": {"error": True}})
    assert world.main(world.argv("t1", "--attempt", "3", live=False)) == 1
    assert world.public_pair("t1") == pair
    assert len(world.runs()) == 2  # the plans started nothing


def test_a_later_attempt_keeps_the_published_status_until_it_publishes(world: Env):
    """One status file per topic and date: while the store's newest version is attempt 1's, attempt 2's plan, start and
    failure go to the runner's record only; once attempt 2 publishes, the file shows it (decision at follow_store)."""
    world.scenario({"t1": [{"exit": 0}, {"exit": 1, "publish": False, "say": "boom"}, {"exit": 0}]}, {"t1": {"fast": 100, "ultra": 0}})
    assert world.main(world.argv("t1")) == 0
    first = world.public_of("t1")
    assert (first["state"], first["run_id"], first["attempts"]) == ("published", f"{DATE}-t1-1", 1)
    pair = world.age_public("t1")  # any rewrite changes its bytes
    assert world.main(world.argv("t1", "--attempt", "2", live=False)) == 0
    assert world.main(world.argv("t1", "--attempt", "2")) == 1  # attempt 2 fails live
    assert world.public_pair("t1") == pair  # readers still read attempt 1's version
    rec = world.status_of("t1")
    assert (rec["state"], rec["run_id"], rec["attempts"]) == ("failed", f"{DATE}-t1-2", 1) and "boom" in rec["reason"]
    assert world.main(world.argv("t1", "--attempt", "2")) == 0  # its rerun publishes version 2
    done = world.public_of("t1")
    assert (done["state"], done["run_id"], done["attempts"]) == ("published", f"{DATE}-t1-2", 2)
    assert [r["status_seen"] for r in world.runs()] == ["running", "published", "published"]  # what the portal saw meanwhile


def test_a_later_attempt_rewrites_a_published_status_file_whose_hash_is_stale(world: Env):
    """A pair the install would refuse (its .sha256 does not match) is written again for the earlier run id, with
    started_at and attempts from the runner's record of that run."""
    world.scenario({"t1": [{"exit": 0}, {"exit": 1, "publish": False, "say": "boom"}]}, {"t1": {"fast": 100, "ultra": 0}})
    assert world.main(world.argv("t1")) == 0
    first = world.public_of("t1")
    (world.status / "t1" / f"{DATE}.json.sha256").write_text("0" * 64 + f"  {DATE}.json\n")
    assert world.main(world.argv("t1", "--attempt", "2")) == 1
    pub = world.public_of("t1", record=False)  # the hash matches again
    assert (pub["state"], pub["run_id"], pub["started_at"], pub["attempts"], pub["reason"]) == \
        ("published", f"{DATE}-t1-1", first["started_at"], 1, None)
    assert world.status_of("t1")["state"] == "failed"


def test_a_later_attempt_shows_a_version_published_outside_the_runner(world: Env):
    """No status file yet and attempt 1 published by run.py itself: attempt 2's failure leaves the file `published`
    with attempt 1's run id, dated by its snapshot."""
    d = world.out / "t1" / DATE
    d.mkdir(parents=True)
    old = {"run_id": f"{DATE}-t1-1", "topic_id": "t1", "edition_date": DATE, "status": "ok", "version": 1,
           "published_at": "2026-10-20T10:00:00Z"}
    (d / "v1.json").write_text(json.dumps(old))
    (d / "latest.json").write_text(json.dumps(old))
    world.scenario({"t1": [{"exit": 1, "publish": False, "say": "boom"}]})
    assert world.main(world.argv("t1", "--attempt", "2")) == 1
    pub = world.public_of("t1", record=False)
    assert pub == {"topic": "t1", "date": DATE, "state": "published", "run_id": f"{DATE}-t1-1", "started_at": "2026-10-20T10:00:00Z",
                   "updated_at": pub["updated_at"], "attempts": 0, "reason": None}
    assert (world.status_of("t1")["state"], world.status_of("t1")["run_id"]) == ("failed", f"{DATE}-t1-2")
    assert [r["status_seen"] for r in world.runs()] == ["published"]


def test_a_topic_that_waits_without_starting_is_not_dated_by_a_plan_run(world: Env):
    """`started_at` is the first live start, or, before one, when a live invocation first queued the run id; a plan
    run's time never reaches it (decision at Statuses.open)."""
    world.scenario({"t1": [{"exit": 0}]}, {"t1": {"fast": 300, "ultra": 30}})
    small = "QTEST_KEY_A=10/10"  # less than MIN_SEGMENT_CALLS of room: the topic waits without a start
    assert world.main(world.argv("t1", keys=small, live=False)) == 3
    world.set_record("t1", started_at="2026-10-20T06:00:00Z")  # the plan ran at 06:00
    assert world.main(world.argv("t1", keys=small)) == 3
    waiting = world.public_of("t1")
    assert (waiting["state"], waiting["attempts"]) == ("waiting_for_key", 0) and world.runs() == []
    assert waiting["started_at"] > "2026-10-20T06:00:00Z"
    world.set_record("t1", started_at="2026-10-20T10:00:00Z")  # the first live invocation queued it at 10:00
    assert world.main(world.argv("t1", keys=small)) == 3
    assert world.public_of("t1")["started_at"] == "2026-10-20T10:00:00Z"  # a later live invocation keeps it
    assert world.main(world.argv("t1", keys="QTEST_KEY_A")) == 0  # a rested key starts and publishes it
    done = world.public_of("t1")
    assert (done["state"], done["attempts"]) == ("published", 1) and done["started_at"] > "2026-10-20T10:00:00Z"


def test_a_plan_of_another_attempt_leaves_a_live_run_s_record_alone(world: Env):
    """One record per run id (decision at Statuses): the README's plan without --attempt (attempt 1) between two live
    invocations of attempt 2 neither restarts attempt 2's `attempts` nor re-dates it, and its second log is run02."""
    world.scenario({"t1": [{"exit": 3, "fast": 100}, {"exit": 0}]}, {"t1": {"fast": 300, "ultra": 0}})
    assert world.main(world.argv("t1", "--attempt", "2", keys="QTEST_KEY_A")) == 3  # its only key drains
    waiting = world.public_of("t1")
    assert (waiting["state"], waiting["run_id"], waiting["attempts"]) == ("waiting_for_key", f"{DATE}-t1-2", 1)
    world.set_record("t1", started_at="2026-10-20T10:00:00Z")  # attempt 2 first started at 10:00
    assert world.main(world.argv("t1", keys="QTEST_KEY_A", live=False)) == 0  # the README's step 1: attempt 1
    plan = world.status_of("t1")
    assert (plan["run_id"], plan["state"], plan["state_mode"]) == (f"{DATE}-t1-1", "queued", "dry")
    assert world.record_files() == ["_summary.json", "t1/1.json", "t1/2.json"]
    assert world.main(world.argv("t1", "--attempt", "2", keys="QTEST_KEY_A")) == 0  # the rested key resumes and publishes
    done = world.public_of("t1")
    assert (done["state"], done["run_id"], done["attempts"], done["started_at"]) == \
        ("published", f"{DATE}-t1-2", 2, "2026-10-20T10:00:00Z")
    assert [r["outcome"] for r in world.status_of("t1")["runs"]] == ["drained", "published"]
    assert [r["resume"] for r in world.runs()] == [False, True]
    assert sorted(p.name for p in world.logs.glob("*_run[0-9]*.log")) == [f"{DATE}_t1_a2_run01_QTEST_KEY_A.log", f"{DATE}_t1_a2_run02_QTEST_KEY_A.log"]


def test_a_rerun_of_a_published_attempt_after_a_plan_of_another_leaves_the_pair_alone(world: Env):
    """The README's step 3 ("the same command again") after a plan of another attempt: a run id found published leaves
    a pair that already says so byte-identical (decision at Statuses.keep_published), whichever attempt it is."""
    world.scenario({"t1": [{"exit": 1, "publish": False, "say": "boom"}, {"exit": 0}]}, {"t1": {"fast": 100, "ultra": 0}})
    assert world.main(world.argv("t1")) == 1  # attempt 1 fails live
    assert world.main(world.argv("t1", "--attempt", "2")) == 0  # attempt 2 publishes
    pair = world.age_public("t1")
    assert world.main(world.argv("t1", live=False)) == 1  # the README's plan: attempt 1, which failed live
    assert world.main(world.argv("t1", "--attempt", "2")) == 0  # "already published, skipped"
    assert world.public_pair("t1") == pair
    pub = world.public_of("t1", record=False)
    assert (pub["state"], pub["run_id"], pub["attempts"]) == ("published", f"{DATE}-t1-2", 1)
    assert world.status_of("t1")["reason"] == "already published by an earlier run" and len(world.runs()) == 2


def test_a_rerun_of_attempt_1_after_a_plan_of_attempt_2_leaves_the_pair_alone(world: Env):
    world.scenario({"t1": [{"exit": 0}]}, {"t1": {"fast": 100, "ultra": 0}})
    assert world.main(world.argv("t1")) == 0  # attempt 1 publishes
    pair = world.age_public("t1")
    assert world.main(world.argv("t1", "--attempt", "2", live=False)) == 0
    assert world.main(world.argv("t1")) == 0  # the same live command again: already published
    assert world.public_pair("t1") == pair and len(world.runs()) == 1
    assert (world.status_of("t1")["attempts"], world.status_of("t1")["state"]) == (1, "published")


def test_a_rerun_of_a_published_run_rewrites_a_pair_whose_hash_is_stale_from_its_record(world: Env):
    world.scenario({"t1": [{"exit": 0}]}, {"t1": {"fast": 100, "ultra": 0}})
    assert world.main(world.argv("t1")) == 0
    first = world.public_of("t1")
    (world.status / "t1" / f"{DATE}.json.sha256").write_text("0" * 64 + f"  {DATE}.json\n")
    assert world.main(world.argv("t1")) == 0  # already published: the pair the install would refuse is written again
    again = world.public_of("t1")  # the hash matches again, and the file equals the record
    assert (again["state"], again["run_id"], again["attempts"], again["started_at"]) == ("published", f"{DATE}-t1-1", 1, first["started_at"])
    assert again["reason"] == "already published by an earlier run"


def test_a_rerun_of_a_published_run_rewrites_a_pair_that_still_says_running(world: Env):
    """The runner died between the child's publish and its own record write, so the verified pair of this run id
    still says `running`: the rerun ("already published") writes `published` (decision at Statuses.keep_published)."""
    world.scenario({"t1": [{"exit": 0}]}, {"t1": {"fast": 100, "ultra": 0}})
    assert world.main(world.argv("t1")) == 0
    first = world.public_of("t1")
    world.age_public("t1", state="running", reason=None)
    world.set_record("t1", state="running")
    assert world.main(world.argv("t1")) == 0  # already published
    again = world.public_of("t1")  # the hash matches, and the file equals the record
    assert (again["state"], again["run_id"], again["attempts"], again["started_at"]) == ("published", f"{DATE}-t1-1", 1, first["started_at"])
    assert len(world.runs()) == 1


def test_a_rerun_of_a_run_published_by_hand_rewrites_a_pair_of_another_run_id(world: Env):
    """Attempt 2 published by hand (resume_with_next_key.sh) while the verified pair still shows attempt 1 published:
    the store's newest version is attempt 2's, so the rerun of --attempt 2 shows attempt 2 (decision at
    Statuses.keep_published)."""
    world.scenario({"t1": [{"exit": 0}]}, {"t1": {"fast": 100, "ultra": 0}})
    assert world.main(world.argv("t1")) == 0  # attempt 1 publishes version 1 through the runner
    assert world.public_of("t1")["run_id"] == f"{DATE}-t1-1"
    d = world.out / "t1" / DATE
    snap = {"run_id": f"{DATE}-t1-2", "topic_id": "t1", "edition_date": DATE, "status": "ok", "version": 2,
            "published_at": "2026-10-20T12:00:00Z"}
    (d / "v2.json").write_text(json.dumps(snap))
    (d / "latest.json").write_text(json.dumps(snap))
    assert world.main(world.argv("t1", "--attempt", "2")) == 0  # already published
    pub = world.public_of("t1")
    assert (pub["state"], pub["run_id"], pub["reason"]) == ("published", f"{DATE}-t1-2", "already published by an earlier run")
    assert len(world.runs()) == 1  # no run was started for attempt 2


def test_a_rerun_of_a_published_run_writes_a_missing_pair_from_its_record(world: Env):
    """The topic's status folder was deleted after its run published: the rerun ("already published") writes a
    verified pair with `published`, this run id and the record's `attempts` and `started_at` (decision at
    Statuses.keep_published)."""
    world.scenario({"t1": [{"exit": 0}]}, {"t1": {"fast": 100, "ultra": 0}})
    assert world.main(world.argv("t1")) == 0
    first = world.public_of("t1")
    shutil.rmtree(world.status / "t1")
    assert world.main(world.argv("t1")) == 0  # already published
    again = world.public_of("t1")  # the pair exists again, its hash matches, and the file equals the record
    assert (again["state"], again["run_id"], again["attempts"], again["started_at"]) == ("published", f"{DATE}-t1-1", 1, first["started_at"])
    assert len(world.runs()) == 1


def test_two_attempts_on_one_key_each_get_their_own_run_log(world: Env):
    """The first run of attempt 1 and the first run of attempt 2 on the same key write two logs, each holding its own
    run only, and each run id's record names its own file (decision at run_log_name)."""
    world.scenario({"t1": [{"exit": 1, "publish": False, "say": "boom"}, {"exit": 0}]}, {"t1": {"fast": 100, "ultra": 0}})
    assert world.main(world.argv("t1", keys="QTEST_KEY_A")) == 1  # attempt 1 fails live on key A
    assert world.main(world.argv("t1", "--attempt", "2", keys="QTEST_KEY_A")) == 0  # attempt 2 publishes on key A
    names = {1: f"{DATE}_t1_a1_run01_QTEST_KEY_A.log", 2: f"{DATE}_t1_a2_run01_QTEST_KEY_A.log"}
    assert sorted(p.name for p in world.logs.glob("*_run[0-9]*.log")) == sorted(names.values())
    for attempt, name in names.items():
        text = (world.logs / name).read_text(encoding="utf-8")
        headers = [ln for ln in text.splitlines() if ln.startswith("=== run")]
        assert len(headers) == 1 and f"=== run 1 of {DATE}-t1-{attempt} on QTEST_KEY_A " in headers[0], headers
        rec = world.status_of("t1", attempt)
        assert [r["log"] for r in rec["runs"]] == [name] and rec["log"] == name, rec
    assert len(world.runs()) == 2


def test_a_live_run_without_its_record_continues_from_its_status_file(world: Env):
    """A run whose record lost its live history (the layout before one record per run id, or a deleted _runner folder,
    here followed by a plan) takes `attempts` and `started_at` from a verified status file of its run id (decision at
    Statuses.open)."""
    world.scenario({"t1": [{"exit": 3, "fast": 100}, {"exit": 0}]}, {"t1": {"fast": 300, "ultra": 0}})
    assert world.main(world.argv("t1", "--attempt", "2", keys="QTEST_KEY_A")) == 3
    world.age_public("t1", started_at="2026-10-20T10:00:00Z")
    shutil.rmtree(world.status / "_runner")
    assert world.main(world.argv("t1", "--attempt", "2", keys="QTEST_KEY_A", live=False)) == 0
    assert (world.status_of("t1")["started_mode"], world.status_of("t1")["runs"]) == ("dry", [])
    assert world.main(world.argv("t1", "--attempt", "2", keys="QTEST_KEY_A")) == 0
    done = world.public_of("t1")
    assert (done["state"], done["attempts"], done["started_at"]) == ("published", 2, "2026-10-20T10:00:00Z")
    assert sorted(p.name for p in world.logs.glob("*_run[0-9]*.log")) == [f"{DATE}_t1_a2_run01_QTEST_KEY_A.log", f"{DATE}_t1_a2_run02_QTEST_KEY_A.log"]
    world.age_public("t1", run_id=f"{DATE}-t1-3", state="waiting_for_key", attempts=5)
    (world.status / "t1" / f"{DATE}.json.sha256").write_text("0" * 64 + f"  {DATE}.json\n")  # a file the install would refuse
    shutil.rmtree(world.status / "_runner")
    world.scenario({"t1": [{"exit": 3, "fast": 100}]}, {"t1": {"fast": 300, "ultra": 0}})
    assert world.main(world.argv("t1", "--attempt", "3", keys="QTEST_KEY_A")) == 3  # an unverified file gives nothing
    assert (world.status_of("t1")["attempts"], world.status_of("t1")["state"]) == (1, "waiting_for_key")


def test_a_later_attempt_takes_the_earlier_run_s_record_when_no_status_file_is_left(world: Env):
    """follow_store reads the shown run id's own record (decision at Statuses): with the status file gone, attempt 2's
    failure writes attempt 1's `published` from attempt 1's record, not from the snapshot."""
    world.scenario({"t1": [{"exit": 0}, {"exit": 1, "publish": False, "say": "boom"}]}, {"t1": {"fast": 100, "ultra": 0}})
    assert world.main(world.argv("t1")) == 0
    world.set_record("t1", started_at="2026-10-20T10:00:00Z")
    shutil.rmtree(world.status / "t1")
    assert world.main(world.argv("t1", "--attempt", "2")) == 1
    pub = world.public_of("t1", record=False)
    assert (pub["state"], pub["run_id"], pub["started_at"], pub["attempts"]) == ("published", f"{DATE}-t1-1", "2026-10-20T10:00:00Z", 1)
    assert (world.status_of("t1", 2)["state"], world.status_of("t1", 1)["state"]) == ("failed", "published")


def _record_live_popen(monkeypatch: pytest.MonkeyPatch, world: Env, delay_s: float = 0.0, on_live_start=None) -> list[subprocess.Popen]:
    """Every live child the runner starts (the fake run), in order; `on_live_start(started)` runs just before each
    Popen, `delay_s` holds each worker before its Popen."""
    live: list[subprocess.Popen] = []
    real = subprocess.Popen

    def recording(argv, *a, **k):
        is_live = str(world.tmp / "fake_run.py") in [str(x) for x in argv]
        if is_live:
            if on_live_start:
                on_live_start(list(live))
            time.sleep(delay_s)
        p = real(argv, *a, **k)
        if is_live:
            live.append(p)
        return p

    monkeypatch.setattr(re_mod.subprocess, "Popen", recording)
    return live


def _kill_alive(procs: list[subprocess.Popen]) -> None:
    for p in procs:
        if p.poll() is None:
            p.kill()
            p.wait(10)


def _failing_save(monkeypatch: pytest.MonkeyPatch, topic: str, state: str) -> None:
    real = re_mod.Statuses.save

    def save(self, t: str, **changes):
        if t == topic and changes.get("state") == state:
            raise OSError("status disk went away")
        return real(self, t, **changes)

    monkeypatch.setattr(re_mod.Statuses, "save", save)


def test_a_status_write_fault_stops_every_live_child_before_the_runner_ends(world: Env, monkeypatch: pytest.MonkeyPatch):
    world.scenario({"quick": [{"exit": 0}], "slow": [{"exit": 0, "sleep": 20}]})
    live = _record_live_popen(monkeypatch, world)
    _failing_save(monkeypatch, "quick", "published")
    t0 = time.monotonic()
    try:
        with pytest.raises(OSError, match="status disk went away"):
            world.main(world.argv("quick,slow"))
        assert len(live) == 2 and [p.poll() is not None for p in live] == [True, True]  # no child outlives the runner
    finally:
        _kill_alive(live)
    assert time.monotonic() - t0 < 15
    assert [r["topic"] for r in world.runs()] == ["quick"]  # slow was stopped in its sleep
    slow = world.public_of("slow")
    assert slow["state"] == "failed" and "interrupted" in slow["reason"]  # not left on `running`
    assert not (world.runner / ".runner.lock").exists()


def test_a_pump_fault_kills_the_child_before_its_key_takes_the_next_topic(world: Env, monkeypatch: pytest.MonkeyPatch):
    world.scenario({"first": [{"exit": 0, "echo": "POISON line", "sleep": 6}], "second": [{"exit": 0}]})
    alive_at_start: list[subprocess.Popen] = []
    live = _record_live_popen(monkeypatch, world, on_live_start=lambda started: alive_at_start.extend(p for p in started if p.poll() is None))
    real_raw = re_mod.Redactor.raw

    def raw(self, b: bytes) -> bytes:
        if b"POISON" in b:
            raise OSError("log disk full")
        return real_raw(self, b)

    monkeypatch.setattr(re_mod.Redactor, "raw", raw)
    try:
        assert world.main(world.argv("first,second", keys="QTEST_KEY_A")) == 1
    finally:
        _kill_alive(live)
    assert len(live) == 2 and alive_at_start == []  # one live process per key: the first had exited
    first = world.public_of("first")
    assert first["state"] == "failed" and "runner error: OSError: log disk full" in first["reason"]
    assert world.public_of("second")["state"] == "published"
    assert [r["topic"] for r in world.runs()] == ["second"]  # first was killed in its sleep


def test_a_child_that_starts_while_the_runner_stops_is_killed_at_once(world: Env, monkeypatch: pytest.MonkeyPatch):
    """t1's worker reaches its Popen after the main thread failed on t2's status write and began the stop."""
    world.scenario({"t1": [{"exit": 0, "sleep": 8}], "t2": [{"exit": 0, "sleep": 8}]})
    live = _record_live_popen(monkeypatch, world, delay_s=1.0)
    _failing_save(monkeypatch, "t2", "running")
    try:
        with pytest.raises(OSError, match="status disk went away"):
            world.main(world.argv("t1,t2"))
        assert len(live) == 1 and live[0].poll() is not None
    finally:
        _kill_alive(live)
    # the fake writes its record only after its 8 s sleep: none means it was killed before (no wall-clock bound, which
    # failed under load)
    assert world.runs() == []
    assert world.status_of("t1")["state"] == "failed" and "interrupted" in world.status_of("t1")["reason"]


@pytest.mark.parametrize("resume", [False, True])
def test_run_py_accepts_the_live_arguments(tmp_path: Path, resume: bool, capsys: pytest.CaptureFixture[str]):
    """run.py's own parser takes what the runner passes; --mermaid returns before any live path is reached."""
    from quorum_reasoning import run

    args = re_mod.live_args("climate-policy", "2026-10-26", tmp_path / "store", 2, resume)
    assert ("--resume" in args) is resume and args[args.index("--model") + 1] == "live"
    assert run.main(args + ["--mermaid"]) == 0
    assert capsys.readouterr().out.strip()  # the Mermaid text
    assert not (tmp_path / "store").exists()  # nothing was run


# ---------------------------------------------------------------------------------------------------------------------
# the dry check: the real one on the bundled fixture day (stand-ins, no network), and its guards in process


def test_dry_check_counts_calls_per_lane_on_the_fixture(tmp_path: Path):
    report = tmp_path / "r.json"
    env = dict(os.environ)
    env["MODEL_API_KEY"] = "must-not-be-used-0000"
    proc = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / "dry_check.py"), "--topic", "russia-ukraine-war", "--date", "2026-10-22",
                           "--corpus", "fixture", "--out", str(tmp_path / "dry"), "--report", str(report)],
                          cwd=str(REASONING), env=env, capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    rep = json.loads(report.read_text(encoding="utf-8"))
    calls = rep["calls"]
    assert calls["fast"] > 0 and calls["ultra"] > 0 and calls["total"] == calls["fast"] + calls["ultra"]
    assert calls["by_lane"]["default"] == calls["fast"] and calls["by_task"]["event_key"] > 0
    assert rep["snapshot_status"] == "ok" and rep["version"] == 1
    snap = json.loads((tmp_path / "dry" / "russia-ukraine-war" / "2026-10-22" / "v1.json").read_text(encoding="utf-8"))
    assert snap["provenance"]["model_calls"] == 0  # stand-ins only: no live call was counted


def test_dry_check_refuses_a_live_store(tmp_path: Path):
    (tmp_path / "store" / "_journal").mkdir(parents=True)
    proc = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / "dry_check.py"), "--topic", "t", "--date", "2026-10-22",
                           "--corpus", "fixture", "--out", str(tmp_path / "store")], cwd=str(REASONING), capture_output=True, text=True, timeout=120)
    assert proc.returncode == 2 and "holds live runs" in proc.stderr


def test_dry_check_isolation_blanks_every_model_credential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    names = ("MODEL_API_KEY", "METERLESS_TOKEN", "METERLESS_RUNTIME_TOKEN", "QTEST_KEY_X")
    for name in (*names, "QUORUM_DRY_RUN"):
        monkeypatch.setenv(name, "set-before-isolation-0000")  # monkeypatch restores each after the test
    env_file = tmp_path / ".env"
    env_file.write_text("MODEL_API_KEY=from-the-env-file-1111\nMETERLESS_TOKEN=from-the-env-file-2222\nQTEST_KEY_X=from-the-env-file-3333\n")
    dc_mod._isolate(str(env_file), ["QTEST_KEY_X"])
    assert {name: os.environ[name] for name in names} == {name: "" for name in names}  # blank, and the .env cannot refill them
    assert os.environ["QUORUM_DRY_RUN"] == "1"


def _guard_llm_seams(monkeypatch: pytest.MonkeyPatch):
    """estimate() replaces llm attributes for the rest of its process; in this process they are restored after the test."""
    from quorum_reasoning import llm, run

    for name in dc_mod.LLM_SEAMS:
        monkeypatch.setattr(llm, name, getattr(llm, name))
    monkeypatch.setattr(run, "main", run.main)
    return llm, run


def test_dry_check_estimate_replaces_every_live_seam_with_a_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    llm, run = _guard_llm_seams(monkeypatch)
    seen: dict[str, object] = {}

    def fake_main(argv: list[str]) -> int:  # inspects the seams; never calls a real one
        for name in ("_create", "_client", "disable_hmem_injection"):
            seen[name] = getattr(llm, name) is dc_mod._refuse
        seen["json_task"] = getattr(llm.json_task, "__name__", "")
        seen["model"] = argv[argv.index("--model") + 1]
        return 0

    monkeypatch.setattr(run, "main", fake_main)
    rep = dc_mod.estimate("t", "2026-10-22", tmp_path / "dry", "fixture", None)
    assert seen == {"_create": True, "_client": True, "disable_hmem_injection": True, "json_task": "counting", "model": "dry"}
    assert rep["calls"]["total"] == 0 and rep["exit_code"] == 0
    with pytest.raises(dc_mod.LiveCallRefused):
        dc_mod._refuse("m", [], 0.0, {})


def test_dry_check_fails_loudly_when_a_seam_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    llm, run = _guard_llm_seams(monkeypatch)
    monkeypatch.delattr(llm, "_client")
    monkeypatch.setattr(run, "main", lambda argv: pytest.fail("the graph ran without its refusal seams"))
    with pytest.raises(RuntimeError, match=r"llm\._client not found"):
        dc_mod.estimate("t", "2026-10-22", tmp_path / "dry", "fixture", None)


def test_dry_check_fails_when_a_live_call_was_refused_during_the_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    llm, run = _guard_llm_seams(monkeypatch)
    monkeypatch.setattr(llm, "json_task", lambda task, payload, *, dry_run, which="default": {})

    def fake_main(argv: list[str]) -> int:  # a node whose dry switch broke: its broad except swallows the refusal
        try:
            llm._create("m", [], 0.0, {})
        except Exception:  # noqa: BLE001
            pass
        llm.json_task("event_key", {}, dry_run=True)
        return 0

    monkeypatch.setattr(run, "main", fake_main)
    rep = dc_mod.estimate("t", "2026-10-22", tmp_path / "dry", "fixture", None)
    assert rep["refused_calls"] == 1 and "1 live model or control-plane call(s) attempted and refused" in rep["error"]
    assert rep["calls"]["fast"] == 1 and rep["exit_code"] == 0  # the counts stay for diagnosis


def test_dry_check_fails_when_the_graph_exits_other_than_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    llm, run = _guard_llm_seams(monkeypatch)
    monkeypatch.setattr(run, "main", lambda argv: 2)  # a partial snapshot (or a refusal) of the dry run
    rep = dc_mod.estimate("t", "2026-10-22", tmp_path / "dry", "fixture", None)
    assert rep["exit_code"] == 2 and rep["error"] == "dry check: graph exit 2, snapshot not stored"


def test_dry_check_cli_exits_1_on_a_report_with_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Counts with an `error` are no estimate: dry_check.py exits 1, so the runner fails the topic."""
    monkeypatch.setattr(dc_mod, "_isolate", lambda env_file, blank: None)
    monkeypatch.setattr(dc_mod, "estimate", lambda *a: {"topic": "t", "calls": {"total": 5, "fast": 5, "ultra": 0}, "snapshot_status": "partial",
                                                       "error": "dry check: graph exit 2, snapshot partial"})
    report = tmp_path / "r.json"
    assert dc_mod.main(["--topic", "t", "--date", "2026-10-22", "--out", str(tmp_path / "dry"), "--report", str(report)]) == 1
    assert json.loads(report.read_text(encoding="utf-8"))["error"].endswith("snapshot partial")


def test_dry_check_counting_passes_further_keywords_through(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    llm, run = _guard_llm_seams(monkeypatch)
    seen: dict[str, object] = {}

    def original(task, payload, *, dry_run, which="default", **more):
        seen.update(more, dry_run=dry_run, which=which)
        return {}

    monkeypatch.setattr(llm, "json_task", original)
    monkeypatch.setattr(run, "main", lambda argv: (llm.json_task("stance", {}, dry_run=False, which="fact_checker", budget=3), 0)[1])
    rep = dc_mod.estimate("t", "2026-10-22", tmp_path / "dry", "fixture", None)
    assert seen == {"budget": 3, "dry_run": True, "which": "fact_checker"} and rep["calls"]["ultra"] == 1 and "error" not in rep


def test_list_topics_reads_active_rows_in_collection_order_and_reports_bad_ids(monkeypatch: pytest.MonkeyPatch):
    from quorum_reasoning.tools import corpus

    sqls: list[str] = []

    def fake_sql(sql: str, limit: int):
        sqls.append(sql)
        return [{"id": "climate-policy"}, {"id": "ai--jobs"}, {"id": "covid-19-"}, {"id": "Not A Slug"}, {"id": "climate-policy"}, {"id": "nul"}]

    monkeypatch.setattr(corpus, "_run_sql", fake_sql)
    got = dc_mod.list_topics()
    assert got["filtered"] is True and got["topics"] == ["climate-policy", "ai--jobs", "covid-19-"]
    assert [s["id"] for s in got["skipped"]] == ["Not A Slug", "nul"] and "device name" in got["skipped"][1]["reason"]
    assert len(sqls) == 1 and sqls[0].endswith(".topics WHERE active ORDER BY created_at, id")


def test_list_topics_falls_back_to_every_row_while_zetaris_lacks_the_columns(monkeypatch: pytest.MonkeyPatch):
    from quorum_reasoning.tools import corpus

    sqls: list[str] = []

    def fake_sql(sql: str, limit: int):
        sqls.append(sql)
        if "WHERE active" in sql:
            raise RuntimeError("Zetaris REST HTTP 400; body withheld")
        return [{"id": "b-topic"}, {"id": "a-topic"}]

    monkeypatch.setattr(corpus, "_run_sql", fake_sql)
    assert dc_mod.list_topics() == {"topics": ["b-topic", "a-topic"], "filtered": False, "skipped": []}
    assert len(sqls) == 2 and "WHERE" not in sqls[1]

    def down(sql: str, limit: int):
        raise RuntimeError("Zetaris REST HTTP 503; body withheld")

    monkeypatch.setattr(corpus, "_run_sql", down)
    with pytest.raises(RuntimeError, match="503"):  # two attempts at most, then the error
        dc_mod.list_topics()


# ---------------------------------------------------------------------------------------------------------------------
# resume_with_next_key.sh


def _git_bash() -> str | None:
    """A POSIX bash: `bash` on PATH unless it is the WSL launcher (PowerShell and cmd find that one first), else Git for
    Windows' own bash next to git.exe or under Program Files."""
    found = shutil.which("bash")
    if found and not (os.name == "nt" and any(s in found.lower() for s in ("system32", "windowsapps"))):
        return found
    if os.name != "nt":
        return None
    roots: list[Path] = []
    git = shutil.which("git")
    if git:
        roots += list(Path(git).resolve().parents)[1:3]  # ...\Git\cmd\git.exe or ...\Git\mingw64\bin\git.exe
    for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        if os.environ.get(var):
            roots.append(Path(os.environ[var]) / "Git")
    for root in roots:
        for rel in ("bin/bash.exe", "usr/bin/bash.exe"):
            if (root / rel).is_file():
                return str(root / rel)
    return None


FAKE_PACKAGE_RUN = r'''
import json, os, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
sc = json.loads(Path(os.environ["FAKE_SCENARIO"]).read_text())
rec = Path(sc["records"])
n = len(rec.read_text().splitlines()) if rec.exists() else 0
codes = sc["codes"]
# what run.py does first: llm._env() loads the repo .env with load_dotenv(override=False) (child_env_file: when the
# script's --env-file is another file than the one the run loads)
for line in Path(sc.get("child_env_file") or sc["env_file"]).read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        if k not in os.environ:
            os.environ[k] = v
key = os.environ.get("MODEL_API_KEY", "")

def argv_holders(value):
    """Names of the running processes whose command line holds `value` (looked up while this run is alive; the value
    reaches the lookup through its environment only)."""
    if os.name == "nt":
        ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        script = ("$v = $env:QPROBE_VALUE; @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and "
                  "$_.CommandLine.Contains($v) } | ForEach-Object { $_.Name }) -join ','")
        p = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-Command", script], env=dict(os.environ, QPROBE_VALUE=value),
                           capture_output=True, text=True, timeout=120)
        return p.stdout.strip() if p.returncode == 0 else f"scan failed: {p.returncode}"
    hits = []
    for f in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            if value.encode() in f.read_bytes():
                hits.append(f.parent.name)
        except OSError:
            pass
    return ",".join(hits)

# the listed names, an exported MODEL_API_KEY_6 and the env file's MODEL_API_KEY_7 must all reach this process blank
row = {"argv": args, "key": sc["values"].get(key, "?"), "dry_env": os.environ.get("QUORUM_DRY_RUN"), "base_url": os.environ.get("MODEL_BASE_URL"),
       "blank_ok": all(os.environ.get(n, "") == "" for n in ("QTEST_KEY_A", "QTEST_KEY_B", "MODEL_API_KEY_6", "MODEL_API_KEY_7"))}
if sc.get("scan"):
    row["holders"] = argv_holders(key)
    row["control"] = argv_holders("-m quorum_reasoning.run --topic")  # this very process: proves the lookup works
print(f"fake run sees MODEL_API_KEY={key}")
with rec.open("a") as fh:
    fh.write(json.dumps(row) + "\n")
sys.exit(codes[min(n, len(codes) - 1)])
'''


DIRECT_URL = "https://integrate.api.nvidia.com/v1"


def _run_resume_script(tmp_path: Path, codes: list[int], values: tuple[str, str], scan: bool = False, topic: str = "climate-policy",
                       flags: tuple[str, ...] = (), extra: tuple[str, ...] = ("--quiet",), file_base_url: str | None = DIRECT_URL,
                       exported_base_url: str | None = "", child_env: str | None = None) -> tuple[subprocess.CompletedProcess, list[dict], str]:
    """`flags` go before `--`, `extra` after it (run.py arguments); MODEL_BASE_URL is `file_base_url` in the env file
    (None: not there) and `exported_base_url` in the environment (blank: the env file's counts; None: not in the
    environment at all); `child_env` is the text of the .env the run itself loads, as llm._env loads the repository's
    (None: the script's env file)."""
    pkg = tmp_path / "work" / "quorum_reasoning"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "run.py").write_text(FAKE_PACKAGE_RUN)
    env_file = tmp_path / ".env"
    env_file.write_text(f"QTEST_KEY_A={values[0]}\nQTEST_KEY_B={values[1]}\nMODEL_API_KEY_7=fake-env-file-key-7777\n"
                        + (f"MODEL_BASE_URL={file_base_url}\n" if file_base_url is not None else ""))
    child_env_file = None
    if child_env is not None:
        child_env_file = tmp_path / "repo.env"
        child_env_file.write_text(child_env)
    records = tmp_path / "records.jsonl"
    (tmp_path / "scenario.json").write_text(json.dumps({"records": str(records), "codes": codes, "env_file": str(env_file), "scan": scan,
                                                        "child_env_file": str(child_env_file) if child_env_file else None,
                                                        "values": {values[0]: "QTEST_KEY_A", values[1]: "QTEST_KEY_B"}}))
    log = tmp_path / "run.log"
    env = {k: v for k, v in os.environ.items() if not k.startswith("QTEST_")}
    env["FAKE_SCENARIO"] = str(tmp_path / "scenario.json")
    env["MODEL_API_KEY_6"] = "fake-exported-key-6666"
    # fail closed: the script hardcodes --model live; if --workdir ever stops reaching the child, the real run.py refuses
    # (QUORUM_DRY_RUN=1, exit 2) and the repo .env cannot fill in a route (load_dotenv never overrides a set variable)
    env["QUORUM_DRY_RUN"] = "1"
    for name in ("METERLESS_TOKEN", "METERLESS_RUNTIME_TOKEN", "MODEL_BASE_URL"):
        env[name] = ""
    if exported_base_url is None:
        del env["MODEL_BASE_URL"]  # the run's own load_dotenv may fill it in (QUORUM_DRY_RUN=1 still guards the real run.py)
    else:
        env["MODEL_BASE_URL"] = exported_base_url
    proc = subprocess.run([_git_bash(), str(SCRIPTS / "resume_with_next_key.sh"), "--topic", topic, "--date", DATE,
                           "--attempt", "2", "--out", str(tmp_path / "store"), "--log", str(log), "--keys", "QTEST_KEY_A,QTEST_KEY_B",
                           "--env-file", str(env_file), "--python", sys.executable, "--workdir", str(tmp_path / "work"), *flags, "--", *extra],
                          env=env, capture_output=True, text=True, timeout=300)
    rows = [json.loads(line) for line in records.read_text().splitlines()] if records.exists() else []
    return proc, rows, (log.read_text(encoding="utf-8") if log.exists() else "") + proc.stdout + proc.stderr


@pytest.mark.skipif(_git_bash() is None, reason="needs Git Bash (or a POSIX bash), not the WSL launcher")
@pytest.mark.parametrize("codes,expected,keys_used", [([3, 0], 0, ["QTEST_KEY_A", "QTEST_KEY_B"]), ([3, 3], 3, ["QTEST_KEY_A", "QTEST_KEY_B"]), ([1], 1, ["QTEST_KEY_A"])])
def test_resume_with_next_key_rotates_on_exit_3(tmp_path: Path, codes: list[int], expected: int, keys_used: list[str]):
    proc, rows, text = _run_resume_script(tmp_path, codes, (VALUE_A, VALUE_B))
    assert proc.returncode == expected, text
    assert [r["key"] for r in rows] == keys_used
    assert ["--resume" in r["argv"] for r in rows] == [False, True][: len(rows)]
    assert all("--quiet" in r["argv"] and "--attempt" in r["argv"] for r in rows)
    assert all(r["blank_ok"] for r in rows)  # the other listed key, an exported and an env-file MODEL_API_KEY_*
    assert all(r["dry_env"] == "1" for r in rows)  # the fail-closed guard reaches the child
    assert VALUE_A not in text and VALUE_B not in text and "MODEL_API_KEY=[redacted]" in text
    assert f"live exit={codes[0]} (QTEST_KEY_A)" in text


@pytest.mark.skipif(_git_bash() is None, reason="needs Git Bash (or a POSIX bash), not the WSL launcher")
@pytest.mark.parametrize("topic", ["../etc", "a.b", "con", "nul"])
def test_resume_with_next_key_refuses_a_topic_off_the_shared_rule(tmp_path: Path, topic: str):
    proc, rows, text = _run_resume_script(tmp_path, [0], (VALUE_A, VALUE_B), topic=topic)
    assert proc.returncode == 2 and rows == [], text
    assert "--topic" in proc.stderr


@pytest.mark.skipif(_git_bash() is None, reason="needs Git Bash (or a POSIX bash), not the WSL launcher")
def test_resume_with_next_key_takes_a_topic_by_the_shared_rule(tmp_path: Path):
    proc, rows, text = _run_resume_script(tmp_path, [0], (VALUE_A, VALUE_B), topic="ai--jobs")
    assert proc.returncode == 0, text
    row, = rows
    assert row["argv"][row["argv"].index("--topic") + 1] == "ai--jobs"


@pytest.mark.skipif(_git_bash() is None, reason="needs Git Bash (or a POSIX bash), not the WSL launcher")
@pytest.mark.parametrize("extra", [("--model", "dry"), ("--model=dry",), ("--out", "elsewhere"), ("--resume",),
                                   # unique prefixes run.py's parser expands (allow_abbrev): the last value would win
                                   ("--ou", "elsewhere"), ("--corp", "fixture"), ("--att", "9"), ("--res",), ("--seed",),
                                   # modes that replace the run and exit 0 (the first two send paid completions)
                                   ("--test-connection",), ("--test-c",), ("--probe",), ("--models",), ("--list",), ("--mermaid",),
                                   ("--quiet", "--fixture", "x"), ("--quiet=1",)])
def test_resume_with_next_key_refuses_run_arguments_it_does_not_pass_through(tmp_path: Path, extra: tuple[str, ...]):
    """After `--` only --quiet, --verbose and --checkpoint, spelled exactly (decision in the script header)."""
    proc, rows, text = _run_resume_script(tmp_path, [0], (VALUE_A, VALUE_B), extra=extra)
    assert proc.returncode == 2 and rows == [], text
    assert "not passed through" in proc.stderr and "final exit" not in proc.stdout


@pytest.mark.skipif(_git_bash() is None, reason="needs Git Bash (or a POSIX bash), not the WSL launcher")
def test_resume_with_next_key_passes_the_allowed_extras_through(tmp_path: Path):
    proc, rows, text = _run_resume_script(tmp_path, [0], (VALUE_A, VALUE_B), extra=("--quiet", "--verbose", "--checkpoint"))
    assert proc.returncode == 0, text
    row, = rows
    assert row["argv"][-3:] == ["--quiet", "--verbose", "--checkpoint"]


@pytest.mark.skipif(_git_bash() is None, reason="needs Git Bash (or a POSIX bash), not the WSL launcher")
@pytest.mark.parametrize("file_url,exported_url", [("http://127.0.0.1:8088/v1", ""), (DIRECT_URL, "http://127.0.0.1:8088/v1"), (None, ""),
                                                   ("https://integrate.api.nvidia.com.example.org/v1", "")])
def test_resume_with_next_key_refuses_a_route_other_than_direct_nvidia(tmp_path: Path, file_url: str | None, exported_url: str):
    """The Meterless route (the README's Nightshift URL in MODEL_BASE_URL), no URL, or a look-alike host: exit 2 before
    any run, so no NVIDIA key is ever sent as the bearer to another service; an exported URL wins over the env file."""
    proc, rows, text = _run_resume_script(tmp_path, [3, 0], (VALUE_A, VALUE_B), file_base_url=file_url, exported_base_url=exported_url)
    assert proc.returncode == 2 and rows == [], text
    assert "not NVIDIA's direct route" in proc.stderr and VALUE_A not in text and VALUE_B not in text


@pytest.mark.skipif(_git_bash() is None, reason="needs Git Bash (or a POSIX bash), not the WSL launcher")
def test_resume_with_next_key_takes_an_exported_direct_url_over_the_env_file(tmp_path: Path):
    proc, rows, text = _run_resume_script(tmp_path, [0], (VALUE_A, VALUE_B), file_base_url="http://127.0.0.1:8088/v1", exported_base_url=DIRECT_URL)
    assert proc.returncode == 0, text
    assert [r["key"] for r in rows] == ["QTEST_KEY_A"]


@pytest.mark.skipif(_git_bash() is None, reason="needs Git Bash (or a POSIX bash), not the WSL launcher")
def test_resume_with_next_key_hands_the_checked_url_to_the_run(tmp_path: Path):
    """--env-file names another file than the one the run loads itself (llm._env: the repository's .env, override=False)
    and MODEL_BASE_URL is not exported: every run gets the URL the route check passed, not its own .env's Meterless URL,
    so no NVIDIA key goes to the Meterless daemon (decision in the script header)."""
    proc, rows, text = _run_resume_script(tmp_path, [3, 0], (VALUE_A, VALUE_B), exported_base_url=None,
                                          child_env="MODEL_BASE_URL=http://127.0.0.1:8088/v1\n")
    assert proc.returncode == 0, text
    assert [(r["key"], r["base_url"]) for r in rows] == [("QTEST_KEY_A", DIRECT_URL), ("QTEST_KEY_B", DIRECT_URL)]


@pytest.mark.skipif(_git_bash() is None, reason="needs Git Bash (or a POSIX bash), not the WSL launcher")
def test_resume_with_next_key_resume_flag_continues_from_the_first_run(tmp_path: Path):
    """A run that drained elsewhere: the first run on the listed keys already resumes."""
    proc, rows, text = _run_resume_script(tmp_path, [3, 0], (VALUE_A, VALUE_B), flags=("--resume",))
    assert proc.returncode == 0, text
    assert [(r["key"], "--resume" in r["argv"]) for r in rows] == [("QTEST_KEY_A", True), ("QTEST_KEY_B", True)]


@pytest.mark.skipif(_git_bash() is None, reason="needs Git Bash (or a POSIX bash), not the WSL launcher")
def test_resume_with_next_key_keeps_the_key_off_every_command_line(tmp_path: Path):
    """While the run is alive no process (an `env` program, a wrapper shell, the run itself) shows the key value in its
    command line; the value is unique to this test, so no other test's process can match it."""
    values = (f"fake-key-scan-{uuid.uuid4().hex}", f"fake-key-scan-{uuid.uuid4().hex}")
    proc, rows, text = _run_resume_script(tmp_path, [0], values, scan=True)
    assert proc.returncode == 0, text
    row, = rows
    assert row["key"] == "QTEST_KEY_A" and row["control"] and not row["control"].startswith("scan failed"), row
    assert row["holders"] == "", row


def test_resume_with_next_key_never_calls_the_env_program():
    """Static half of the check above, for machines without Git Bash: no code line runs `env` (it would take the key
    as an argument) and the key is exported inside the run's subshell."""
    text = (SCRIPTS / "resume_with_next_key.sh").read_text(encoding="utf-8")
    code = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    env_call = re.compile(r"(?:^|[\s(;&|])(?:/usr/bin/)?env\s+(?:[\"'$-]|[A-Za-z_][A-Za-z0-9_]*=)")  # env "$X" / env -i / env NAME=
    assert env_call.search('( cd "$WORKDIR" && env "${BLANK[@]}" "MODEL_API_KEY=$key" "$PY"') and env_call.search("env MODEL_API_KEY=1 x")
    assert [line for line in code if env_call.search(line)] == []
    assert 'export MODEL_API_KEY="$key"' in text and 'exec "$PY" -X utf8 -m quorum_reasoning.run' in text
