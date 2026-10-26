"""scripts/run_editions.py and scripts/resume_with_next_key.sh, fully offline: fake child commands stand in for run.py
and the dry check (exit 0 / 2 / 3 / 1, slow, crash); no model, no Zetaris, no control plane is ever reached."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REASONING = Path(__file__).resolve().parents[1]
SCRIPTS = REASONING / "scripts"

_spec = importlib.util.spec_from_file_location("run_editions", SCRIPTS / "run_editions.py")
re_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["run_editions"] = re_mod
_spec.loader.exec_module(re_mod)

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
        seen = json.loads((Path(sd) / date / f"{topic}.json").read_text())["state"]
    except Exception:
        seen = "unreadable"
rec = {"topic": topic, "argv": args, "resume": "--resume" in args, "key_name": sc["values"].get(key, "?" if key else ""),
       "blank_ok": all(os.environ.get(nm, "") == "" for nm in sc.get("blank_expected", [])), "status_seen": seen,
       "start": time.time()}
if sc.get("echo_key"):
    print(f"stdout sees MODEL_API_KEY={key}", flush=True)
    print(f"stderr sees {key}", file=sys.stderr, flush=True)
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
    print(json.dumps(sc["db_topics"]))
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
        for name in ("QTEST_KEY_A", "QTEST_KEY_B", "QTEST_KEY_C"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("FAKE_SCENARIO", str(tmp / "scenario.json"))
        monkeypatch.setenv("FAKE_STATUS_DIR", str(self.status))
        self.scenario({})

    def scenario(self, live: dict, dry: dict | None = None, **extra) -> None:
        sc = {"live": live, "dry": dry or {}, "records": str(self.records), "dry_records": str(self.dry_records), "env_file": str(self.env_file),
              "values": {VALUE_A: "QTEST_KEY_A", VALUE_B: "QTEST_KEY_B", VALUE_C: "QTEST_KEY_C"},
              "blank_expected": ["QTEST_KEY_A", "QTEST_KEY_B", "MODEL_API_KEY_9"], "db_topics": []}  # the --keys names and any MODEL_API_KEY_*
        sc.update(extra)
        (self.tmp / "scenario.json").write_text(json.dumps(sc))

    def argv(self, topics: str, *more: str, keys: str | None = "QTEST_KEY_A,QTEST_KEY_B", live: bool = True) -> list[str]:
        a = ["--date", DATE, "--topics", topics, "--out", str(self.out), "--log-dir", str(self.logs), "--status-dir", str(self.status),
             "--dry-check-out", str(self.dry), "--estimate-factor", "1"]
        if keys:
            a += ["--keys", keys]
        if live:
            a.append("--live")
        return a + list(more)

    def main(self, argv: list[str]) -> int:
        # -I -S: the fakes need only the standard library, and a bare interpreter starts several times faster on Windows
        return re_mod.main(argv, live_cmd=[sys.executable, "-I", "-S", str(self.tmp / "fake_run.py")],
                           dry_cmd=[sys.executable, "-I", "-S", str(self.tmp / "fake_dry.py")])

    def runs(self) -> list[dict]:
        """Every fake live run, in the order they started."""
        rows = [json.loads(p.read_text()) for p in self.records.glob("*.json")] if self.records.is_dir() else []
        return sorted(rows, key=lambda r: r["start"])

    def dry_runs(self) -> list[dict]:
        return [json.loads(p.read_text()) for p in self.dry_records.glob("*.json")] if self.dry_records.is_dir() else []

    def status_of(self, topic: str) -> dict:
        return json.loads((self.status / DATE / f"{topic}.json").read_text(encoding="utf-8"))


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
    assert p.place() == [] and [i.topic for i, _ in p.take_waiting()] == ["next"]  # 310 left on B: never placed whole
    assert keys[1].used_fast == 340 and p.holds == {}


def test_waiting_for_key_when_all_keys_together_lack_room_and_drained_keys_take_nothing():
    keys = [K("A"), K("B")]
    p = re_mod.Planner(keys, [re_mod.Item("huge", 2000, 0), re_mod.Item("small", 100, 0)])
    started = p.place()
    assert [(i.topic, k.name) for i, k, _ in started] == [("small", "A")]
    (huge, reason), = p.take_waiting()  # 2000 calls against 1300 on both keys together: never placeable today
    assert huge.topic == "huge" and "needs about 2000 fast-lane" in reason and "1300" in reason
    i, k, res = started[0]
    p.finish(i, k, res, "drained", (100, 0))
    (i2, k2, _), = p.place()
    assert (i2.topic, k2.name, i2.resume) == ("small", "B", True)  # never back on the drained key
    p.finish(i2, k2, _, "drained", (5, 0))
    assert p.place() == []
    assert "every key is drained" in p.take_waiting()[0][1]
    keys[1].drained = True
    p2 = re_mod.Planner(keys, [re_mod.Item("x", 1, 0)])
    assert p2.place() == [] and "every key is drained" in p2.take_waiting()[0][1]


def test_unknown_remainder_after_estimate_is_used_up():
    it = re_mod.Item("t", 100, 0, done_fast=150)
    assert it.need() == (re_mod.MIN_SEGMENT_CALLS, 0)


def test_simulated_plan_shows_segments_and_waiting():
    plan = re_mod.simulate([K("A"), K("B")], [re_mod.Item("big", 1000, 50), re_mod.Item("next", 400, 40)])
    assert [s["key"] for s in plan["big"]["segments"]] == ["A", "B"]
    assert [s["resume"] for s in plan["big"]["segments"]] == [False, True]
    assert plan["big"]["outcome"] == "published"
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
    st = world.status_of("t1")
    assert st["state"] == "published" and st["version"] == 1 and st["attempts"] == 2
    assert [r["outcome"] for r in st["runs"]] == ["drained", "published"]
    assert st["runs"][0]["calls"] == {"fast": 200, "ultra": 0}
    assert st["calls_estimate"] == 330 and st["calls_estimate_lanes"] == {"fast": 300, "ultra": 30}
    assert {"topic", "date", "state", "run_id", "started_at", "updated_at", "attempts"} <= set(st)
    assert (world.logs / f"{DATE}_t1_run01_QTEST_KEY_A.log").is_file()
    assert (world.logs / f"{DATE}_t1_run02_QTEST_KEY_B.log").is_file()
    summary = json.loads((world.status / DATE / "_summary.json").read_text())
    assert [k["drained"] for k in summary["keys"]] == [True, False]


def test_failures_do_not_stop_the_rest_and_have_short_reasons(world: Env):
    world.scenario({
        "ok": [{"exit": 0, "fast": 10}],
        "crash": [{"crash": True, "fast": 5}],
        "refused": [{"exit": 2, "publish": False, "say": "refusing to run: --model live with a mixed model route"}],
        "partial": [{"exit": 2, "publish": True, "status": "partial"}],
        "odd": [{"exit": 7, "publish": False, "say": "something odd"}],
    })
    rc = world.main(world.argv("ok,crash,refused,partial,odd", keys="QTEST_KEY_A,QTEST_KEY_B,QTEST_KEY_C"))
    assert rc == 1
    assert world.status_of("ok")["state"] == "published"
    crash = world.status_of("crash")
    assert crash["state"] == "failed" and "RuntimeError: boom in the fake run" in crash["reason"] and crash["exit_code"] == 1
    refused = world.status_of("refused")
    assert refused["state"] == "failed" and refused["reason"].startswith("exit 2: refusing to run: --model live with a mixed")
    partial = world.status_of("partial")
    assert partial["state"] == "published" and partial["snapshot_status"] == "partial" and "partial" in partial["reason"]
    assert world.status_of("odd")["reason"] == "exit 7: something odd"
    assert len(world.runs()) == 5


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


def test_slow_runs_on_two_keys_overlap_and_the_status_says_running(world: Env):
    world.scenario({"s1": [{"exit": 0, "sleep": 1.2}], "s2": [{"exit": 0, "sleep": 1.2}]})
    t0 = time.monotonic()
    assert world.main(world.argv("s1,s2")) == 0
    runs = {r["topic"]: r for r in world.runs()}
    assert runs["s1"]["start"] < runs["s2"]["end"] and runs["s2"]["start"] < runs["s1"]["end"]  # one process per key, in parallel
    assert {r["key_name"] for r in runs.values()} == {"QTEST_KEY_A", "QTEST_KEY_B"}
    assert all(r["status_seen"] == "running" for r in runs.values())
    assert time.monotonic() - t0 < 2.4 + 6  # not serial (2.4 s of sleeps) plus generous process start-up


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
    rc = re_mod.main(world.argv("t1"), live_cmd=[str(world.tmp / "no-such-interpreter.exe")],
                     dry_cmd=[sys.executable, "-I", "-S", str(world.tmp / "fake_dry.py")])
    assert rc == 1
    st = world.status_of("t1")
    assert st["state"] == "failed" and st["reason"].startswith("could not start the run")


def test_no_key_value_reaches_a_log_or_a_status_file(world: Env):
    world.scenario({"t1": [{"exit": 3, "fast": 10}, {"exit": 0}], "t2": [{"crash": True}]}, echo_key=True)
    world.main(world.argv("t1,t2", keys="QTEST_KEY_A,QTEST_KEY_B,QTEST_KEY_C"))
    text = _all_text(world.logs, world.status)
    for value in (VALUE_A, VALUE_B, VALUE_C):
        assert value not in text
    assert "MODEL_API_KEY=[redacted]" in (world.logs / f"{DATE}_t1_run01_QTEST_KEY_A.log").read_text(encoding="utf-8")
    assert "stderr sees [redacted]" in text
    for p in (world.status / DATE).glob("*.json"):
        doc = p.read_text(encoding="utf-8")
        assert str(world.tmp) not in doc and str(world.tmp).replace("\\", "\\\\") not in doc  # no absolute paths


def test_without_live_only_dry_checks_run(world: Env):
    world.scenario({"t1": [{"exit": 0}]}, {"t1": {"fast": 900, "ultra": 20}, "t2": {"fast": 100, "ultra": 0}})
    rc = world.main(world.argv("t1,t2", live=False))
    assert rc == 0
    assert world.runs() == [] and not (world.out / "_journal").exists()  # nothing live was started
    dry = world.dry_runs()
    assert sorted(d["topic"] for d in dry) == ["t1", "t2"]
    assert all(d["dry_env"] == "1" and d["model_key"] == "" for d in dry)
    assert all("QTEST_KEY_A" in d["blank"].split(",") for d in dry)
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


def test_topics_all_reads_the_topics_table(world: Env):
    world.scenario({}, {}, db_topics=["alpha-topic", "beta-topic", "Not A Slug"])
    assert world.main(world.argv("all", live=False)) == 0
    assert sorted(d["topic"] for d in world.dry_runs()) == ["alpha-topic", "beta-topic"]


def test_route_mode_injects_no_key(world: Env):
    world.scenario({"t1": [{"exit": 0}]}, blank_expected=[])
    assert world.main(world.argv("t1", keys=None)) == 0
    run, = world.runs()
    assert run["key_name"] == "?" or run["key_name"] == ""  # whatever the environment holds; the runner set nothing
    assert world.status_of("t1")["key"] == re_mod.ROUTE


@pytest.mark.parametrize("case", ["dry_inside_out", "meterless_with_keys", "before_cut", "unusable_key", "env_file_live", "bad_topic", "lock"])
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
    elif case == "lock":
        (world.status / DATE).mkdir(parents=True)
        (world.status / DATE / ".runner.lock").write_text("{}")
    assert world.main(argv) == 2
    assert world.runs() == [] and world.dry_runs() == []


def test_dry_mode_may_run_before_the_cut(world: Env):
    world.scenario({}, {"t1": {"fast": 10, "ultra": 0}})
    argv = world.argv("t1", live=False)
    argv[argv.index("--date") + 1] = "2099-01-01"
    assert world.main(argv) == 0


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
# the real dry check, on the bundled fixture day (stand-ins, no network)


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


# ---------------------------------------------------------------------------------------------------------------------
# resume_with_next_key.sh


def _git_bash() -> str | None:
    found = shutil.which("bash")
    if not found:
        return None
    low = found.lower()
    if os.name == "nt" and ("system32" in low or "windowsapps" in low):  # the WSL launcher, not Git Bash
        return None
    return found


FAKE_PACKAGE_RUN = r'''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
sc = json.loads(Path(os.environ["FAKE_SCENARIO"]).read_text())
rec = Path(sc["records"])
n = len(rec.read_text().splitlines()) if rec.exists() else 0
codes = sc["codes"]
# what run.py does first: llm._env() loads the repo .env with load_dotenv(override=False)
for line in Path(sc["env_file"]).read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        if k not in os.environ:
            os.environ[k] = v
key = os.environ.get("MODEL_API_KEY", "")
print(f"fake run sees MODEL_API_KEY={key}")
with rec.open("a") as fh:
    fh.write(json.dumps({"argv": args, "key": sc["values"].get(key, "?"), "blank_ok": os.environ.get("QTEST_KEY_A", "") == "" and os.environ.get("QTEST_KEY_B", "") == ""}) + "\n")
sys.exit(codes[min(n, len(codes) - 1)])
'''


@pytest.mark.skipif(_git_bash() is None, reason="needs Git Bash (or a POSIX bash), not the WSL launcher")
@pytest.mark.parametrize("codes,expected,keys_used", [([3, 0], 0, ["QTEST_KEY_A", "QTEST_KEY_B"]), ([3, 3], 3, ["QTEST_KEY_A", "QTEST_KEY_B"]), ([1], 1, ["QTEST_KEY_A"])])
def test_resume_with_next_key_rotates_on_exit_3(tmp_path: Path, codes: list[int], expected: int, keys_used: list[str]):
    pkg = tmp_path / "work" / "quorum_reasoning"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "run.py").write_text(FAKE_PACKAGE_RUN)
    env_file = tmp_path / ".env"
    env_file.write_text(f"QTEST_KEY_A={VALUE_A}\nQTEST_KEY_B={VALUE_B}\n")
    records = tmp_path / "records.jsonl"
    (tmp_path / "scenario.json").write_text(json.dumps({"records": str(records), "codes": codes, "env_file": str(env_file),
                                                        "values": {VALUE_A: "QTEST_KEY_A", VALUE_B: "QTEST_KEY_B"}}))
    log = tmp_path / "run.log"
    env = {k: v for k, v in os.environ.items() if not k.startswith("QTEST_")}
    env["FAKE_SCENARIO"] = str(tmp_path / "scenario.json")
    proc = subprocess.run([_git_bash(), str(SCRIPTS / "resume_with_next_key.sh"), "--topic", "climate-policy", "--date", DATE,
                           "--attempt", "2", "--out", str(tmp_path / "store"), "--log", str(log), "--keys", "QTEST_KEY_A,QTEST_KEY_B",
                           "--env-file", str(env_file), "--python", sys.executable, "--workdir", str(tmp_path / "work"), "--", "--quiet"],
                          env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == expected, proc.stdout + proc.stderr
    rows = [json.loads(line) for line in records.read_text().splitlines()]
    assert [r["key"] for r in rows] == keys_used
    assert ["--resume" in r["argv"] for r in rows] == [False, True][: len(rows)]
    assert all("--quiet" in r["argv"] and "--attempt" in r["argv"] for r in rows)
    assert all(r["blank_ok"] for r in rows)
    text = log.read_text(encoding="utf-8") + proc.stdout + proc.stderr
    assert VALUE_A not in text and VALUE_B not in text and "MODEL_API_KEY=[redacted]" in text
    assert f"live exit={codes[0]} (QTEST_KEY_A)" in text
