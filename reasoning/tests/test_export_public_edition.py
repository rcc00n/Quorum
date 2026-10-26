"""scripts/export_public_edition.py: an installed edition's snapshot copied into docs/examples/editions with a public run
summary of counts (2026-10-26, Yelysei's D2).

Synthetic snapshots and ledgers only, in pytest's temporary directory; a throw-away git repository (isolated from the
user's git configuration) holds the producer commit; the sidecar and hash files are written by edition_sidecar.make
as for a real hand-over. One ledger holds fake secret-looking fields (receipt ids, request keys, reply hashes, a
payload, a prompt, a reply, a bearer header, a token, rate headers) to prove none of them reaches the summary.
Nothing reaches the network, Zetaris or a model route."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_public_edition.py"


def _load():
    spec = importlib.util.spec_from_file_location("export_public_edition_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ex = _load()
es = ex.es

TOPIC, DATE = "test-topic", "2026-10-26"
RUN_ID = f"{DATE}-{TOPIC}-1"
LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"
ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"
FAKE_ENV_SECRET = "fake-env-secret-value-SSSS-0003"
# key-shaped fakes are built at run time, so no key-shaped literal sits in the repository
FAKE_BEARER = "Bearer " + "abcdefghij" * 3
FAKE_NVAPI = "nvapi-" + "A" * 28
# every value a public file must never hold (the ledger's private fields below)
PRIVATE = ("rcpt-SECRET-RECEIPT-0001", "rcpt-SECRET-RECEIPT-0002", "rcpt-SECRET-RECEIPT-0003", "rcpt-SECRET-RECEIPT-0004",
           "rcpt-SECRET-RECEIPT-0005", "f00d" * 16, "cafe" * 16, "be" * 32, FAKE_BEARER,
           FAKE_NVAPI, "SECRET-RETRY-HEADER-VALUE", "PRIVATE PAGE TEXT", "PRIVATE REPLY TEXT",
           "PRIVATE PROMPT TEXT", "fake-token-value-TTTT-0009", "Connection error", "runtime injected 2 prior answers")


def ledger_rows() -> list[dict]:
    ok = {"lane": "default", "route": LIGHTNING, "served": LIGHTNING, "http_status": 200, "receipt_hmem_injected": 0,
          "receipt_from_cache": False, "ms": 100, "attempts": 1, "run_id": RUN_ID, "tokens_in": 10, "tokens_out": 5}
    return [
        {**ok, "task": "event_key", "receipt_id": "rcpt-SECRET-RECEIPT-0001", "request_key": "f00d" * 16, "reply_sha256": "be" * 32},
        {**ok, "task": "rubric", "receipt_id": "rcpt-SECRET-RECEIPT-0002", "request_key": "cafe" * 16},
        {**ok, "task": "stance", "receipt_id": "rcpt-SECRET-RECEIPT-0003"},
        {**ok, "task": "stance_document", "lane": "fact_checker", "route": ULTRA, "served": ULTRA, "receipt_id": "rcpt-SECRET-RECEIPT-0004"},
        {**ok, "task": "review_disputed", "lane": "reviewer", "route": ULTRA, "served": ULTRA, "receipt_id": "rcpt-SECRET-RECEIPT-0005"},
        {**ok, "task": "write", "lane_unverified": True},
        {**ok, "task": "summary", "served": "error", "answered_model": LIGHTNING, "route_substituted": True,
         "error": f"route substituted {ULTRA} for {LIGHTNING}"},
        {**ok, "task": "frame", "served": "error", "http_status": 429,
         "error": f"RateLimitError: {FAKE_BEARER} {FAKE_NVAPI}",
         "rate_headers": [{"retry-after": "SECRET-RETRY-HEADER-VALUE"}]},
        {**ok, "task": "roundup_line", "served": "error", "receipt_hmem_injected": 2, "hmem_rejected": True,
         "error": "runtime injected 2 prior answers"},
        {**ok, "task": "merge_confirm", "served": "error", "cache_refused": True, "error": "Nightshift cache replay refused"},
        {"task": "extract_claims", "lane": "default", "route": LIGHTNING, "served": "error", "http_status": None, "run_id": RUN_ID,
         "error": "APIConnectionError: Connection error.", "payload": {"text": "PRIVATE PAGE TEXT of an article"},
         "reply": "PRIVATE REPLY TEXT", "prompt": "PRIVATE PROMPT TEXT", "token": "fake-token-value-TTTT-0009"},
    ]


def base_snapshot(rows: list[dict] | None = None) -> dict:
    rows = ledger_rows() if rows is None else rows
    served = Counter(r["served"] for r in rows)
    return {
        "schema_version": "1.0", "topic_id": TOPIC, "edition_date": DATE, "run_id": RUN_ID, "version": 1, "status": "ok",
        "summary": "Synthetic test edition.", "sources_missing": [], "stories": [],
        "roundup": {"empty_day": False, "count": 1, "groups": [{"name": "Test group", "items": [
            {"event_id": "ev-test-1", "line": "A synthetic roundup line.", "status": "unverified", "sources": []}]}]},
        "generated_at": "2026-10-26T11:02:13Z", "published_at": "2026-10-26T11:02:14Z", "expires_at": "2026-10-27T12:00:00Z",
        "edition_timezone": "America/New_York", "window": {"start": "2026-10-25T09:30:00Z", "end": "2026-10-26T09:30:00Z"},
        "provenance": {"corpus": "zetaris", "model": LIGHTNING, "fact_checker_model": ULTRA, "fictional": False,
                       "model_calls": len(rows), "answered_by": dict(served), "model_errors": sum(1 for r in rows if r.get("error"))},
        "trace": [
            {"node": "plan", "iteration": 1, "event_id": None, "decision": "test", "reason": "synthetic", "model": None, "duration_ms": 0},
            {"node": "memory", "iteration": 1, "event_id": None, "decision": "stored 3 source memories",
             "reason": "Reference H-MEM; candidate-only records; 3 ledger actions", "model": None, "duration_ms": 1},
            {"node": "memory", "iteration": 1, "event_id": None, "decision": "recalled 2 authorized source candidates",
             "reason": "Reference H-MEM; fresh verification required", "model": None, "duration_ms": 1},
            {"node": "memory", "iteration": 2, "event_id": None, "decision": "recalled 1 authorized source candidates",
             "reason": "Reference H-MEM; fresh verification required", "model": None, "duration_ms": 1},
            {"node": "memory", "iteration": 3, "event_id": None, "decision": "memory recall unavailable",
             "reason": "Ordinary research ranking retained", "model": None, "duration_ms": 1},
        ],
        "errors": [],
    }


@pytest.fixture(scope="module")
def producer(tmp_path_factory):
    """A temporary git repository with one commit holding reasoning/config/reasoning.toml."""
    root = tmp_path_factory.mktemp("producer")
    repo = root / "repo"
    repo.mkdir()
    empty = root / "empty.gitconfig"
    empty.write_bytes(b"")
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(empty),
           "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}

    def git(*args: str) -> str:
        done = subprocess.run(["git", "-c", "init.defaultBranch=main", "-c", "core.autocrlf=false", *args],
                              cwd=repo, env=env, capture_output=True, check=True)
        return done.stdout.decode("utf-8").strip()

    git("init", "-q")
    (repo / "reasoning" / "config").mkdir(parents=True)
    (repo / "reasoning" / "config" / "reasoning.toml").write_bytes(b"[research]\nstance_min_overlap = 0.15\n")
    git("add", "reasoning/config/reasoning.toml")
    git("commit", "-q", "-m", "config")
    return SimpleNamespace(repo=repo, commit=git("rev-parse", "HEAD"))


class Hand:
    """One edition as reasoning hands it over: snapshot, its .sha256, sidecar (+ .sha256) and the private ledger."""

    def __init__(self, tmp: Path, producer, snap: dict | None = None, rows: list[dict] | None = None):
        self.tmp = tmp
        self.producer = producer
        self.rows = ledger_rows() if rows is None else rows
        self.snap = snap or base_snapshot(self.rows)
        self.day = tmp / "store" / TOPIC / DATE
        self.day.mkdir(parents=True, exist_ok=True)
        self.snapshot = self.day / "v1.json"
        self.snapshot.write_bytes(json.dumps(self.snap, ensure_ascii=False, indent=2).encode("utf-8"))
        self.sha = self.day / "v1.json.sha256"
        self.sidecar = self.day / "v1.json.sidecar.json"
        self.ledger = self.day / "v1.ledger.json"
        self.write_ledger()
        self.out = tmp / "public" / "editions"

    def seal(self, corpus: str = "2026-10-26T10:30Z") -> "Hand":
        """edition_sidecar.make: the sidecar, its .sha256 and the snapshot's .sha256, as for the real hand-over."""
        es.make(self.snapshot, corpus, self.producer.commit, None, self.producer.repo)
        return self

    def write_ledger(self, **identity) -> None:
        doc = {"topic_id": TOPIC, "edition_date": DATE, "version": 1, "run_id": RUN_ID, "calls": self.rows}
        doc.update(identity)
        self.ledger.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    def argv(self, *more: str) -> list[str]:
        return [str(self.snapshot), "--sha256", str(self.sha), "--ledger", str(self.ledger), "--out", str(self.out),
                "--repo", str(self.producer.repo), *more]

    def run(self, capsys, *more: str) -> tuple[int, str]:
        code = ex.main(self.argv(*more))
        out, err = capsys.readouterr()
        return code, out + err

    @property
    def public(self) -> tuple[Path, Path]:
        return self.out / DATE / f"{TOPIC}.json", self.out / DATE / f"{TOPIC}.run-summary.json"


@pytest.fixture(autouse=True)
def fake_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The repo .env is never read by these tests: a fake one with one fake secret stands in."""
    env = tmp_path / "fake.env"
    env.write_text(f"QTEST_API_KEY={FAKE_ENV_SECRET}\nZETARIS_ORG_ID=not-a-secret-name\n", encoding="utf-8")
    monkeypatch.setattr(ex, "DEFAULT_ENV_FILE", env)
    return env


@pytest.fixture
def hand(tmp_path: Path, producer) -> Hand:
    return Hand(tmp_path, producer).seal()


# ---------------------------------------------------------------- the export


def test_the_snapshot_is_copied_byte_for_byte_and_the_summary_holds_counts_only(hand: Hand, capsys):
    code, out = hand.run(capsys)
    assert code == 0, out
    copy_path, summary_path = hand.public
    assert copy_path.read_bytes() == hand.snapshot.read_bytes()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    sidecar = json.loads(hand.sidecar.read_text(encoding="utf-8"))
    assert list(summary) == list(ex.RUN_SUMMARY_KEYS)
    assert summary == {
        "schema": "quorum.run-summary.v1", "topic_id": TOPIC, "edition_date": DATE, "version": 1, "run_id": RUN_ID, "status": "ok",
        "generated_at": "2026-10-26T11:02:13Z", "snapshot_sha256": hashlib.sha256(hand.snapshot.read_bytes()).hexdigest(),
        "producer_commit": hand.producer.commit, "corpus_as_of_utc": sidecar["corpus_as_of_utc"], "provider_route": "meterless",
        "calls": {"total": 11, "failed": 5,
                  "by_node": {"cluster": 2, "extract_claims": 1, "fact_check": 1, "frame": 1, "publish": 1, "research": 1,
                              "review_disputed": 1, "roundup": 1, "score_importance": 1, "write": 1},
                  "by_lane": {"default": 9, "fact_checker": 1, "reviewer": 1},
                  "by_model": {"error": 5, LIGHTNING: 4, ULTRA: 2},
                  "by_route": {LIGHTNING: 9, ULTRA: 2}},
        "route_substituted": 1, "lane_unverified": 1, "hmem_injected": 1, "cache_hits": 1, "meterless_receipts": 5,
        "memory_trace_rows": {"stored": 1, "recalled": 2, "write_unavailable": 0, "recall_unavailable": 1, "other": 0},
    }
    text = summary_path.read_text(encoding="utf-8")
    for value in PRIVATE:
        assert value not in text and value not in out, value
    assert summary_path.read_bytes().endswith(b"}\n") and b"\r\n" not in summary_path.read_bytes()


def test_a_second_export_needs_replace_and_writes_the_same_bytes(hand: Hand, capsys):
    assert hand.run(capsys)[0] == 0
    first = [p.read_bytes() for p in hand.public]
    code, out = hand.run(capsys)
    assert code == 2 and "destination_exists" in out and "--replace" in out
    assert hand.run(capsys, "--replace")[0] == 0
    assert [p.read_bytes() for p in hand.public] == first


def test_one_existing_destination_is_enough_to_refuse(hand: Hand, capsys):
    hand.public[1].parent.mkdir(parents=True)
    hand.public[1].write_text("{}", encoding="utf-8")
    assert hand.run(capsys)[0] == 2 and not hand.public[0].exists()


@pytest.mark.parametrize("case", ["other_hash", "other_name", "two_lines"])
def test_the_hand_over_hash_must_be_the_snapshots(hand: Hand, capsys, case: str):
    sha = hashlib.sha256(hand.snapshot.read_bytes()).hexdigest()
    text = {"other_hash": f"{'0' * 64}  v1.json\n", "other_name": f"{sha}  v2.json\n", "two_lines": f"{sha}  v1.json\n{sha}  v1.json\n"}[case]
    hand.sha.write_text(text, encoding="utf-8")
    code, out = hand.run(capsys)
    assert code == 2 and not hand.out.exists(), out


def test_a_bare_hash_file_is_accepted(hand: Hand, capsys):
    hand.sha.write_text(hashlib.sha256(hand.snapshot.read_bytes()).hexdigest() + "\n", encoding="utf-8")
    assert hand.run(capsys)[0] == 0


def test_a_snapshot_the_portal_check_rejects_is_refused(tmp_path: Path, producer, capsys):
    snap = base_snapshot()
    snap["roundup"]["count"] = 2  # differs from the one item: the portal's parse_reasoning rejects it
    hand = Hand(tmp_path, producer, snap=snap)
    raw = hand.snapshot.read_bytes()
    hand.sha.write_text(f"{hashlib.sha256(raw).hexdigest()}  v1.json\n", encoding="utf-8")
    code, out = hand.run(capsys)
    assert code == 2 and "invalid_roundup_count" in out and not hand.out.exists()


@pytest.mark.parametrize("change", [{"fictional": True}, {"model": "stand-ins"}])
def test_a_fixture_or_stand_in_snapshot_is_refused(tmp_path: Path, producer, capsys, change: dict):
    snap = base_snapshot()
    snap["provenance"].update(change)
    hand = Hand(tmp_path, producer, snap=snap)
    raw = hand.snapshot.read_bytes()
    hand.sha.write_text(f"{hashlib.sha256(raw).hexdigest()}  v1.json\n", encoding="utf-8")
    code, out = hand.run(capsys)
    assert code == 2 and "genuine_model_output_required" in out and not hand.out.exists()


def test_the_sidecar_must_be_this_snapshots(tmp_path: Path, producer, capsys):
    hand = Hand(tmp_path, producer).seal()
    other = Hand(tmp_path / "other", producer, snap={**base_snapshot(), "summary": "Another edition."}).seal()
    code, out = hand.run(capsys, "--sidecar", str(other.sidecar))
    assert code == 2 and "sidecar_snapshot_mismatch" in out and not hand.out.exists()


def test_a_sidecar_whose_hash_file_differs_is_refused(hand: Hand, capsys):
    (hand.day / "v1.json.sidecar.json.sha256").write_text(f"{'1' * 64}  v1.json.sidecar.json\n", encoding="utf-8")
    code, out = hand.run(capsys)
    assert code == 2 and "sidecar_hash_mismatch" in out


@pytest.mark.parametrize("case", ["run_id", "version", "count", "served", "errors"])
def test_another_runs_ledger_is_refused(hand: Hand, capsys, case: str):
    if case in ("run_id", "version"):
        hand.write_ledger(**{"run_id": f"{DATE}-{TOPIC}-2"} if case == "run_id" else {"version": 2})
    else:
        rows = ledger_rows()
        if case == "count":
            rows = rows[:-1]
        elif case == "served":
            rows[0]["served"] = ULTRA
        else:
            rows[0]["error"] = "reply carried no JSON object"
        hand.rows = rows
        hand.write_ledger()
    code, out = hand.run(capsys)
    assert code == 2 and "ledger_mismatch" in out and not hand.out.exists()


@pytest.mark.parametrize("text", [
    "C:\\Users\\someone\\Projects\\Quorum\\reasoning\\snapshots\\_private\\x.json",
    "failed reading D:/data/run.log",
    "see /home/someone/quorum/.env",
    "file:///C:/Users/someone/x",
    f"key {FAKE_ENV_SECRET} echoed",
    "receipt rcpt-SECRET-RECEIPT-0003",
])
def test_a_snapshot_holding_a_local_path_a_secret_or_a_ledger_id_is_refused(tmp_path: Path, producer, capsys, text: str):
    snap = base_snapshot()
    snap["trace"][0]["reason"] = text
    hand = Hand(tmp_path, producer, snap=snap).seal()
    code, out = hand.run(capsys)
    assert code == 2 and "unsafe_snapshot_content" in out and "snapshot.trace[0].reason" in out, out
    assert text not in out and not hand.out.exists()


@pytest.mark.parametrize("text", ["https://www.state.gov/home/remarks", "https://example.com/Users/guide",
                                  "Score: 5/10, at 09:30 on 10/26", "a profile:/x page"])
def test_public_urls_and_prose_are_no_local_paths(text: str):
    assert ex.unsafe_strings({"reason": text}, set()) == []


def test_out_inside_the_private_store_is_refused(hand: Hand, capsys):
    code = ex.main([*hand.argv()[:-4], "--out", str(hand.tmp / "store" / "_public"), "--repo", str(hand.producer.repo)])
    out = capsys.readouterr()
    assert code == 2 and "out_inside_private_store" in out.err


# ---------------------------------------------------------------- the summary's guards


def test_the_allowlist_refuses_any_other_field_or_shape(hand: Hand, capsys):
    assert hand.run(capsys)[0] == 0
    good = json.loads(hand.public[1].read_text(encoding="utf-8"))
    ex.check_allowlist(good, set(PRIVATE))  # passes as written
    bad_cases = []
    for mutate in (
        lambda s: s.update(receipt_ids=["rcpt-SECRET-RECEIPT-0001"]),
        lambda s: s["calls"].update(prompts=1),
        lambda s: s.update(hmem_injected="0"),
        lambda s: s.update(cache_hits=True),
        lambda s: s.update(meterless_receipts=-1),
        lambda s: s["calls"]["by_node"].update(memory_sidecar=1),
        lambda s: s["calls"]["by_model"].update({"a model with spaces": 1}),
        lambda s: s["calls"]["by_route"].update({LIGHTNING: "9"}),
        lambda s: s["memory_trace_rows"].update(reason=1),
        lambda s: s.update(provider_route="Nightshift at 127.0.0.1"),
        lambda s: s.update(corpus_as_of_utc="yesterday"),
        lambda s: s.update(producer_commit="abc123"),
        lambda s: s.pop("cache_hits"),
    ):
        s = copy.deepcopy(good)
        mutate(s)
        bad_cases.append(s)
    for s in bad_cases:
        with pytest.raises(ex.ExportError) as err:
            ex.check_allowlist(s, set(PRIVATE))
        assert err.value.code == "summary_not_allowlisted", s
    leaky = copy.deepcopy(good)
    leaky["calls"]["by_model"] = {"rcpt-SECRET-RECEIPT-0001": 11}  # an id that has the shape of a model id
    with pytest.raises(ex.ExportError) as err:
        ex.check_allowlist(leaky, set(PRIVATE))
    assert err.value.code == "summary_leaks_private_data"


def test_rows_map_to_their_nodes_by_task_and_lane():
    assert ex.node_of({"task": "stance", "lane": "default"}) == "research"
    assert ex.node_of({"task": "stance_document", "lane": "fact_checker"}) == "fact_check"
    assert ex.node_of({"task": "stance", "lane": "reviewer"}) == "other"
    assert ex.node_of({"task": "topic_terms", "lane": "default"}) == "other"
    assert set(ex.TASK_NODE.values()) <= set(ex.NODES)


def test_the_node_list_is_the_graphs():
    from quorum_reasoning import graph

    assert set(ex.NODES) == set(graph.builder.nodes)


def test_provider_route_reads_the_receipt_evidence():
    assert ex.provider_route([{"http_status": 200, "receipt_hmem_injected": 0}, {"http_status": None}]) == "meterless"
    assert ex.provider_route([{"http_status": 200}, {"http_status": 200}]) == "nvidia"
    assert ex.provider_route([{"http_status": 200}, {"http_status": 200, "receipt_id": "r-1"}]) == "mixed"
    assert ex.provider_route([{"http_status": None}]) == "unknown"
