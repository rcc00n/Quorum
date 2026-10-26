"""scripts/edition_sidecar.py: the provisional sidecar the portal needs to accept a new edition (2026-10-26).

Synthetic snapshots only, in pytest's temporary directory; a throw-away git repository (isolated from the user's git
configuration) holds the producer commit and its config; nothing here reaches the network, Zetaris, a database or a
model route. The parity tests at the end read master's portal check code from the local `origin/master` ref
(`git show`, no fetch), run the portal's own binding and envelope functions on the same inputs, and pin the shape of
every check `reasoning_snapshot` makes: when the portal changes, they fail and name what to re-read.
"""

from __future__ import annotations

import ast
import builtins
import copy
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import symtable
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve()
SCRIPT = HERE.parents[1] / "scripts" / "edition_sidecar.py"
REPO_ROOT = HERE.parents[2]
PORTAL_REF = "origin/master"
PREVIEW = "backend/portal/reasoning_preview.py"
VALIDATION = "backend/portal/snapshot_validation.py"
COMMAND = "backend/portal/management/commands/reasoning_snapshot.py"
SHAPE_CHANGED = ("PORTAL SHAPE CHANGED on " + PORTAL_REF + ": re-read {what} and update scripts/edition_sidecar.py "
                 "(validate_sidecar) and these tests before writing another sidecar")


def _load_script():
    spec = importlib.util.spec_from_file_location("edition_sidecar_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


es = _load_script()

WINDOW = ("2026-10-25T09:30:00Z", "2026-10-26T09:30:00Z")  # 05:30 to 05:30 America/New_York (EDT)
GENERATED = "2026-10-26T11:02:13Z"


def _python_rejects_hour_24() -> bool:
    """Python 3.10 (the production portal) rejects T24:00; Python 3.14 reads it as next-day midnight."""
    try:
        datetime.fromisoformat("2026-10-25T24:00+00:00")
    except ValueError:
        return True
    return False


PYTHON_REJECTS_HOUR_24 = _python_rejects_hour_24()


def base_snapshot() -> dict:
    """A synthetic, portal-valid reasoning 1.0 snapshot (no real topic, source or document)."""
    return {
        "schema_version": "1.0",
        "topic_id": "test-topic",
        "edition_date": "2026-10-26",
        "run_id": "2026-10-26-test-topic-1",
        "version": 1,
        "status": "ok",
        "summary": "Synthetic test edition.",
        "sources_missing": [],
        "stories": [],
        "roundup": {"empty_day": False, "count": 1, "groups": [{"name": "Test group", "items": [
            {"event_id": "ev-test-1", "line": "A synthetic roundup line.", "status": "unverified", "sources": []}]}]},
        "generated_at": GENERATED,
        "published_at": "2026-10-26T11:02:14Z",
        "expires_at": "2026-10-27T12:00:00Z",
        "edition_timezone": "America/New_York",
        "window": {"start": WINDOW[0], "end": WINDOW[1]},
        "provenance": {"corpus": "zetaris", "model": "test-model", "fact_checker_model": "test-checker",
                       "fictional": False, "model_calls": 3, "answered_by": {"test-model": 2, "test-checker": 1},
                       "model_errors": 0},
        "trace": [{"node": "plan", "iteration": 1, "event_id": None, "decision": "test", "reason": "synthetic",
                   "model": None, "duration_ms": 0}],
        "errors": [],
    }


def story() -> dict:
    """A synthetic story the portal accepts: a confirmed fact, a sourced context block, framing on both flanks."""
    return {
        "event_id": "ev-story-1", "rank": 1, "headline": "Synthetic headline", "standfirst": "Synthetic standfirst.",
        "reading_minutes": 2,
        "rubric": {"legal_force": 1, "reach": 2, "irreversibility": 1, "confirmation": 2, "total": 6,
                   "rationale": {"reach": "Synthetic rationale."}},
        "photo": None,
        "article": [
            {"kind": "fact", "text": "A synthetic fact.", "claim_ids": ["c-1"], "sources": []},
            {"kind": "context", "text": "Synthetic context.", "claim_ids": [],
             "sources": [{"title": "Example source", "url": "https://example.com/context"}]},
        ],
        "claims": [
            {"id": "c-1", "text": "A synthetic confirmed claim.", "status": "confirmed", "verifier": "confirmed",
             "fact_checker": "confirmed", "reason": "Synthetic reason.", "evidence": [
                 {"stance": "supports", "quote": "A synthetic quote.", "title": "Example source",
                  "url": "https://example.com/evidence", "independence_group": "example.com",
                  "source_id": "src-example", "document_id": 1, "official_doc_id": None}]},
            {"id": "c-2", "text": "A synthetic unverified claim.", "status": "unverified", "verifier": "unverified",
             "fact_checker": "unverified", "reason": "Synthetic reason.", "evidence": []},
        ],
        "spectrum": {"rating_mode": "average", "coverage": {"center": [1, 2]}, "interpretations": [],
                     "left": {"highlights": "h", "omits": "o", "wording": "w", "example_url": ""},
                     "right": {"highlights": "h", "omits": "o", "wording": "w",
                               "example_url": "https://example.com/right"},
                     "note": "Synthetic framing note."},
        "needs_review": False,
        "trace_ref": "trace-1",
    }


def story_snapshot() -> dict:
    snap = base_snapshot()
    snap["stories"] = [story()]
    return snap


def pre_cut_snapshot() -> dict:
    """A run that finished before the window end: generated_at, not window.end, bounds the capture time."""
    snap = base_snapshot()
    snap.update(generated_at="2026-10-26T08:00:00Z", published_at="2026-10-26T08:00:01Z")
    return snap


def snapshot_bytes(snap: dict) -> bytes:
    return json.dumps(snap, ensure_ascii=False, indent=2).encode("utf-8")


# ---------------------------------------------------------------- fixtures


@pytest.fixture(scope="module")
def producer(tmp_path_factory):
    """A temporary git repository: one commit with reasoning/config/reasoning.toml, a later one without it."""
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
    config = b"[research]\nstance_min_overlap = 0.15\n"
    (repo / "reasoning" / "config").mkdir(parents=True)
    (repo / "reasoning" / "config" / "reasoning.toml").write_bytes(config)
    git("add", "reasoning/config/reasoning.toml")
    git("commit", "-q", "-m", "config")
    with_config = git("rev-parse", "HEAD")
    git("rm", "-q", "reasoning/config/reasoning.toml")
    git("commit", "-q", "-m", "drop config")
    without_config = git("rev-parse", "HEAD")
    return SimpleNamespace(repo=repo, commit=with_config, no_config=without_config,
                           config_sha256=hashlib.sha256(config).hexdigest())


@pytest.fixture
def edition(tmp_path):
    """Writes a snapshot (base or mutated) into a fresh directory and returns its path."""
    folder = tmp_path / "store" / "test-topic" / "2026-10-26"
    folder.mkdir(parents=True)

    def write(snap: dict | None = None, raw: bytes | None = None) -> Path:
        path = folder / "v1.json"
        path.write_bytes(raw if raw is not None else snapshot_bytes(snap or base_snapshot()))
        return path

    return write


def good_sidecar(path: Path, producer, corpus: str = "2026-10-26T09:30Z") -> dict:
    raw = path.read_bytes()
    return es.build_sidecar(raw, json.loads(raw), corpus, producer.commit, producer.config_sha256)


def run_main(capsys, *args: str) -> tuple[int, str, str]:
    code = es.main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def cli(path: Path, producer, corpus: str = "2026-10-26T10:30Z", commit: str | None = None, *extra: str) -> list[str]:
    return ["--snapshot", str(path), "--corpus-as-of", corpus, "--producer-commit", commit or producer.commit,
            "--repo", str(producer.repo), *extra]


def files_in(path: Path) -> list[str]:
    return sorted(p.name for p in path.parent.iterdir())


def refused(capsys, args: list[str], code: str, snapshot: Path) -> str:
    before = files_in(snapshot)
    rc, out, err = run_main(capsys, *args)
    assert rc == 2, (out, err)
    assert f"refused ({code})" in err, err
    assert "nothing written" in err
    assert files_in(snapshot) == before, "a refused run wrote files"
    return err


# ---------------------------------------------------------------- the happy path


def test_writes_sidecar_and_both_hash_files_in_the_agreed_shape(edition, producer, capsys):
    path = edition()
    raw = path.read_bytes()
    rc, out, err = run_main(capsys, *cli(path, producer, corpus="2026-10-26T00:23Z"))
    assert rc == 0, err
    assert err == ""  # in the window: no clamp note
    sidecar_path = path.with_name("v1.json.sidecar.json")
    data = sidecar_path.read_bytes()
    sidecar = json.loads(data)
    assert list(sidecar) == ["snapshot", "provisional", "corpus_as_of_utc", "edition_window_utc", "producer"]
    assert list(sidecar["snapshot"]) == ["sha256", "topic_id", "edition_date", "version", "run_id", "status", "bytes"]
    assert list(sidecar["producer"]) == ["commit", "config_sha256"]
    assert sidecar == {
        "snapshot": {"sha256": hashlib.sha256(raw).hexdigest(), "topic_id": "test-topic", "edition_date": "2026-10-26",
                     "version": 1, "run_id": "2026-10-26-test-topic-1", "status": "ok", "bytes": len(raw)},
        "provisional": True,
        "corpus_as_of_utc": "2026-10-26T00:23Z",
        "edition_window_utc": list(WINDOW),
        "producer": {"commit": producer.commit, "config_sha256": producer.config_sha256},
    }
    assert data == (json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n").encode("utf-8")  # stable bytes, LF
    assert b"\r\n" not in data
    assert path.with_name("v1.json.sidecar.json.sha256").read_bytes() == \
        f"{hashlib.sha256(data).hexdigest()}  v1.json.sidecar.json\n".encode()
    assert path.with_name("v1.json.sha256").read_bytes() == f"{hashlib.sha256(raw).hexdigest()}  v1.json\n".encode()
    assert path.read_bytes() == raw  # the snapshot itself is never touched
    assert hashlib.sha256(data).hexdigest() in out and hashlib.sha256(raw).hexdigest() in out
    assert files_in(path) == ["v1.json", "v1.json.sha256", "v1.json.sidecar.json", "v1.json.sidecar.json.sha256"]


def test_out_option_and_rerun_replace_the_files(edition, producer, capsys, tmp_path):
    path = edition()
    out = tmp_path / "hand-over.sidecar.json"
    assert run_main(capsys, *cli(path, producer, "2026-10-26T00:23Z", None, "--out", str(out)))[0] == 0
    first = out.read_bytes()
    assert run_main(capsys, *cli(path, producer, "2026-10-26T01:00Z", None, "--out", str(out)))[0] == 0
    assert out.read_bytes() != first and json.loads(out.read_bytes())["corpus_as_of_utc"] == "2026-10-26T01:00Z"
    assert (tmp_path / "hand-over.sidecar.json.sha256").read_text().split("  ") == \
        [hashlib.sha256(out.read_bytes()).hexdigest(), "hand-over.sidecar.json\n"]
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


def test_serialize_keeps_non_ascii_characters():
    assert es.serialize({"a": "é ü"}) == '{\n  "a": "é ü"\n}\n'.encode("utf-8")


def test_validate_sidecar_accepts_what_build_sidecar_makes(edition, producer):
    path = edition()
    data = es.serialize(good_sidecar(path, producer))
    hashes = es.validate_sidecar(data, path, producer.commit, producer.repo)
    assert hashes == {"snapshot_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "sidecar_sha256": hashlib.sha256(data).hexdigest()}
    assert es.validate_sidecar(good_sidecar(path, producer), path, producer.commit, producer.repo) == hashes


# ---------------------------------------------------------------- corpus time


def test_post_cut_dump_is_clamped_to_window_end_and_said_on_stderr(edition, producer, capsys):
    path = edition()
    rc, _, err = run_main(capsys, *cli(path, producer, corpus="2026-10-26T10:30Z"))
    assert rc == 0
    assert json.loads(path.with_name("v1.json.sidecar.json").read_bytes())["corpus_as_of_utc"] == "2026-10-26T09:30:00Z"
    assert "clamped to min(window.end, generated_at) = 2026-10-26T09:30:00Z" in err


@pytest.mark.parametrize("corpus", ["2026-10-25T09:30Z", "2026-10-25T09:30:00Z", "2026-10-26T09:30Z"])
def test_corpus_time_at_the_window_bounds_is_kept_verbatim(edition, producer, capsys, corpus):
    path = edition()
    rc, _, err = run_main(capsys, *cli(path, producer, corpus=corpus))
    assert rc == 0 and err == ""
    assert json.loads(path.with_name("v1.json.sidecar.json").read_bytes())["corpus_as_of_utc"] == corpus


def test_pre_cut_run_keeps_a_corpus_time_equal_to_generated_at(edition, producer, capsys):
    snap = base_snapshot()
    snap.update(generated_at="2026-10-26T08:00:00Z", published_at="2026-10-26T08:00:01Z")
    path = edition(snap)
    assert run_main(capsys, *cli(path, producer, corpus="2026-10-26T08:00:00Z"))[0] == 0
    assert json.loads(path.with_name("v1.json.sidecar.json").read_bytes())["corpus_as_of_utc"] == "2026-10-26T08:00:00Z"


def test_refuses_a_corpus_time_before_the_window(edition, producer, capsys):
    path = edition()
    err = refused(capsys, cli(path, producer, corpus="2026-10-25T09:29Z"), "corpus_before_window", path)
    assert "before the edition window start" in err


def test_refuses_a_corpus_time_after_generated_at(edition, producer, capsys):
    path = edition()
    refused(capsys, cli(path, producer, corpus="2026-10-26T11:02:14Z"), "corpus_after_generation", path)
    snap = base_snapshot()
    snap.update(generated_at="2026-10-26T08:00:00Z", published_at="2026-10-26T08:00:01Z")
    path = edition(snap)
    refused(capsys, cli(path, producer, corpus="2026-10-26T08:00:01Z"), "corpus_after_generation", path)


@pytest.mark.parametrize("corpus", ["2026-10-26T10:30:00+00:00", "2026-10-26 10:30Z", "2026-10-26T10:30:00.5Z",
                                    "2026-02-30T03:53Z", "2026-10-26T10Z", "yesterday", ""])
def test_refuses_a_corpus_time_in_another_format(edition, producer, capsys, corpus):
    path = edition()
    refused(capsys, cli(path, producer, corpus=corpus), "invalid_sidecar", path)


@pytest.mark.parametrize("corpus", ["2026-10-25T24:00Z", "2026-10-25T24:00:00Z"])
def test_refuses_hour_24_inside_the_window_whatever_this_python_accepts(edition, producer, capsys, corpus):
    """T24:00 on 25 Oct is 26 Oct 00:00, inside the window; Python 3.14 parses it, the portal's Python 3.10 does not."""
    path = edition()
    err = refused(capsys, cli(path, producer, corpus=corpus), "invalid_sidecar", path)
    assert "has hour 24" in err and "YYYY-MM-DDT00:00Z" in err
    with pytest.raises(es.SidecarError) as caught:
        es.capture_time(corpus)
    assert caught.value.code == "invalid_sidecar"


def test_next_day_midnight_written_canonically_is_kept(edition, producer, capsys):
    path = edition()
    rc, _, err = run_main(capsys, *cli(path, producer, corpus="2026-10-26T00:00Z"))
    assert rc == 0 and err == ""
    assert json.loads(path.with_name("v1.json.sidecar.json").read_bytes())["corpus_as_of_utc"] == "2026-10-26T00:00Z"


# ---------------------------------------------------------------- refusals: genuine output, commit, config, files


@pytest.mark.parametrize("change, words", [
    (lambda p: p.update(fictional=True, corpus="fixture:default"), "fictional"),
    (lambda p: p.update(model="stand-ins", fact_checker_model="stand-ins"), "stand-ins"),
    (lambda p: p.update(model_calls=0, answered_by={}), "no model call"),
    (lambda p: [p.pop("model_calls"), p.pop("answered_by"), p.pop("model_errors")], "no model call"),
], ids=["fictional", "stand-ins", "zero-calls", "no-call-count"])
def test_refuses_output_that_is_not_genuine(edition, producer, capsys, change, words):
    snap = base_snapshot()
    change(snap["provenance"])
    path = edition(snap)
    assert words in refused(capsys, cli(path, producer), "genuine_model_output_required", path)


@pytest.mark.parametrize("commit", ["abc1234", "A" * 40, "a" * 41, "g" * 40, " " + "a" * 39, ""])
def test_refuses_a_producer_commit_that_is_not_40_lowercase_hex(edition, producer, capsys, commit):
    path = edition()
    args = cli(path, producer)
    args[args.index("--producer-commit") + 1] = commit
    refused(capsys, args, "expected_full_producer_commit_required", path)


def test_refuses_a_commit_that_is_not_in_the_repository(edition, producer, capsys):
    path = edition()
    refused(capsys, cli(path, producer, "2026-10-26T10:30Z", "0123456789abcdef0123456789abcdef01234567"),
            "producer_commit_unknown", path)


def test_refuses_a_commit_without_the_config(edition, producer, capsys):
    path = edition()
    err = refused(capsys, cli(path, producer, "2026-10-26T10:30Z", producer.no_config), "producer_config_unavailable", path)
    assert "reasoning/config/reasoning.toml" in err


def test_refuses_a_missing_snapshot(producer, capsys, tmp_path):
    path = tmp_path / "v9.json"
    refused(capsys, cli(path, producer), "snapshot_unreadable", path)


def test_refuses_a_hard_linked_snapshot(edition, producer, capsys):
    path = edition()
    os.link(path, path.with_name("latest-link.json"))
    refused(capsys, cli(path, producer), "unsafe_snapshot_file", path)


def test_refuses_a_symlinked_snapshot(edition, producer, capsys):
    path = edition()
    link = path.with_name("link.json")
    try:
        os.symlink(path, link)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot create symlinks")
    refused(capsys, cli(link, producer), "unsafe_snapshot_file", path)


def test_refuses_a_snapshot_that_lstat_reports_as_a_symlink(edition, producer, capsys, monkeypatch):
    """Runs where symlinks cannot be created too: the rule is that the snapshot's own entry (lstat) is a file."""
    path = edition()
    real = es.os.lstat
    link = os.stat_result((stat.S_IFLNK | 0o644, 0, 0, 1, 0, 0, path.stat().st_size, 0, 0, 0))
    monkeypatch.setattr(es.os, "lstat", lambda p, *a, **k: link if Path(p) == path else real(p, *a, **k))
    refused(capsys, cli(path, producer), "unsafe_snapshot_file", path)


def test_refuses_a_snapshot_over_the_portal_size_limit(edition, producer, capsys):
    path = edition(raw=b" " * (es.MAX_BYTES + 1))
    refused(capsys, cli(path, producer), "payload_too_large", path)


def test_refuses_an_invalid_snapshot_envelope(edition, producer, capsys):
    snap = base_snapshot()
    snap["window"]["end"] = "2026-10-26T10:30:00Z"
    path = edition(snap)
    refused(capsys, cli(path, producer), "inconsistent_edition_window", path)


def test_refuses_the_snapshot_under_the_portal_impact_hold(edition, producer, capsys):
    snap = base_snapshot()
    snap["run_id"] = es.HELD_RUN_ID
    path = edition(snap)
    refused(capsys, cli(path, producer), "impact_score_review_required", path)


@pytest.mark.parametrize("target", ["v1.json", "v1.json.sha256"])
def test_refuses_an_out_path_that_would_overwrite_the_snapshot_or_its_hash(edition, producer, capsys, target):
    path = edition()
    raw = path.read_bytes()
    refused(capsys, cli(path, producer, "2026-10-26T10:30Z", None, "--out", str(path.with_name(target))),
            "out_path_conflict", path)
    assert path.read_bytes() == raw


@pytest.mark.parametrize("target", ["V1.JSON", "V1.JSON.SHA256", "v1.JSON.sha256"])
def test_refuses_an_out_path_that_differs_from_the_snapshot_or_its_hash_only_in_case(edition, producer, capsys,
                                                                                      target):
    """On a case-insensitive file system (NTFS, APFS) V1.JSON is the snapshot itself; refused on every system."""
    path = edition()
    raw = path.read_bytes()
    refused(capsys, cli(path, producer, "2026-10-26T10:30Z", None, "--out", str(path.with_name(target))),
            "out_path_conflict", path)
    assert path.read_bytes() == raw
    if path.with_name("V1.JSON").exists():  # case-insensitive here: the variant really was the snapshot
        assert path.with_name("V1.JSON").read_bytes() == raw


def test_case_variants_are_the_same_path_where_normcase_keeps_case(monkeypatch):
    """As on macOS, where os.path.normcase returns the path unchanged but APFS ignores case."""
    monkeypatch.setattr(es.os.path, "normcase", lambda value: value)
    assert es._same(Path("edition") / "v1.json", Path("edition") / "V1.JSON")
    assert es._same(Path("edition") / "v1.json", Path("edition") / "x" / ".." / "v1.json")
    assert not es._same(Path("edition") / "v1.json", Path("edition") / "v2.json")


def test_refuses_an_out_directory_that_does_not_exist(edition, producer, capsys, tmp_path):
    path = edition()
    refused(capsys, cli(path, producer, "2026-10-26T10:30Z", None, "--out", str(tmp_path / "nowhere" / "s.json")),
            "out_dir_missing", path)


def test_validate_runs_before_anything_is_written(edition, producer, capsys, monkeypatch):
    path = edition()
    real = es.build_sidecar

    def off_by_one(*args, **kwargs):
        sidecar = real(*args, **kwargs)
        sidecar["snapshot"]["bytes"] += 1
        return sidecar

    monkeypatch.setattr(es, "build_sidecar", off_by_one)
    refused(capsys, cli(path, producer), "sidecar_size_mismatch", path)


def test_a_failed_write_leaves_no_file_and_no_temporary(edition, producer, capsys, monkeypatch):
    path = edition()
    real = es.tempfile.mkstemp
    calls = []

    def third_fails(*args, **kwargs):
        calls.append(1)
        if len(calls) == 3:
            raise PermissionError(13, "denied")
        return real(*args, **kwargs)

    monkeypatch.setattr(es.tempfile, "mkstemp", third_fails)
    refused(capsys, cli(path, producer), "write_failed", path)
    assert files_in(path) == ["v1.json"]


def test_refuses_a_snapshot_that_changes_after_validation(edition, producer, capsys, monkeypatch):
    path = edition()
    real = es.read_snapshot_file
    calls = []

    def third_read_differs(snapshot):
        calls.append(snapshot)
        raw = real(snapshot)
        return raw + b" " if len(calls) == 3 else raw  # make, validate_sidecar, then the re-read before writing

    monkeypatch.setattr(es, "read_snapshot_file", third_read_differs)
    refused(capsys, cli(path, producer), "snapshot_changed", path)
    assert len(calls) == 3


def _tamper_sidecar_on_replace(monkeypatch):
    real = es.os.replace

    def replace(src, dst):
        real(src, dst)
        if str(dst).endswith(".sidecar.json"):
            Path(dst).write_bytes(b"{}\n")

    monkeypatch.setattr(es.os, "replace", replace)


def test_a_sidecar_that_differs_on_disk_after_the_write_is_refused_and_removed(edition, producer, capsys,
                                                                                monkeypatch):
    path = edition()
    _tamper_sidecar_on_replace(monkeypatch)
    rc, out, err = run_main(capsys, *cli(path, producer))
    assert rc == 2, (out, err)
    assert "refused (write_failed)" in err and "differs from the validated bytes" in err
    assert "the files it wrote were removed" in err and "nothing written" not in err
    assert files_in(path) == ["v1.json"]


def test_a_sidecar_that_differs_on_disk_and_cannot_be_removed_is_named(edition, producer, capsys, monkeypatch):
    path = edition()
    _tamper_sidecar_on_replace(monkeypatch)
    monkeypatch.setattr(es, "_remove", lambda _: False)
    rc, out, err = run_main(capsys, *cli(path, producer))
    assert rc == 2, (out, err)
    assert "refused (write_failed)" in err and "nothing written" not in err
    left = err.split("delete ", 1)[1]
    for name in ("v1.json.sidecar.json", "v1.json.sidecar.json.sha256", "v1.json.sha256"):
        assert str(path.with_name(name)) in left
    assert "before any hand-over" in left


HAND_OVER = ("v1.json.sidecar.json", "v1.json.sidecar.json.sha256", "v1.json.sha256")  # the order of the replaces


def _replace_fails_on(monkeypatch, n: int) -> None:
    real = es.os.replace
    calls = []

    def replace(src, dst):
        calls.append(dst)
        if len(calls) == n:
            raise PermissionError(13, "Access is denied")
        real(src, dst)

    monkeypatch.setattr(es.os, "replace", replace)


def _assert_no_unmatched_sidecar(path: Path) -> None:
    """A sidecar on disk always sits beside a .sha256 that matches it, and no temporary file is left."""
    sidecar = path.with_name("v1.json.sidecar.json")
    if sidecar.exists():
        line = path.with_name("v1.json.sidecar.json.sha256").read_text()
        assert line == f"{hashlib.sha256(sidecar.read_bytes()).hexdigest()}  v1.json.sidecar.json\n"
    assert not [name for name in files_in(path) if name.endswith(".tmp")]


@pytest.mark.parametrize("n", [2, 3])
def test_a_replace_that_fails_part_way_on_a_first_run_removes_what_it_replaced(edition, producer, capsys,
                                                                               monkeypatch, n):
    path = edition()
    _replace_fails_on(monkeypatch, n)
    rc, out, err = run_main(capsys, *cli(path, producer))
    assert rc == 2, (out, err)
    assert "refused (write_failed)" in err and "Access is denied" in err
    assert "nothing written" not in err and "earlier run" not in err
    removed = err.split("the files it wrote were removed: ", 1)[1]
    for name in HAND_OVER[:n - 1]:
        assert str(path.with_name(name)) in removed
    assert files_in(path) == ["v1.json"]
    _assert_no_unmatched_sidecar(path)


@pytest.mark.parametrize("n", [2, 3])
def test_a_replace_that_fails_part_way_on_a_rerun_names_the_files_left_from_the_earlier_run(edition, producer,
                                                                                            capsys, monkeypatch, n):
    path = edition()
    assert run_main(capsys, *cli(path, producer, "2026-10-26T00:23Z"))[0] == 0
    before = {name: path.with_name(name).read_bytes() for name in HAND_OVER}
    _replace_fails_on(monkeypatch, n)
    rc, out, err = run_main(capsys, *cli(path, producer, "2026-10-26T01:00Z"))
    assert rc == 2, (out, err)
    assert "refused (write_failed)" in err and "nothing written" not in err
    removed, earlier = err.split("the files it wrote were removed: ", 1)[1].split("left from an earlier run", 1)
    for name in HAND_OVER[:n - 1]:
        assert str(path.with_name(name)) in removed and not path.with_name(name).exists()
    for name in HAND_OVER[n - 1:]:
        assert str(path.with_name(name)) in earlier
        assert path.with_name(name).read_bytes() == before[name]  # the earlier file is left as it was, and named
    assert "delete them before any hand-over" in earlier
    assert files_in(path) == sorted(["v1.json", *HAND_OVER[n - 1:]])
    _assert_no_unmatched_sidecar(path)


def test_a_first_replace_that_fails_leaves_the_earlier_set_intact_and_says_nothing_written(edition, producer, capsys,
                                                                                         monkeypatch):
    path = edition()
    assert run_main(capsys, *cli(path, producer, "2026-10-26T00:23Z"))[0] == 0
    before = {name: path.with_name(name).read_bytes() for name in HAND_OVER}
    _replace_fails_on(monkeypatch, 1)
    rc, out, err = run_main(capsys, *cli(path, producer, "2026-10-26T01:00Z"))
    assert rc == 2, (out, err)
    assert "refused (write_failed)" in err and err.rstrip().endswith("; nothing written")
    assert {name: path.with_name(name).read_bytes() for name in HAND_OVER} == before
    _assert_no_unmatched_sidecar(path)


def test_a_replaced_file_that_cannot_be_removed_after_a_failed_replace_is_named(edition, producer, capsys,
                                                                                monkeypatch):
    path = edition()
    _replace_fails_on(monkeypatch, 3)
    monkeypatch.setattr(es, "_remove", lambda _: False)
    rc, out, err = run_main(capsys, *cli(path, producer))
    assert rc == 2, (out, err)
    assert "nothing written" not in err and "were removed" not in err
    left = err.split("delete ", 1)[1]
    for name in HAND_OVER[:2]:
        assert str(path.with_name(name)) in left
    assert "before any hand-over" in left


@pytest.mark.skipif(os.name != "nt", reason="replacing onto a read-only file fails on Windows only")
def test_a_read_only_hash_file_on_a_rerun_is_reported_on_the_real_filesystem(edition, producer, capsys):
    path = edition()
    assert run_main(capsys, *cli(path, producer, "2026-10-26T00:23Z"))[0] == 0
    locked = path.with_name("v1.json.sidecar.json.sha256")
    os.chmod(locked, stat.S_IREAD)
    try:
        rc, out, err = run_main(capsys, *cli(path, producer, "2026-10-26T01:00Z"))
    finally:
        os.chmod(locked, stat.S_IREAD | stat.S_IWRITE)
    assert rc == 2, (out, err)
    assert "refused (write_failed)" in err and "nothing written" not in err
    assert str(locked) in err.split("left from an earlier run", 1)[1]
    assert not path.with_name("v1.json.sidecar.json").exists()
    _assert_no_unmatched_sidecar(path)


# ---------------------------------------------------------------- validate_sidecar: one check each


def _set(path: tuple, value):
    def change(s):
        target = s
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
    return change


def _drop(path: tuple):
    def change(s):
        target = s
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]
    return change


# (id, mutation, our code, does the portal's own bind_preview_sidecar reject it too?[, the snapshot, base by default])
SIDECAR_MUTATIONS = [
    ("sha256", _set(("snapshot", "sha256"), "0" * 64), "sidecar_snapshot_mismatch", True),
    ("topic_id", _set(("snapshot", "topic_id"), "other-topic"), "sidecar_snapshot_mismatch", True),
    ("edition_date", _set(("snapshot", "edition_date"), "2026-10-25"), "sidecar_snapshot_mismatch", True),
    ("version-value", _set(("snapshot", "version"), 2), "sidecar_snapshot_mismatch", True),
    ("version-float", _set(("snapshot", "version"), 1.0), "sidecar_snapshot_mismatch", True),
    ("version-bool", _set(("snapshot", "version"), True), "sidecar_snapshot_mismatch", True),
    ("version-string", _set(("snapshot", "version"), "1"), "sidecar_snapshot_mismatch", True),
    ("run_id", _set(("snapshot", "run_id"), "2026-10-26-test-topic-2"), "sidecar_snapshot_mismatch", True),
    ("status", _set(("snapshot", "status"), "partial"), "sidecar_snapshot_mismatch", True),
    ("identity-missing", _drop(("snapshot", "run_id")), "invalid_sidecar", True),
    ("bytes-value", lambda s: s["snapshot"].update(bytes=s["snapshot"]["bytes"] + 1), "sidecar_size_mismatch", True),
    ("bytes-bool", _set(("snapshot", "bytes"), True), "sidecar_size_mismatch", True),
    ("bytes-missing", _drop(("snapshot", "bytes")), "sidecar_size_mismatch", False),
    ("provisional-string", _set(("provisional",), "true"), "invalid_sidecar", True),
    ("provisional-false", _set(("provisional",), False), "provisional_required", False),
    ("provisional-missing", _drop(("provisional",)), "invalid_sidecar", True),
    ("capture-offset", _set(("corpus_as_of_utc",), "2026-10-26T03:53+00:00"), "invalid_sidecar", True),
    ("capture-local", _set(("corpus_as_of_utc",), "2026-10-22T03:53-06:00"), "invalid_sidecar", True),
    ("capture-fraction", _set(("corpus_as_of_utc",), "2026-10-26T00:23:00.5Z"), "invalid_sidecar", True),
    ("capture-impossible-date", _set(("corpus_as_of_utc",), "2026-02-30T03:53Z"), "invalid_sidecar", True),
    # inside the window as next-day midnight; the binding rejects it only on a Python whose fromisoformat does (the
    # production portal's 3.10 does, 3.14 does not), so the expectation follows the interpreter running the binding here
    ("capture-hour-24", _set(("corpus_as_of_utc",), "2026-10-25T24:00Z"), "invalid_sidecar", PYTHON_REJECTS_HOUR_24),
    ("capture-not-text", _set(("corpus_as_of_utc",), 1761436800), "invalid_sidecar", True),
    ("capture-missing", _drop(("corpus_as_of_utc",)), "invalid_sidecar", True),
    ("capture-before-start", _set(("corpus_as_of_utc",), "2026-10-25T09:29Z"), "sidecar_capture_outside_window", True),
    ("capture-after-end", _set(("corpus_as_of_utc",), "2026-10-26T09:31Z"), "sidecar_capture_outside_window", True),
    # a pre-cut run: inside the window but after generated_at (08:00:00Z), so min(window.end, generated_at) binds
    ("capture-after-generated-at", _set(("corpus_as_of_utc",), "2026-10-26T09:00Z"), "sidecar_capture_outside_window",
     True, pre_cut_snapshot),
    ("window-reversed", lambda s: s["edition_window_utc"].reverse(), "sidecar_window_mismatch", True),
    ("window-reformatted", _set(("edition_window_utc",), ["2026-10-25T09:30Z", "2026-10-26T09:30Z"]),
     "sidecar_window_mismatch", True),
    ("window-missing", _drop(("edition_window_utc",)), "invalid_sidecar", True),
    ("snapshot-not-object", _set(("snapshot",), []), "invalid_sidecar", True),
    ("closed-snapshot-form", _set(("snapshot", "sha256_file_bytes"), "0" * 64), "closed_form_not_produced", True),
    ("closed-producer-form", _set(("producer", "commit_of_the_publishing_process"), "abc1234"),
     "closed_form_not_produced", False),
    ("extra-field", _set(("private_evidence",), {"journal": "TEST-private"}), "unexpected_sidecar_field", False),
    ("extra-snapshot-field", _set(("snapshot", "stories"), 0), "unexpected_sidecar_field", False),
    ("extra-producer-field", _set(("producer", "config_sha256_git_blob_lf"), "0" * 64), "unexpected_sidecar_field", False),
    ("key-order", lambda s: s.update(snapshot=dict(reversed(list(s["snapshot"].items())))), "unexpected_sidecar_field", False),
    ("producer-missing", _drop(("producer",)), "unexpected_sidecar_field", False),
    ("commit-prefix-only", lambda s: s["producer"].update(commit=s["producer"]["commit"][:7]), "producer_commit_mismatch", False),
    ("commit-other", _set(("producer", "commit"), "f" * 40), "producer_commit_mismatch", False),
    ("commit-not-hex", _set(("producer", "commit"), "HEAD"), "producer_commit_mismatch", False),
    ("commit-not-text", _set(("producer", "commit"), 7), "invalid_sidecar", False),
    ("config-not-hex", lambda s: s["producer"].update(config_sha256=s["producer"]["config_sha256"].upper()),
     "invalid_config_sha256", False),
    ("config-wrong", _set(("producer", "config_sha256"), "0" * 64), "producer_config_mismatch", False),
]
SIDECAR_CASES = [(row_id, mutate, code, portal_rejects, rest[0] if rest else base_snapshot)
                 for row_id, mutate, code, portal_rejects, *rest in SIDECAR_MUTATIONS]


@pytest.mark.parametrize("mutate, code, snapshot", [(m, c, s) for _, m, c, _, s in SIDECAR_CASES],
                         ids=[i for i, *_ in SIDECAR_CASES])
def test_validate_sidecar_rejects(edition, producer, mutate, code, snapshot):
    path = edition(snapshot())
    sidecar = good_sidecar(path, producer)
    mutate(sidecar)
    with pytest.raises(es.SidecarError) as caught:
        es.validate_sidecar(es.serialize(sidecar), path, producer.commit, producer.repo)
    assert caught.value.code == code


@pytest.mark.parametrize("raw, code", [
    (b"[]", "invalid_sidecar"), (b"null", "invalid_sidecar"), (b"true", "invalid_sidecar"),
    (b'{"provisional":false,"provisional":true}', "duplicate_json_key"),
    (b'{"unused":NaN}', "non_finite_number"), (b'{"unused":-Infinity}', "non_finite_number"),
    (b"\xff", "invalid_reasoning_json"), (b"[" * 30 + b"0" + b"]" * 30, "excessive_nesting"),
    (b" " * (2 * 1024 * 1024 + 1), "payload_too_large"),
    (b'{"note":"nvapi-' + b"a" * 24 + b'"}', "unsafe_public_content"),
], ids=["list", "null", "true", "duplicate-key", "nan", "infinity", "not-utf8", "nesting", "size", "token-like"])
def test_validate_sidecar_rejects_bytes(edition, producer, raw, code):
    path = edition()
    with pytest.raises(es.SidecarError) as caught:
        es.validate_sidecar(raw, path, producer.commit, producer.repo)
    assert caught.value.code == code


def test_validate_sidecar_requires_the_full_producer_commit_argument(edition, producer):
    path = edition()
    with pytest.raises(es.SidecarError) as caught:
        es.validate_sidecar(good_sidecar(path, producer), path, producer.commit[:7], producer.repo)
    assert caught.value.code == "expected_full_producer_commit_required"


def test_validate_sidecar_checks_the_commit_and_the_config_in_the_repository(edition, producer):
    path = edition()
    unknown = "0123456789abcdef0123456789abcdef01234567"
    sidecar = good_sidecar(path, producer)
    sidecar["producer"]["commit"] = unknown
    with pytest.raises(es.SidecarError) as caught:
        es.validate_sidecar(sidecar, path, unknown, producer.repo)
    assert caught.value.code == "producer_commit_unknown"
    sidecar["producer"]["commit"] = producer.no_config
    with pytest.raises(es.SidecarError) as caught:
        es.validate_sidecar(sidecar, path, producer.no_config, producer.repo)
    assert caught.value.code == "producer_config_unavailable"


def test_validate_sidecar_requires_genuine_output(edition, producer):
    for change in (lambda p: p.update(fictional=True), lambda p: p.update(model="stand-ins"),
                   lambda p: p.update(model_calls=0, answered_by={})):
        snap = base_snapshot()
        change(snap["provenance"])
        path = edition(snap)
        with pytest.raises(es.SidecarError) as caught:
            es.validate_sidecar(good_sidecar(path, producer), path, producer.commit, producer.repo)
        assert caught.value.code == "genuine_model_output_required"


def test_validate_sidecar_keeps_the_v4_impact_hold(edition, producer, monkeypatch):
    path = edition()
    monkeypatch.setattr(es, "GENUINE_V4_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(es.SidecarError) as caught:
        es.validate_sidecar(good_sidecar(path, producer), path, producer.commit, producer.repo)
    assert caught.value.code == "impact_score_review_required"


def test_a_provisional_snapshot_needs_a_provisional_sidecar(edition, producer, monkeypatch):
    path = edition()
    monkeypatch.setattr(es, "HISTORICAL_V3_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    sidecar = good_sidecar(path, producer)
    sidecar["provisional"] = False
    with pytest.raises(es.SidecarError) as caught:
        es.validate_sidecar(sidecar, path, producer.commit, producer.repo)
    assert caught.value.code == "sidecar_provisional_mismatch"


# ---------------------------------------------------------------- the snapshot envelope: one check each


def _snap(change):
    def make():
        snap = base_snapshot()
        change(snap)
        return snapshot_bytes(snap)
    return make


SNAPSHOT_MUTATIONS = [
    ("not-object", lambda: b"[]", "invalid_reasoning_1_0"),
    ("duplicate-key", lambda: b'{"a":1,"a":2}', "duplicate_json_key"),
    ("too-large", lambda: b" " * (es.MAX_BYTES + 1), "payload_too_large"),
    ("not-utf8", lambda: b"\xff", "invalid_reasoning_json"),
    ("nan", lambda: b'{"a":NaN}', "non_finite_number"),
    ("nesting", lambda: b"[" * 30 + b"0" + b"]" * 30, "excessive_nesting"),
    ("missing-field", _snap(lambda s: s.pop("summary")), "missing_reasoning_field"),
    ("extra-field", _snap(lambda s: s.update(private="x")), "unsupported_reasoning_field"),
    ("schema-version", _snap(lambda s: s.update(schema_version="1.1")), "unsupported_reasoning_version"),
    ("topic-id", _snap(lambda s: s.update(topic_id="test topic")), "invalid_reasoning_id"),
    ("run-id", _snap(lambda s: s.update(run_id="")), "invalid_reasoning_id"),
    ("edition-date", _snap(lambda s: s.update(edition_date="2026-10-32")), "invalid_reasoning_date"),
    ("edition-date-basic", _snap(lambda s: s.update(edition_date="20261026")), "invalid_reasoning_date"),
    ("edition-date-no-previous-day", _snap(lambda s: s.update(edition_date="0001-01-01")), "invalid_reasoning_date"),
    ("generated-no-seconds", _snap(lambda s: s.update(generated_at="2026-10-26T11:02Z")), "invalid_reasoning_timestamp"),
    ("generated-impossible", _snap(lambda s: s.update(generated_at="2026-02-30T11:02:00Z")), "invalid_reasoning_timestamp"),
    ("expires-offset", _snap(lambda s: s.update(expires_at="2026-10-27T08:00:00-04:00")), "invalid_reasoning_timestamp"),
    ("published-before-generated", _snap(lambda s: s.update(published_at="2026-10-26T11:02:12Z")),
     "publication_before_generation"),
    ("timezone-unknown", _snap(lambda s: s.update(edition_timezone="Mars/Olympus_Mons")), "invalid_edition_timezone"),
    ("timezone-not-text", _snap(lambda s: s.update(edition_timezone=5)), "invalid_reasoning_1_0"),
    ("window-extra", _snap(lambda s: s["window"].update(middle=WINDOW[0])), "unsupported_reasoning_field"),
    ("window-missing-end", _snap(lambda s: s["window"].pop("end")), "missing_reasoning_field"),
    ("window-shifted", _snap(lambda s: s["window"].update(end="2026-10-26T10:30:00Z")), "inconsistent_edition_window"),
    ("window-other-day", _snap(lambda s: s.update(edition_date="2026-10-25")), "inconsistent_edition_window"),
    ("expires-at-end", _snap(lambda s: s.update(expires_at=WINDOW[1])), "expiry_before_edition_end"),
    ("provenance-missing-model", _snap(lambda s: s["provenance"].pop("model")), "missing_reasoning_field"),
    ("provenance-extra", _snap(lambda s: s["provenance"].update(key="x")), "unsupported_reasoning_field"),
    ("provenance-empty-model", _snap(lambda s: s["provenance"].update(model="")), "missing_reasoning_provenance"),
    ("provenance-model-too-long", _snap(lambda s: s["provenance"].update(model="x" * 20001)), "invalid_reasoning_1_0"),
    ("provenance-fictional-text", _snap(lambda s: s["provenance"].update(fictional="false")), "invalid_reasoning_1_0"),
    ("provenance-empty-checker", _snap(lambda s: s["provenance"].update(fact_checker_model="")),
     "missing_reasoning_provenance"),
    ("calls-negative", _snap(lambda s: s["provenance"].update(model_calls=-1)), "invalid_model_call_count"),
    ("calls-bool", _snap(lambda s: s["provenance"].update(model_calls=True)), "invalid_model_call_count"),
    ("calls-over-bound", _snap(lambda s: s["provenance"].update(model_calls=100001)), "invalid_model_call_count"),
    ("errors-over-bound", _snap(lambda s: s["provenance"].update(model_errors=100001)), "invalid_model_call_count"),
    ("answered-zero", _snap(lambda s: s["provenance"]["answered_by"].update(other=0)), "invalid_answered_by"),
    ("answered-too-many-models", _snap(lambda s: s["provenance"].update(
        answered_by={f"model-{i}": 1 for i in range(101)}, model_calls=101)), "invalid_answered_by"),
    ("answered-count-over-bound", _snap(lambda s: [s["provenance"].pop("model_calls"),
                                                   s["provenance"].update(answered_by={"test-model": 100001})]),
     "invalid_answered_by"),
    # 61 transport errors beside 63 in all is allowed only for the historical v3 bytes, never for a new hash
    ("historical-error-exception-elsewhere", _snap(lambda s: s["provenance"].update(
        model_calls=64, model_errors=63, answered_by={"test-model": 2, "test-checker": 1, "error": 61})),
     "inconsistent_model_error_count"),
    ("answered-sum", _snap(lambda s: s["provenance"].update(model_calls=4)), "inconsistent_model_call_count"),
    ("answered-errors", _snap(lambda s: s["provenance"].update(model_errors=1)), "inconsistent_model_error_count"),
    ("errors-over-calls", _snap(lambda s: [s["provenance"].pop("answered_by"), s["provenance"].update(model_errors=4)]),
     "inconsistent_model_error_count"),
    ("version-zero", _snap(lambda s: s.update(version=0)), "invalid_reasoning_1_0"),
    ("version-bool", _snap(lambda s: s.update(version=True)), "invalid_reasoning_1_0"),
    ("status", _snap(lambda s: s.update(status="done")), "invalid_reasoning_1_0"),
    ("token-like-text", _snap(lambda s: s.update(summary="Bearer " + "a" * 24)), "unsafe_public_content"),
]


@pytest.mark.parametrize("make, code", [(m, c) for _, m, c in SNAPSHOT_MUTATIONS], ids=[i for i, *_ in SNAPSHOT_MUTATIONS])
def test_check_snapshot_rejects(make, code):
    with pytest.raises(es.SidecarError) as caught:
        es.check_snapshot(make())
    assert caught.value.code == code
    # the envelope rules are refused by this tool's own explained check, before the portal copy runs
    assert not caught.value.message.startswith(es.PORTAL_REJECTS), caught.value.message


def _story_change(change):
    def make():
        snap = story_snapshot()
        change(snap)
        return snapshot_bytes(snap)
    return make


def _evidence(snap: dict) -> dict:
    return snap["stories"][0]["claims"][0]["evidence"][0]


def _article(snap: dict, index: int) -> dict:
    return snap["stories"][0]["article"][index]


# Content parse_reasoning checks after the envelope; each is refused only by the portal copy in the script.
CONTENT_MUTATIONS = [
    ("evidence-url-port", _story_change(lambda s: _evidence(s).update(url="https://example.com:8443/evidence")),
     "unsafe_reasoning_url"),
    ("roundup-source-url", _story_change(lambda s: s["roundup"]["groups"][0]["items"][0]["sources"].append(
        {"title": "Local", "url": "http://localhost/item"})), "unsafe_reasoning_url"),
    ("evidence-fetched-at", _story_change(lambda s: _evidence(s).update(fetched_at="2026-10-26T09:00Z")),
     "invalid_reasoning_timestamp"),
    ("roundup-count", _story_change(lambda s: s["roundup"].update(count=2)), "invalid_roundup_count"),
    ("fact-unconfirmed", _story_change(lambda s: _article(s, 0).update(claim_ids=["c-2"])),
     "unsafe_fact_claim_reference"),
    ("ok-missing-framing", _story_change(lambda s: s["stories"][0]["spectrum"].pop("left")),
     "missing_completed_framing"),
    ("context-unsourced", _story_change(lambda s: _article(s, 1).update(sources=[])), "unsourced_article_context"),
    ("article-unknown-claim", _story_change(lambda s: _article(s, 1).update(claim_ids=["c-9"])),
     "invalid_article_claim_reference"),
    ("rubric-total", _story_change(lambda s: s["stories"][0]["rubric"].update(total=7)), "invalid_impact_total"),
    ("story-rank", _story_change(lambda s: s["stories"][0].update(rank=0)), "invalid_reasoning_rank"),
    ("story-id", _story_change(lambda s: s["stories"][0].update(event_id="ev story")), "invalid_reasoning_id"),
    ("story-missing-field", _story_change(lambda s: s["stories"][0].pop("trace_ref")), "missing_reasoning_field"),
    ("story-extra-field", _story_change(lambda s: s["stories"][0].update(private="x")), "unsupported_reasoning_field"),
    ("story-reading-minutes", _story_change(lambda s: s["stories"][0].update(reading_minutes=0)),
     "invalid_reasoning_1_0"),
    ("duplicate-event", _story_change(lambda s: s["roundup"]["groups"][0]["items"][0].update(event_id="ev-story-1")),
     "duplicate_reasoning_event"),
    ("duplicate-claim", _story_change(lambda s: s["stories"][0]["claims"][1].update(id="c-1")),
     "duplicate_reasoning_claim"),
    ("cohort-counts", _story_change(lambda s: s["stories"][0]["spectrum"]["coverage"].update(center=[3, 2])),
     "invalid_cohort_counts"),
    ("empty-with-stories", _story_change(lambda s: s.update(status="empty")), "invalid_empty_snapshot"),
    ("quiet-day-with-stories", _story_change(lambda s: s["roundup"].update(empty_day=True)), "invalid_quiet_day"),
    ("trace-unknown-event", _story_change(lambda s: s["trace"][0].update(event_id="ev-unknown")),
     "invalid_trace_event_reference"),
    ("error-unknown-event", _story_change(lambda s: s.update(
        errors=[{"node": "plan", "event_id": "ev-unknown", "message": "Synthetic failure."}])),
     "invalid_error_event_reference"),
    ("conflicting-document-source", _story_change(lambda s: s["stories"][0]["claims"][1]["evidence"].append(
        {**_evidence(s), "source_id": "src-other"})), "conflicting_document_source"),
]
CONTENT = {row_id: (make, code) for row_id, make, code in CONTENT_MUTATIONS}


@pytest.mark.parametrize("make, code", [(m, c) for _, m, c in CONTENT_MUTATIONS], ids=[i for i, *_ in CONTENT_MUTATIONS])
def test_check_snapshot_rejects_content_through_the_portal_copy(make, code):
    with pytest.raises(es.SidecarError) as caught:
        es.check_snapshot(make())
    assert caught.value.code == code
    assert caught.value.message.startswith(f"{es.PORTAL_REJECTS} ({code}): ")


@pytest.mark.parametrize("row_id", ["evidence-url-port", "roundup-count", "fact-unconfirmed", "ok-missing-framing"])
def test_refuses_a_snapshot_whose_content_the_portal_rejects(edition, producer, capsys, row_id):
    """The four snapshots of review round 1 that got a sidecar and hash files although the portal rejects them."""
    make, code = CONTENT[row_id]
    path = edition(raw=make())
    err = refused(capsys, cli(path, producer), code, path)
    assert es.PORTAL_REJECTS in err and es.CONTENT_HINTS[code] in err


def test_unreadable_content_gets_the_portal_command_catch_all_code(monkeypatch):
    def broken(_raw):
        raise KeyError("x")

    monkeypatch.setattr(es, "parse_reasoning", broken)
    with pytest.raises(es.SidecarError) as caught:
        es.check_snapshot(snapshot_bytes(base_snapshot()))
    assert caught.value.code == "acceptance_input_unavailable_or_invalid"


def test_a_snapshot_with_a_story_gets_a_sidecar(edition, producer, capsys):
    path = edition(story_snapshot())
    rc, _, err = run_main(capsys, *cli(path, producer))
    assert rc == 0, err
    assert path.with_name("v1.json.sidecar.json").exists()


def test_check_snapshot_accepts_the_synthetic_snapshot_and_its_dst_day():
    assert es.check_snapshot(snapshot_bytes(base_snapshot()))["topic_id"] == "test-topic"
    snap = base_snapshot()  # 2026-11-01: DST ends, a 25-hour local day
    snap.update(edition_date="2026-11-01", run_id="2026-11-01-test-topic-1", generated_at="2026-11-01T11:00:00Z",
                published_at=None, expires_at="2026-11-02T13:00:00Z",
                window={"start": "2026-10-31T09:30:00Z", "end": "2026-11-01T10:30:00Z"})
    assert es.check_snapshot(snapshot_bytes(snap))["edition_date"] == "2026-11-01"


# ---------------------------------------------------------------- parity with master's portal code


def portal_source(path: str) -> str:
    known = subprocess.run(["git", "rev-parse", "--verify", "-q", PORTAL_REF + "^{commit}"], cwd=REPO_ROOT,
                           capture_output=True)
    if known.returncode != 0:
        pytest.skip(f"{PORTAL_REF} is not in this clone: `git fetch origin` to check portal parity")
    shown = subprocess.run(["git", "show", f"{PORTAL_REF}:{path}"], cwd=REPO_ROOT, capture_output=True)
    assert shown.returncode == 0, SHAPE_CHANGED.format(what=f"{path} (it is gone)")
    return shown.stdout.decode("utf-8")


def find_function(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(SHAPE_CHANGED.format(what=f"function {name} (not found)"))


def module_namespace(source: str, filename: str, imported: dict | None = None) -> dict:
    """Executes a portal module's functions, classes and plain constants without Django, fcntl or jsonschema.

    Absolute imports that are missing here are skipped, relative imports are bound from `imported`, decorators
    (jsonschema format registrations) are dropped, and module constants that need a file or a schema are skipped.
    """
    ns: dict = {"__name__": "portal_under_test", **(imported or {})}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.level:
                continue
            try:
                exec(compile(ast.Module(body=[node], type_ignores=[]), filename, "exec"), ns)
            except ImportError:
                pass
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            node.decorator_list = []
            exec(compile(ast.Module(body=[node], type_ignores=[]), filename, "exec"), ns)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            try:
                exec(compile(ast.Module(body=[node], type_ignores=[]), filename, "exec"), ns)
            except Exception:  # needs the schema file or jsonschema; not part of the sidecar checks
                pass
    return ns


@pytest.fixture(scope="module")
def portal():
    validation_source = portal_source(VALIDATION)
    validation = module_namespace(validation_source, VALIDATION)
    imported = {name: validation[name] for name in
                ("MAX_BYTES", "SnapshotError", "require", "bounded_structure", "edition_date", "public_url")}
    preview_source = portal_source(PREVIEW)
    preview = module_namespace(preview_source, PREVIEW, imported)
    return SimpleNamespace(validation=validation, preview=preview, preview_tree=ast.parse(preview_source),
                           command_tree=ast.parse(portal_source(COMMAND)),
                           sources={PREVIEW: preview_source, VALIDATION: validation_source},
                           namespaces={PREVIEW: preview, VALIDATION: validation})


def portal_result(portal, raw: bytes) -> dict:
    """What present_reasoning hands bind_preview_sidecar: the parsed snapshot and preview.sha256/provisional."""
    sha256 = hashlib.sha256(raw).hexdigest()
    return {"reasoning": portal.preview["parse_reasoning"](raw),
            "preview": {"sha256": sha256, "provisional": True if sha256 == portal.preview["HISTORICAL_V3_SHA256"] else None}}


def test_parity_constants_match_the_portal(portal):
    assert es.MAX_BYTES == portal.validation["MAX_BYTES"]
    for name in ("HISTORICAL_V3_SHA256", "GENUINE_V4_SHA256"):
        assert getattr(es, name) == portal.preview[name], SHAPE_CHANGED.format(what=name)
    review = find_function(portal.preview_tree, "artifact_review_issues")
    held = {n.value for n in ast.walk(review) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert es.HELD_RUN_ID in held, SHAPE_CHANGED.format(what="artifact_review_issues")
    for sha256, run_id in ((es.GENUINE_V4_SHA256, "x"), ("0" * 64, es.HELD_RUN_ID), ("0" * 64, "2026-10-26-test-topic-1")):
        ours = sha256 == es.GENUINE_V4_SHA256 or run_id == es.HELD_RUN_ID
        assert bool(portal.preview["artifact_review_issues"](sha256, run_id)) is ours
    patterns = {n.value for fn in ("timestamp", "identifier", "bind_preview_sidecar")
                for n in ast.walk(find_function(portal.preview_tree, fn)) if isinstance(n, ast.Constant)}
    for ours in (es.TIMESTAMP, es.IDENTIFIER, es.CAPTURE):
        assert ours.pattern in patterns, SHAPE_CHANGED.format(what=f"the regex {ours.pattern}")
    bounded = find_function(ast.parse(portal_source(VALIDATION)), "bounded_structure")
    constants = {n.value for n in ast.walk(bounded) if isinstance(n, ast.Constant)}
    assert es.UNSAFE_CONTENT.pattern in constants and es.MAX_DEPTH in constants, \
        SHAPE_CHANGED.format(what="snapshot_validation.bounded_structure")


def test_parity_every_field_bind_preview_sidecar_reads_is_produced(portal, edition, producer):
    fn = find_function(portal.preview_tree, "bind_preview_sidecar")

    def keys_of(var: str) -> set:
        return {n.slice.value for n in ast.walk(fn) if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name)
                and n.value.id == var and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str)}

    loops = {c.value for n in ast.walk(fn) if isinstance(n, ast.For) and isinstance(n.iter, ast.Tuple)
             for c in n.iter.elts if isinstance(c, ast.Constant)}
    checked_top, checked_binding = keys_of("sidecar"), keys_of("binding") | loops
    # the portal's shape as of master 1444e7c; a change here means re-reading bind_preview_sidecar
    assert checked_top == {"snapshot", "provisional", "corpus_as_of_utc", "edition_window_utc"}, \
        SHAPE_CHANGED.format(what=f"bind_preview_sidecar (sidecar keys now {sorted(checked_top)})")
    assert checked_binding == {"sha256", "bytes", "topic_id", "edition_date", "version", "run_id", "status"}, \
        SHAPE_CHANGED.format(what=f"bind_preview_sidecar (snapshot keys now {sorted(checked_binding)})")
    source = ast.unparse(fn)
    assert "'sha256_file_bytes' in sidecar['snapshot']" in source, SHAPE_CHANGED.format(what="the closed-form switch")
    present = ast.unparse(find_function(portal.preview_tree, "present_reasoning"))
    assert "sha256=hashlib.sha256(raw).hexdigest()" in present and \
        "provisional=True if hashlib.sha256(raw).hexdigest() == HISTORICAL_V3_SHA256 else None" in present, \
        SHAPE_CHANGED.format(what="present_reasoning (preview.sha256 / preview.provisional)")
    sidecar = good_sidecar(edition(), producer)
    assert checked_top <= set(sidecar) and checked_binding <= set(sidecar["snapshot"])
    assert "sha256_file_bytes" not in sidecar["snapshot"]


def test_parity_the_portal_binding_accepts_our_sidecar(portal, edition, producer, capsys):
    path = edition()
    assert run_main(capsys, *cli(path, producer, corpus="2026-10-26T10:30Z"))[0] == 0
    raw, data = path.read_bytes(), path.with_name("v1.json.sidecar.json").read_bytes()
    result = portal.preview["bind_preview_sidecar"](data, raw, portal_result(portal, raw))
    assert result["preview"]["corpus_binding"] == {"provisional": True, "corpus_as_of_utc": "2026-10-26T09:30:00Z",
                                                   "sidecar_sha256": hashlib.sha256(data).hexdigest()}


@pytest.mark.parametrize("mutate, portal_rejects, snapshot", [(m, r, s) for _, m, _, r, s in SIDECAR_CASES],
                         ids=[i for i, *_ in SIDECAR_CASES])
def test_parity_sidecar_mutations_portal_binding_agrees(portal, edition, producer, mutate, portal_rejects, snapshot):
    """Where the portal's binding rejects, so do we; where only the command or our contract rejects, the binding passes."""
    path = edition(snapshot())
    raw = path.read_bytes()
    sidecar = good_sidecar(path, producer)
    mutate(sidecar)
    data = es.serialize(sidecar)
    with pytest.raises(es.SidecarError):
        es.validate_sidecar(data, path, producer.commit, producer.repo)
    if portal_rejects:
        with pytest.raises(portal.validation["SnapshotError"]):
            portal.preview["bind_preview_sidecar"](data, raw, portal_result(portal, raw))
    else:
        portal.preview["bind_preview_sidecar"](data, raw, portal_result(portal, raw))


@pytest.mark.parametrize("make, code", [(m, c) for _, m, c in SNAPSHOT_MUTATIONS], ids=[i for i, *_ in SNAPSHOT_MUTATIONS])
def test_parity_snapshot_envelope_codes_match_the_portal(portal, make, code):
    with pytest.raises(portal.validation["SnapshotError"]) as caught:
        portal.preview["parse_reasoning"](make())
    assert str(caught.value) == code


def test_parity_the_portal_accepts_the_synthetic_snapshot(portal):
    assert portal.preview["parse_reasoning"](snapshot_bytes(base_snapshot()))["run_id"] == "2026-10-26-test-topic-1"
    assert portal.preview["parse_reasoning"](snapshot_bytes(story_snapshot()))["stories"][0]["event_id"] == "ev-story-1"
    assert portal.preview["parse_reasoning"](snapshot_bytes(pre_cut_snapshot()))["generated_at"] == "2026-10-26T08:00:00Z"


@pytest.mark.parametrize("make, code", [(m, c) for _, m, c in CONTENT_MUTATIONS], ids=[i for i, *_ in CONTENT_MUTATIONS])
def test_parity_content_codes_match_the_portal(portal, make, code):
    with pytest.raises(portal.validation["SnapshotError"]) as caught:
        portal.preview["parse_reasoning"](make())
    assert str(caught.value) == code


def test_parity_the_portal_binding_accepts_the_sidecar_of_a_story_snapshot(portal, edition, producer, capsys):
    path = edition(story_snapshot())
    assert run_main(capsys, *cli(path, producer))[0] == 0
    raw, data = path.read_bytes(), path.with_name("v1.json.sidecar.json").read_bytes()
    portal.preview["bind_preview_sidecar"](data, raw, portal_result(portal, raw))


def portal_closure(portal) -> dict:
    """Every module-level name master's parse_reasoning reaches, resolved per module as Python resolves it.

    Returns {name: (kind, module, node or None)}, kind "def" (a function or class), "const" or "import"; the script
    holds them all in one namespace, so a def or constant name defined in both portal modules fails loudly.
    """
    trees = {module: ast.parse(source) for module, source in portal.sources.items()}
    defs = {m: {n.name: n for n in t.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))} for m, t in trees.items()}
    consts = {m: {target.id for n in t.body if isinstance(n, ast.Assign) for target in n.targets
                  if isinstance(target, ast.Name)} for m, t in trees.items()}
    relative = {m: {alias.asname or alias.name for n in t.body if isinstance(n, ast.ImportFrom) and n.level
                    and n.module == "snapshot_validation" for alias in n.names} for m, t in trees.items()}
    tables = {m: {child.get_name(): child for child in symtable.symtable(source, m, "exec").get_children()}
              for m, source in portal.sources.items()}

    def global_names(table) -> set:
        names = {s.get_name() for s in table.get_symbols() if s.is_global() and s.is_referenced()}
        for child in table.get_children():
            names |= global_names(child)
        return names

    def resolve(module: str, name: str):
        if name in defs[module]:
            return "def", module
        if name in consts[module]:
            return "const", module
        if name in relative[module]:
            return resolve(VALIDATION, name)
        return (None, None) if hasattr(builtins, name) else ("import", module)

    found: dict = {}
    todo = [(PREVIEW, "parse_reasoning")]
    while todo:
        module, name = todo.pop()
        kind, home = resolve(module, name)
        if kind is None:
            continue
        if name in found:
            same = found[name][1] == home or found[name][0] == kind == "import"  # e.g. `re` imported by both
            assert same, SHAPE_CHANGED.format(what=f"{name} (defined in both portal modules)")
            continue
        found[name] = (kind, home, defs[home][name] if kind == "def" else None)
        if kind == "def":
            todo.extend((home, n) for n in global_names(tables[home][name]))
    return found


def test_parity_the_portal_copy_is_verbatim(portal):
    """The script's portal copy is master's parse_reasoning and everything it calls, node for node."""
    closure = portal_closure(portal)
    ours = {n.name: n for n in ast.parse(SCRIPT.read_text(encoding="utf-8")).body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    assert {"parse_reasoning", "envelope", "quote_binding", "public_url", "bounded_structure"} <= set(closure)
    for name, (kind, module, node) in sorted(closure.items()):
        if kind == "def":
            theirs = copy.deepcopy(node)
            theirs.decorator_list = []  # jsonschema format registrations, not checks
            assert name in ours and ast.dump(ours[name]) == ast.dump(theirs), \
                SHAPE_CHANGED.format(what=f"{module} › {name} (copy it verbatim into the portal copy section)")
        elif kind == "const":
            assert getattr(es, name) == portal.namespaces[module][name], SHAPE_CHANGED.format(what=f"{module} › {name}")
        else:
            assert getattr(es, name) is portal.namespaces[module][name], \
                SHAPE_CHANGED.format(what=f"{module} › the import of {name}")


def test_parity_every_code_parse_reasoning_raises_is_exercised(portal):
    codes = {find_function(portal.preview_tree, "fail").args.defaults[0].value}
    for kind, _, node in portal_closure(portal).values():
        for call in ast.walk(node) if kind == "def" else ():
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
                continue
            position = {"fail": 1, "require": 1, "SnapshotError": 0}.get(call.func.id)
            if position is not None and len(call.args) > position and isinstance(call.args[position], ast.Constant):
                codes.add(call.args[position].value)
    covered = {code for *_, code in SNAPSHOT_MUTATIONS} | {code for *_, code in CONTENT_MUTATIONS}
    assert len(codes) > 30 and not codes - covered, \
        SHAPE_CHANGED.format(what=f"parse_reasoning (codes without a test: {sorted(codes - covered)})")


def command_handle(portal) -> ast.FunctionDef:
    return find_function(portal.command_tree, "handle")


def test_parity_reasoning_snapshot_checks_are_the_ones_mirrored(portal):
    handle = command_handle(portal)
    checks = {(ast.unparse(n.args[0]), n.args[1].value) for n in ast.walk(handle) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name) and n.func.id == "require" and isinstance(n.args[1], ast.Constant)}
    expected = {
        ("re.fullmatch('[0-9a-f]{64}', options[key])", "expected_full_sha256_required"),
        ("re.fullmatch('[0-9a-f]{40}', commit)", "expected_full_producer_commit_required"),
        ("hashlib.sha256(raw).hexdigest() == options['sha256']", "snapshot_sha256_mismatch"),
        ("hashlib.sha256(sidecar_raw).hexdigest() == options['sidecar_sha256']", "sidecar_sha256_mismatch"),
        ("p['provenance']['fictional'] is False and p['provenance']['model'] != 'stand-ins' and "
         "(p['provenance'].get('model_calls', 0) > 0)", "genuine_model_output_required"),
        ("prefix is not None and commit.startswith(prefix[1])", "producer_commit_mismatch"),
        ("isinstance(declared, str) and re.fullmatch('[0-9a-f]{64}', declared)", "invalid_config_sha256"),
        ("actual == declared", "producer_config_mismatch"),
        # closed form only (never produced here)
        ("isinstance(prefix, str) and re.fullmatch('[0-9a-f]{7,40}', prefix) and commit.startswith(prefix)",
         "producer_commit_mismatch"),
        ("declared == [report['git_config_sha256'], report['git_config_crlf_sha256']]", "producer_config_mismatch"),
    }
    assert checks == expected, SHAPE_CHANGED.format(what=f"{COMMAND} (require calls now {sorted(checks - expected)}, "
                                                         f"gone {sorted(expected - checks)})")
    producer_keys = {n.slice.value for n in ast.walk(handle) if isinstance(n, ast.Subscript)
                     and isinstance(n.value, ast.Name) and n.value.id == "producer" and isinstance(n.slice, ast.Constant)}
    assert producer_keys == {"commit", "config_sha256", "commit_of_the_publishing_process"}, \
        SHAPE_CHANGED.format(what=f"{COMMAND} (producer keys now {sorted(producer_keys)})")
    assert set(es.PRODUCER_KEYS) == producer_keys - {"commit_of_the_publishing_process"}
    source = ast.unparse(handle)
    assert "'commit_of_the_publishing_process' in producer" in source
    assert f"f'{{commit}}:{es.CONFIG_PATH}'" in source, SHAPE_CHANGED.format(what="the config path read with git show")
    assert "artifact_review_issues(options['sha256'], p['run_id'])" in source
    matches = {n.args[0].value for n in ast.walk(handle) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == "match" and n.args and isinstance(n.args[0], ast.Constant)}
    assert matches == {es.COMMIT_PREFIX.pattern}, SHAPE_CHANGED.format(what="the producer.commit prefix regex")
    assert es.FULL_COMMIT.pattern == "[0-9a-f]{40}" and es.SHA256.pattern == "[0-9a-f]{64}"


@pytest.mark.parametrize("provenance", [
    {"fictional": False, "model": "test-model", "model_calls": 3},
    {"fictional": True, "model": "test-model", "model_calls": 3},
    {"fictional": False, "model": "stand-ins", "model_calls": 3},
    {"fictional": False, "model": "test-model", "model_calls": 0},
    {"fictional": False, "model": "test-model"},
], ids=["genuine", "fictional", "stand-ins", "zero-calls", "no-count"])
def test_parity_genuine_output_rule_evaluates_like_the_portal(portal, provenance):
    handle = command_handle(portal)
    condition = next(n.args[0] for n in ast.walk(handle) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                     and n.func.id == "require" and isinstance(n.args[1], ast.Constant)
                     and n.args[1].value == "genuine_model_output_required")
    portal_ok = eval(compile(ast.Expression(body=condition), COMMAND, "eval"), {"p": {"provenance": provenance}})
    assert bool(portal_ok) is (es.genuine_problem({"provenance": provenance}) is None)


def test_parity_the_portal_producer_check_accepts_our_sidecar_and_repo(portal, edition, producer, tmp_path):
    """Runs the command's own non-closed producer statements (prefix, config hash via git show) on our sidecar."""
    handle = command_handle(portal)
    body = next(n for n in ast.walk(handle) if isinstance(n, ast.Try)).body
    start = next(i for i, n in enumerate(body) if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "prefix")
    end = next(i for i, n in enumerate(body) if i > start and "artifact_review_issues" in ast.unparse(n))
    statements = ast.Module(body=body[start:end], type_ignores=[])
    assert "report['metadata_valid'] = True" in ast.unparse(statements), SHAPE_CHANGED.format(what=COMMAND)
    code = compile(statements, COMMAND, "exec")

    def run(producer_block: dict, commit: str) -> dict:
        report: dict = {}
        ns = {"re": re, "hashlib": hashlib, "subprocess": subprocess, "Path": Path,
              "SnapshotError": portal.validation["SnapshotError"], "require": portal.validation["require"],
              "producer": producer_block, "commit": commit, "report": report,
              "__file__": str(producer.repo / "backend" / "portal" / "management" / "commands" / "x.py")}
        exec(code, ns)  # parents[4] of __file__ is the temporary producer repository
        return report

    sidecar = good_sidecar(edition(), producer)
    report = run(sidecar["producer"], producer.commit)
    assert report["metadata_valid"] is True and report["git_config_sha256"] == producer.config_sha256
    for bad, commit in (({**sidecar["producer"], "config_sha256": "0" * 64}, producer.commit),
                        ({**sidecar["producer"], "commit": "f" * 40}, producer.commit),
                        ({**sidecar["producer"], "commit": producer.no_config}, producer.no_config)):
        with pytest.raises(portal.validation["SnapshotError"]):
            run(bad, commit)
        with pytest.raises(es.SidecarError):
            es.validate_sidecar({**copy.deepcopy(sidecar), "producer": bad}, edition(), commit, producer.repo)
