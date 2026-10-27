"""scripts/run_editions.py --route meterless (2026-10-26, Yelysei's D1): the Meterless Nightshift route for the canonical
editions of 27 October, its child environment, the token check and the Meterless stop rule.

Fully offline, on the world of tests/test_run_editions.py: a fake run.py (below) writes journal rows and output lines
the way run.py does; no model, no Zetaris, no control plane is reached. Every test keeps QUORUM_DRY_RUN=1 exported
and the model credentials blank or fake, so a real run.py reached by mistake refuses (exit 2) instead of spending."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

import test_run_editions as base  # the shared world (Env), the runner module and the fake dry check

re_mod = base.re_mod
DATE = base.DATE
TOKEN = "QT.EST-meterless-token-for-tests-only"  # a dot keeps scripts/security-check.py from reading it as a real token
NVIDIA_FILE_KEY = "QT.EST-nvidia-file-key-for-tests-only"

FAKE_METERLESS_RUN = r'''
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
n = sum(1 for p in rec_dir.glob("*.json") if json.loads(p.read_text())["topic"] == topic)
steps = sc["mlive"].get(topic, [{}])
step = steps[min(n, len(steps) - 1)]
# what run.py does first: llm._env() loads the repo .env with load_dotenv(override=False)
for line in Path(sc["env_file"]).read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        if k not in os.environ:
            os.environ[k] = v
names = ("MODEL_BASE_URL", "MODEL_API_KEY", "QUORUM_MIN_INTERVAL_MS", "QUORUM_MIN_INTERVAL_MS_FACT_CHECKER",
         "QUORUM_MIN_INTERVAL_MS_REVIEWER", "MODEL_API_KEY_8", "MODEL_API_KEY_9", "QUORUM_HMEM", "QUORUM_HMEM_DIR", "METERLESS_HOME")
rec = {"topic": topic, "argv": args, "resume": "--resume" in args, "start": time.time(),
       "env": {k: os.environ.get(k) for k in names}, "token_seen": os.environ.get("METERLESS_TOKEN") == sc.get("token")}
tmp = rec_dir / f"{time.time_ns()}-{os.getpid()}.tmp"
tmp.write_text(json.dumps(rec))
os.replace(tmp, rec_dir / f"{time.time_ns()}-{os.getpid()}.json")
if step.get("guard", True) and os.environ.get("MODEL_BASE_URL") == "":
    print("meterless: hmemKnowledge read back false (prior-answer injection off on this daemon)", file=sys.stderr, flush=True)
if step.get("echo_token"):
    print("child sees " + os.environ.get("METERLESS_TOKEN", ""), flush=True)
cp = out / "_checkpoints" / f"{rid}.sqlite"
cp.parent.mkdir(parents=True, exist_ok=True)
c = sqlite3.connect(cp)
c.execute("CREATE TABLE IF NOT EXISTS checkpoints (thread_id TEXT)")
c.execute("INSERT INTO checkpoints VALUES (?)", (rid,))
c.commit()
c.close()
ok = {"task": "stance", "lane": "default", "route": "nvidia/nemotron-3.5-lightning-30b-a3b", "served": "m", "http_status": 200,
      "receipt_hmem_injected": 0, "receipt_id": "rcpt-private", "request_key": "k" * 64}
journal = out / "_journal" / f"{rid}.jsonl"
journal.parent.mkdir(parents=True, exist_ok=True)
for row in [dict(ok)] * step.get("ok_rows", 2) + step.get("rows", []):
    with journal.open("a") as fh:
        fh.write(json.dumps({**ok, **row, "payload": {"text": "private page text"}}) + "\n")
    time.sleep(step.get("row_gap", 0))
for line in step.get("lines", []):
    print(line, flush=True)
time.sleep(step.get("sleep", 0))
if step.get("crash"):
    raise RuntimeError("boom in the fake run")
if step.get("publish", step.get("exit", 0) == 0):
    d = out / topic / date
    d.mkdir(parents=True, exist_ok=True)
    v = 1 + max([int(p.stem[1:]) for p in d.glob("v*.json") if p.stem[1:].isdigit()] or [0])
    snap = {"run_id": rid, "topic_id": topic, "edition_date": date, "status": step.get("status", "ok"), "version": v}
    (d / f"v{v}.json").write_text(json.dumps(snap))
    (d / "latest.json").write_text(json.dumps(snap))
    # run.py's summary line after store.publish, from the whole journal: on --resume llm.load_journal restores every
    # row, error rows included, into llm.calls, and flagged_calls_note names the flags
    rows = [json.loads(x) for x in journal.read_text().splitlines() if x.strip()]
    flags = ((sum(1 for r in rows if r.get("route_substituted")), "lane substituted"),
             (sum(1 for r in rows if r.get("lane_unverified")), "lane unverified"),
             (sum(1 for r in rows if r.get("hmem_rejected")), "rejected for injected memories"),
             (sum(1 for r in rows if r.get("cache_refused")), "refused as cache replays"))
    served = {}
    for r in rows:
        served[r.get("served")] = served.get(r.get("served"), 0) + 1
    print(f"model calls: {len(rows)} ({sum(1 for r in rows if r.get('error'))} failed"
          + "".join(f", {n} {label}" for n, label in flags if n) + "); answered by: "
          + ", ".join(f"{m} x{n}" for m, n in served.items()), flush=True)
for line in step.get("after", []):  # run.py prints its summary after store.publish
    print(line, flush=True)
sys.exit(step.get("exit", 0))
'''


class MWorld:
    """The shared world with a Meterless token in its .env (never exported), the NVIDIA route's values there too, and
    the fake run above."""

    def __init__(self, env: "base.Env", monkeypatch: pytest.MonkeyPatch, token: str | None = TOKEN, extra_env: str = ""):
        self.w = env
        for name in ("METERLESS_TOKEN", "METERLESS_RUNTIME_TOKEN", "METERLESS_BASE_URL"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv("MODEL_API_KEY", raising=False)  # the .env's NVIDIA key below is what a child would load
        lines = [f"MODEL_API_KEY={NVIDIA_FILE_KEY}", "QUORUM_MIN_INTERVAL_MS=6000", "QUORUM_MIN_INTERVAL_MS_FACT_CHECKER=10000"]
        if token:
            lines.append(f"METERLESS_TOKEN={token}")
        env.env_file.write_text(env.env_file.read_text() + "\n".join(lines) + "\n" + extra_env)
        self.fake = env.tmp / "fake_meterless_run.py"
        self.fake.write_text(FAKE_METERLESS_RUN)

    def scenario(self, mlive: dict, **extra) -> None:
        self.w.scenario({}, mlive=mlive, token=TOKEN, **extra)

    def run(self, topics: str, *more: str, live: bool = True, route: str | None = "meterless", keys: str | None = None) -> int:
        argv = self.w.argv(topics, *more, keys=keys, live=live)
        if route:
            argv += ["--route", route]
        return self.w.main(argv, live_cmd=[sys.executable, "-I", "-S", str(self.fake)])

    def logs(self) -> str:
        return "".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(self.w.logs.glob("*.log")))


@pytest.fixture
def mw(world: "base.Env", monkeypatch: pytest.MonkeyPatch) -> MWorld:
    return MWorld(world, monkeypatch)


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> "base.Env":
    return base.Env(tmp_path, monkeypatch)


# ---------------------------------------------------------------------------------------------------------------------
# the route, the child environment, the record


def test_meterless_children_get_the_blank_nvidia_pair_and_no_pacing(mw: MWorld):
    mw.scenario({"t1": [{"echo_token": True}], "t2": [{}]})
    assert mw.run("t1,t2") == 0
    runs = mw.w.runs()
    assert [r["topic"] for r in runs] == ["t1", "t2"]
    for r in runs:
        # set by the runner before the child loaded .env, so the .env's NVIDIA values and lane pauses did not win
        assert r["env"]["MODEL_BASE_URL"] == "" and r["env"]["MODEL_API_KEY"] == "", r["env"]
        assert r["env"]["QUORUM_MIN_INTERVAL_MS"] == "0", r["env"]
        assert r["env"]["QUORUM_MIN_INTERVAL_MS_FACT_CHECKER"] == "" and r["env"]["QUORUM_MIN_INTERVAL_MS_REVIEWER"] == ""
        assert r["env"]["MODEL_API_KEY_8"] == "" and r["env"]["MODEL_API_KEY_9"] == ""  # no NVIDIA key at all
        assert r["token_seen"] and "--resume" not in r["argv"]
    for topic in ("t1", "t2"):
        doc = mw.w.public_of(topic)  # exactly the eight fields, a known state, the hash
        assert doc["state"] == "published" and doc["reason"] is None
        rec = mw.w.status_of(topic)
        assert rec["route"] == "meterless" and [r["route"] for r in rec["runs"]] == ["meterless"]
    summary = mw.w.summary()
    assert summary["route"] == "meterless" and summary["stop_rule"] is True and summary["halted_by"] is None
    assert [(k["name"], k["cap_fast"], k["cap_ultra"]) for k in summary["keys"]] == [(re_mod.ROUTE, re_mod.UNCAPPED, re_mod.UNCAPPED)]
    logs = mw.logs()
    assert f"=== run 1 of {DATE}-t1-1 on {re_mod.ROUTE} " in logs and "; route meterless; Meterless stop rule on ===" in logs
    assert TOKEN not in logs and NVIDIA_FILE_KEY not in logs and "child sees [redacted]" in logs
    for p in mw.w.status.rglob("*.json"):
        text = p.read_text(encoding="utf-8")
        assert TOKEN not in text and NVIDIA_FILE_KEY not in text


def test_meterless_plan_paces_nothing_and_is_uncapped_unless_caps_are_given(mw: MWorld, capsys: pytest.CaptureFixture[str]):
    mw.scenario({}, dry={"t1": {"fast": 900, "ultra": 0}, "t2": {"fast": 900, "ultra": 0}})
    assert mw.run("t1,t2", live=False) == 0  # 1440 + 1440 estimated fast-lane calls: both fit, one after the other
    out = capsys.readouterr().out
    assert "route meterless (the Meterless stop rule on)" in out and f"{re_mod.ROUTE} uncapped" in out
    assert "this route paces nothing" in out and "min of pacing" not in out
    assert [mw.w.status_of(t)["plan_outcome"] for t in ("t1", "t2")] == ["published", "published"]
    assert mw.run("t1,t2", "--max-calls-per-key", "1000", live=False) == 3  # given caps apply as on the NVIDIA route
    assert mw.w.status_of("t2")["plan_outcome"] == "waiting_for_key"
    assert not mw.w.runs() and not list(mw.w.status.glob("t*/*.json"))  # a plan starts no run and writes no status file


def test_the_default_route_is_nvidia_and_unchanged(mw: MWorld):
    # a row with an HTTP 429 and lane_unverified would stop a Meterless run; on the default route it is published
    mw.scenario({"t1": [{"rows": [{"http_status": 429, "error": "RateLimitError: x"}, {"lane_unverified": True}]}]})
    assert mw.run("t1", route=None, keys="QTEST_KEY_A") == 0
    run, = mw.w.runs()
    assert run["env"]["MODEL_BASE_URL"] == "https://integrate.api.nvidia.com/v1" and run["env"]["QUORUM_MIN_INTERVAL_MS"] == "6000"
    rec = mw.w.status_of("t1")
    assert rec["state"] == "published" and rec["route"] == "nvidia"
    summary = mw.w.summary()
    assert summary["route"] == "nvidia" and summary["stop_rule"] is False
    assert [(k["cap_fast"], k["cap_ultra"]) for k in summary["keys"]] == [(650, 250)]
    assert "Meterless stop rule" not in mw.logs()


# ---------------------------------------------------------------------------------------------------------------------
# preflight: the token, --keys, the base URL


def test_a_missing_meterless_token_fails_every_topic_and_starts_nothing(world: "base.Env", monkeypatch: pytest.MonkeyPatch):
    mw = MWorld(world, monkeypatch, token=None)
    mw.scenario({}, db_error=True)  # a topics listing would fail the invocation with exit 2: none may be made
    assert mw.run("t1,t2") == 1
    for topic in ("t1", "t2"):
        doc = world.public_of(topic)
        assert (doc["state"], doc["reason"], doc["attempts"]) == ("failed", "meterless token missing", 0)
    assert not world.runs() and not world.dry_runs()
    assert world.summary()["route"] == "meterless"
    # a plan run says the same in its records, and writes no status file of its own
    assert mw.run("t3", live=False) == 1
    assert world.status_of("t3")["reason"] == "meterless token missing" and not (world.status / "t3").exists()
    assert mw.run("all") == 2 and not world.runs()  # the topics are known only from the listing: refused


def test_an_exported_empty_token_counts_as_missing(world: "base.Env", monkeypatch: pytest.MonkeyPatch):
    mw = MWorld(world, monkeypatch)
    monkeypatch.setenv("METERLESS_TOKEN", "")  # the child keeps an exported empty value over the .env's (override=False)
    mw.scenario({})
    assert mw.run("t1") == 1 and world.public_of("t1")["reason"] == "meterless token missing" and not world.runs()


def test_the_runtime_token_alias_is_enough(world: "base.Env", monkeypatch: pytest.MonkeyPatch):
    mw = MWorld(world, monkeypatch, token=None, extra_env=f"METERLESS_RUNTIME_TOKEN={TOKEN}\n")
    mw.scenario({})
    assert mw.run("t1") == 0 and world.public_of("t1")["state"] == "published"


@pytest.mark.parametrize("case", ["keys", "nvidia_base"])
def test_meterless_refusals_start_nothing(world: "base.Env", monkeypatch: pytest.MonkeyPatch, case: str):
    extra = "METERLESS_BASE_URL=https://integrate.api.nvidia.com/v1\n" if case == "nvidia_base" else ""
    mw = MWorld(world, monkeypatch, extra_env=extra)
    mw.scenario({})
    assert mw.run("t1", keys="QTEST_KEY_A" if case == "keys" else None) == 2
    assert not world.runs() and not world.dry_runs() and not world.status.exists()


# ---------------------------------------------------------------------------------------------------------------------
# the stop rule


ROW_CASES = {
    "http_429": ({"http_status": 429, "error": "RateLimitError: Error code: 429", "served": "error"}, "HTTP 429 on a model call"),
    "http_500": ({"http_status": 500, "error": "InternalServerError", "served": "error"}, "HTTP 500 on a model call"),
    "retried_503": ({"retried_after": "InternalServerError: HTTP 503, waited 5 s", "attempts": 2}, "HTTP 503 on a model call (answered on its retry)"),
    "substituted": ({"route_substituted": True, "served": "error", "error": "route substituted"}, "route substituted"),
    "unverified": ({"lane_unverified": True}, "lane unverified"),
    "hmem_count": ({"receipt_hmem_injected": 2}, "injected H-MEM memories"),
    "hmem_rejected": ({"hmem_rejected": True, "served": "error", "error": "runtime injected"}, "injected H-MEM memories"),
    "cache": ({"cache_refused": True, "served": "error", "error": "cache"}, "cache replay was refused"),
    "no_json": ({"error": "reply carried no JSON object", "served": "error"}, "a model call failed"),
}


@pytest.mark.parametrize("case", sorted(ROW_CASES))
def test_a_journal_row_stops_the_run_at_once_and_nothing_starts_after_it(mw: MWorld, capsys: pytest.CaptureFixture[str], case: str):
    row, expected = ROW_CASES[case]
    mw.scenario({"t1": [{"rows": [row], "sleep": 60}], "t2": [{}], "t3": [{}]})
    started = time.monotonic()
    assert mw.run("t1,t2,t3") == 1
    assert time.monotonic() - started < 45  # killed at the first error, not after the child's 60 s
    assert [r["topic"] for r in mw.w.runs()] == ["t1"]  # t2 and t3 never started, nor the fallback
    t1 = mw.w.public_of("t1")
    assert t1["state"] == "failed" and t1["reason"].startswith("stopped at the first error on the Meterless route: ")
    assert expected in t1["reason"] and "private" not in t1["reason"] and "rcpt" not in t1["reason"]
    for topic in ("t2", "t3"):
        doc = mw.w.public_of(topic)
        assert (doc["state"], doc["attempts"]) == ("queued", 0)
        assert doc["reason"] == "not started: t1 stopped at the first error on the Meterless route"
    out = capsys.readouterr().out
    fallback = next(line for line in out.splitlines() if "manual fallback for t1" in line)
    assert "only by Yelysei's word" in fallback and "the runner never starts it" in fallback
    assert (f"scripts/run_editions.py --date {DATE} --topics t1 --route nvidia --keys MODEL_API_KEY,MODEL_API_KEY_8,MODEL_API_KEY_9 "
            "--attempt 2 --out ") in fallback and fallback.rstrip().endswith("--live")
    assert NVIDIA_FILE_KEY not in out and TOKEN not in out
    assert mw.w.summary()["halted_by"] == "t1"
    assert "--- Meterless stop rule: " in mw.logs()


LINE_CASES = {
    "traceback": ({"crash": True}, "a Traceback in the run's output"),
    "refusal": ({"lines": ["refusing to run: cannot turn H-MEM injection off: the control plane is unreachable"], "exit": 2,
                 "publish": False}, "run.py refused to run or to continue"),
    "failed_call": ({"lines": ["  · stance          default       m                                    FAILED   1200 ms  APITimeoutError"]},
                    "a model call failed"),
    "retry_note": ({"lines": ["  · stance          fact_checker  m                                    RateLimitError; 429; retry in 15 s"]},
                   "RateLimitError on a model call"),
    "rejected": ({"lines": ["  · stance          default       m                                    REJECTED: 2 injected memories"]},
                 "injected H-MEM memories"),
    "summary_flags": ({"lines": ["model calls: 12 (0 failed, 1 lane unverified); answered by: m ×12"]}, "lane unverified"),
    "summary_failed": ({"lines": ["model calls: 12 (1 failed); answered by: m ×11, error ×1"]}, "a model call failed"),
}


@pytest.mark.parametrize("case", sorted(LINE_CASES))
def test_an_output_line_stops_the_run(mw: MWorld, case: str):
    step, expected = LINE_CASES[case]
    mw.scenario({"t1": [{**step, "sleep": step.get("sleep", 0)}], "t2": [{}]})
    assert mw.run("t1,t2") == 1
    t1 = mw.w.public_of("t1")
    assert t1["state"] == "failed" and expected in t1["reason"], t1
    assert mw.w.public_of("t2")["state"] == "queued" and [r["topic"] for r in mw.w.runs()] == ["t1"]


@pytest.mark.parametrize("code", [2, 3, 7])
def test_a_non_zero_exit_fails_the_topic_even_with_a_published_partial(mw: MWorld, code: int):
    mw.scenario({"t1": [{"exit": code, "publish": code == 2, "status": "partial"}], "t2": [{}]})
    assert mw.run("t1,t2") == 1
    rec = mw.w.status_of("t1")
    assert rec["state"] == "failed" and (f"run.py exited {code}" in rec["reason"] or f"exit {code}" in rec["reason"]), rec
    assert [r["outcome"] for r in rec["runs"]] == ["failed"]  # exit 3 is no drain to rotate on: there is no key rotation
    if code == 2:
        assert "version 1, is not for hand-over" in rec["reason"]
    assert mw.w.public_of("t2")["state"] == "queued"


def test_a_rerun_keeps_a_published_partial_failed_and_runs_the_next_topic(mw: MWorld):
    mw.scenario({"t1": [{"exit": 2, "publish": True, "status": "partial"}, {}], "t2": [{}]})
    assert mw.run("t1,t2") == 1
    assert mw.run("t1,t2") == 1  # the same command again
    t1 = mw.w.public_of("t1")
    assert t1["state"] == "failed" and "published a partial snapshot (version 1)" in t1["reason"]
    assert [r["topic"] for r in mw.w.runs()] == ["t1", "t2"]  # t1 is not run again; t2 now runs
    assert mw.w.public_of("t2")["state"] == "published"


def test_a_run_that_made_calls_without_the_guard_line_fails(mw: MWorld):
    mw.scenario({"t1": [{"guard": False}]})
    assert mw.run("t1") == 1
    assert "without confirming the H-MEM guard" in mw.w.public_of("t1")["reason"]


STOP_ROWS = {  # rows a stopped run leaves in its journal; llm.load_journal restores each into a resumed run's ledger
    "http_429": {"http_status": 429, "error": "RateLimitError: Error code: 429", "served": "error"},
    "http_401": {"http_status": 401, "error": "AuthenticationError: Error code: 401", "served": "error"},
    "refused": {"http_status": None, "error": "APIConnectionError: Connection error.", "served": "error"},
    "substituted": {"route_substituted": True, "served": "error", "error": "route substituted"},
    "unverified": {"lane_unverified": True},
    "hmem": {"hmem_rejected": True, "receipt_hmem_injected": 2, "served": "error", "error": "runtime injected"},
    "retried_503": {"retried_after": "InternalServerError: HTTP 503, waited 5 s", "attempts": 2},
}


@pytest.mark.parametrize("case", sorted(STOP_ROWS))
def test_a_stopped_topic_whose_journal_keeps_a_call_the_rule_fails_is_not_resumed(mw: MWorld, capsys: pytest.CaptureFixture[str],
                                                                                  case: str):
    # a resume would restore that row, and its own summary line ("model calls: N (1 failed ...)") would trip the rule
    # again at its end, after re-running the rest of the topic and publishing a version that cannot be handed over
    mw.scenario({"t1": [{"rows": [STOP_ROWS[case]], "sleep": 30}, {}], "t2": [{}]})
    assert mw.run("t1,t2") == 1
    halt = next(line for line in capsys.readouterr().out.splitlines() if "once the cause is fixed" in line)
    assert "t1 stays failed (its journal keeps a call the rule fails" in halt and "a fresh --attempt 2" in halt
    assert mw.run("t1,t2") == 1  # the same command again: t1 is failed at once, t2 runs
    t1 = mw.w.public_of("t1")
    assert t1["state"] == "failed" and "keeps a call the Meterless stop rule fails in its journal" in t1["reason"], t1
    assert t1["reason"].endswith("a fresh --attempt 2 runs the topic again") and "rcpt" not in t1["reason"]
    assert [r["topic"] for r in mw.w.runs()] == ["t1", "t2"] and mw.w.public_of("t2")["state"] == "published"
    assert mw.run("t1", "--attempt", "2") == 0  # the fresh attempt: its own journal, clean
    doc = mw.w.public_of("t1")
    assert (doc["state"], doc["run_id"]) == ("published", f"{DATE}-t1-2")


def test_a_stopped_topic_whose_journal_is_clean_resumes_and_ends_clean(mw: MWorld, capsys: pytest.CaptureFixture[str]):
    mw.scenario({"t1": [{"crash": True}, {}], "t2": [{}]})  # a Traceback outside any model call: 2 clean rows stay
    assert mw.run("t1,t2") == 1
    halt = next(line for line in capsys.readouterr().out.splitlines() if "once the cause is fixed" in line)
    assert "t1 resumes from its checkpoint" in halt
    assert mw.run("t1,t2") == 0  # same route: the stopped run id resumes, its summary line is clean, then t2 runs
    first, second, third = mw.w.runs()
    assert (first["topic"], second["topic"], third["topic"]) == ("t1", "t1", "t2")
    assert second["resume"] and not first["resume"]
    assert mw.w.public_of("t1")["state"] == "published" and "model calls: 4 (0 failed)" in mw.logs()


@pytest.mark.parametrize("second", ["meterless", "nvidia"])
def test_a_version_the_rule_rejected_is_never_shown_as_published(mw: MWorld, second: str):
    # run 1 publishes v1, then its summary line trips the rule: v1 is the store's latest.json but not for hand-over
    mw.scenario({"t1": [{"after": ["model calls: 3 (0 failed, 1 lane unverified); answered by: m x3"]},
                        {"rows": [{"lane_unverified": True}], "sleep": 30}]})
    assert mw.run("t1") == 1 and mw.w.public_of("t1")["state"] == "failed"
    if second == "meterless":  # the fresh attempt the runbook gives, stopped before it publishes
        assert mw.run("t1", "--attempt", "2") == 1
        state = "failed"
    else:  # the printed NVIDIA fallback, whose key drains
        mw.w.scenario({"t1": [{"exit": 3, "fast": 50}]})
        assert mw.w.main(mw.w.argv("t1", "--attempt", "2", keys="QTEST_KEY_A")) == 3
        state = "waiting_for_key"
    doc = mw.w.public_of("t1")  # attempt 2's own state, the same as its record
    assert (doc["state"], doc["run_id"]) == (state, f"{DATE}-t1-2"), doc
    assert f"the store's newest version is run {DATE}-t1-1's, which the Meterless stop rule failed" in mw.logs()
    assert "keeps the published version" not in mw.logs()


def test_a_run_stopped_after_it_published_stays_failed_on_either_route(mw: MWorld):
    # the error shows only in run.py's summary, printed after it published (or a kill that lands after the publish)
    mw.scenario({"t1": [{"after": ["model calls: 3 (0 failed, 1 lane unverified); answered by: m ×3"]}, {}], "t2": [{}]})
    assert mw.run("t1,t2") == 1
    rec = mw.w.status_of("t1")
    assert rec["stopped_by_rule"] is True and rec["version"] == 1 and "is not for hand-over" in rec["reason"]
    for again in (lambda: mw.run("t1,t2"), lambda: mw.w.main(mw.w.argv("t1", keys="QTEST_KEY_A"))):
        assert again() == 1
        doc = mw.w.public_of("t1")
        assert doc["state"] == "failed" and "was stopped by the Meterless stop rule, and its version 1 is not for hand-over" in doc["reason"]
    assert [r["topic"] for r in mw.w.runs()] == ["t1", "t2"]  # t1 never ran again; the rerun ran t2


# ---------------------------------------------------------------------------------------------------------------------
# one edition never mixes routes


def test_a_run_id_started_on_nvidia_does_not_continue_on_meterless(mw: MWorld):
    mw.w.scenario({"t1": [{"exit": 3, "fast": 50}]})  # the shared fake: the key drains, a checkpoint and journal stay
    assert mw.w.main(mw.w.argv("t1", keys="QTEST_KEY_A")) == 3
    assert mw.w.status_of("t1")["route"] == "nvidia"
    mw.scenario({"t1": [{}]})
    assert mw.run("t1") == 1
    doc = mw.w.public_of("t1")
    assert doc["state"] == "failed" and "already has live calls on the nvidia route" in doc["reason"]
    assert "a fresh --attempt 2" in doc["reason"]
    assert len(mw.w.runs()) == 1  # the NVIDIA run only: nothing was started on the Meterless route
    assert mw.run("t1", "--attempt", "2") == 0  # the fresh attempt runs on the Meterless route
    assert mw.w.status_of("t1", 2)["route"] == "meterless"


def test_a_run_id_started_on_meterless_does_not_continue_on_nvidia(mw: MWorld):
    mw.scenario({"t1": [{"rows": [{"lane_unverified": True}], "sleep": 30}]})  # killed before it could publish
    assert mw.run("t1") == 1
    assert mw.w.main(mw.w.argv("t1", keys="QTEST_KEY_A")) == 1
    assert "already has live calls on the meterless route" in mw.w.public_of("t1")["reason"]
    assert len(mw.w.runs()) == 1


def test_a_meterless_run_id_without_a_recorded_route_does_not_continue(mw: MWorld):
    mw.scenario({"t1": [{"rows": [{"lane_unverified": True}], "sleep": 30}, {}]})
    assert mw.run("t1") == 1
    mw.w.record_path("t1").unlink()  # a lost record: the run id's history no longer says which route it is on
    assert mw.run("t1") == 1
    assert "a route this runner did not record" in mw.w.public_of("t1", record=False)["reason"]
    assert len(mw.w.runs()) == 1


# ---------------------------------------------------------------------------------------------------------------------
# the rule's readers


def test_row_and_line_readers_trip_only_on_errors():
    ok = {"http_status": 200, "receipt_hmem_injected": 0, "receipt_from_cache": False, "served": "m"}
    assert re_mod.row_stop_reason(ok) is None and re_mod.row_stop_reason("not a row") is None
    assert re_mod.row_stop_reason({**ok, "receipt_hmem_injected": True}) is not None  # not an integer count: refused
    assert re_mod.row_stop_reason({**ok, "receipt_hmem_injected": "2"}) is not None
    assert re_mod.row_stop_reason({**ok, "rate_headers": [{"retry-after": "5"}]}) == "HTTP 429 on a model call"
    assert re_mod.row_stop_reason({**ok, "receipt_from_cache": True}) is not None
    for line in ("plan                1  -              12  12 documents, 3 official", "frame               1  e1           40  failed; coverage counts only",
                 "fetch failed https://example.org/home/a: HTTPError", "model calls: 12 (0 failed); answered by: m ×12",
                 "summary (model): Officials FAILED to agree; HTTP 404 was not the cause", "corpus: zetaris; model: m; fact-checker: u",
                 "meterless: hmemKnowledge read back false (prior-answer injection off on this daemon)",
                 "  · stance          default       m                                    APITimeoutError; one retry in 5 s"):
        assert re_mod.line_stop_reason(line) is None, line
    assert re_mod.line_stop_reason("Traceback (most recent call last):") is not None
    assert re_mod.line_stop_reason("openai.NotFoundError: Error code: 404") == "HTTP 404 on a model call"


def test_the_guard_line_is_what_run_live_guard_prints(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    from quorum_reasoning import llm, run

    monkeypatch.setattr(llm, "on_meterless", lambda: True)
    monkeypatch.setattr(llm, "disable_hmem_injection", lambda: None)  # the setter confirmed (no control plane reached)
    assert run.live_guard() is None
    assert re_mod.HMEM_OFF_LINE in capsys.readouterr().err


def test_the_watch_reads_only_rows_added_after_it_started(tmp_path: Path):
    journal = tmp_path / "j.jsonl"
    journal.write_text(json.dumps({"http_status": 429, "error": "x"}) + "\n" + '{"cut short')  # an earlier run's rows
    watch = re_mod.MeterlessWatch(journal)
    with journal.open("a") as fh:
        fh.write("\n" + json.dumps({"http_status": 200}) + "\n")
    assert not watch.poll() and watch.reason is None
    with journal.open("a") as fh:
        fh.write(json.dumps({"lane_unverified": True}))  # no newline yet: not a complete row
    assert not watch.poll()
    with journal.open("a") as fh:
        fh.write("\n")
    assert watch.poll() and "lane unverified" in watch.reason
    assert not watch.trip("later reason") and "lane unverified" in watch.reason  # the first reason stays


# --hmem on: the source memory for the live children (D3)


def test_hmem_on_gives_live_children_the_switch_and_the_store(mw: MWorld, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    store = tmp_path / "hmem-store"
    monkeypatch.setenv("METERLESS_HOME", str(tmp_path / "meterless"))
    monkeypatch.setenv("QUORUM_HMEM_DIR", str(store))
    mw.scenario({"t1": [{}], "t2": [{}]})
    assert mw.run("t1,t2", "--hmem", "on") == 0
    assert store.is_dir() and (store.stat().st_mode & 0o777) == 0o700
    runs = mw.w.runs()
    assert [r["topic"] for r in runs] == ["t1", "t2"]
    for r in runs:
        assert r["env"]["QUORUM_HMEM"] == "on" and r["env"]["QUORUM_HMEM_DIR"] == str(store), r["env"]
        assert r["env"]["METERLESS_HOME"] == str(tmp_path / "meterless")


def test_hmem_off_by_default_and_on_needs_its_environment(mw: MWorld, monkeypatch: pytest.MonkeyPatch):
    mw.scenario({"t1": [{}]})
    assert mw.run("t1") == 0
    assert all(r["env"]["QUORUM_HMEM"] is None for r in mw.w.runs())
    monkeypatch.delenv("METERLESS_HOME", raising=False)
    monkeypatch.delenv("QUORUM_HMEM_DIR", raising=False)
    with pytest.raises(SystemExit):
        mw.run("t1", "--hmem", "on")
