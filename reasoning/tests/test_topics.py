"""Free-text topic → collection terms (`quorum_reasoning.topics`, owner's decision 2026-10-25, Issue #2
"topics are free text"). No credits and no network: `llm.json_task` is replaced or answered by the stand-in."""

from __future__ import annotations

import json

import pytest

from quorum_reasoning import dryrun, llm, topics

PHRASE = "climate policy and carbon tax"


@pytest.fixture
def no_route(monkeypatch):
    for var in ("MODEL_BASE_URL", "MODEL_API_KEY", "METERLESS_BASE_URL", "METERLESS_RUNTIME_TOKEN"):
        monkeypatch.setenv(var, "")
    monkeypatch.delenv("QUORUM_DRY_RUN", raising=False)


def _reply(**over):
    base = {
        "slug": "climate-policy-carbon-tax",
        "name": "Climate Policy and Carbon Tax",
        "terms": ["carbon tax", "carbon taxes", "emissions trading", "Paris Agreement", "NATO", "climate"],
        "notes": "misses stories that say 'carbon levy'",
    }
    base.update(over)
    return base


def _fake(monkeypatch, answer=None, exc=None):
    seen = {}

    def fake(task, payload, *, dry_run, which="default"):
        seen.update(task=task, payload=payload, dry_run=dry_run, which=which)
        if exc is not None:
            raise exc
        return answer

    monkeypatch.setattr(llm, "json_task", fake)
    return seen


# ---------------------------------------------------------------- validation ----


@pytest.mark.parametrize("slug", ["climate-policy", "carbon-tax-eu-2026", "a1-b2"])
def test_valid_slugs(slug):
    row, why = topics.validate(_reply(slug=slug))
    assert row is not None and row["slug"] == slug, why


@pytest.mark.parametrize("slug", ["climate", "Climate-Policy-x", "a-b-c-d-e", "climate_policy", "climate--policy", "-x-y", "", "клімат-політика"])
def test_invalid_slugs_are_rejected(slug):
    row, why = topics.validate(_reply(slug=slug))
    # "Climate-Policy-x" lowercases to a valid slug; every other one is invalid
    if slug == "Climate-Policy-x":
        assert row is not None and row["slug"] == "climate-policy-x"
    else:
        assert row is None and "slug" in why


def test_term_filtering_rules():
    kept, dropped = topics.clean_terms(
        ["Carbon Tax", "carbon tax", "the", "and of", "tax", "EPA", "epa", "US", "IT", "U.S.", "x", "a" * 41, "net-zero", "Zelenskyy's", "emissions; drop", 7, "EU tariffs"]
    )
    assert kept == ["carbon tax", "EPA", "net-zero", "zelenskyy's", "EU tariffs"]
    for bad in ("the", "and of", "tax", "epa", "US", "IT", "U.S.", "x", "emissions; drop", "7"):
        assert bad in dropped


def test_acronyms_stay_uppercase_other_words_lowercase():
    assert topics.normalize_term("NATO") == "NATO"
    assert topics.normalize_term("NATO Summit") == "NATO summit"
    assert topics.normalize_term("Paris Agreement") == "paris agreement"
    assert topics.normalize_term("Nato") == "nato"  # mixed case is a word, not an acronym


def test_terms_capped_and_deduplicated():
    kept, dropped = topics.clean_terms([f"term{i:02d}" for i in range(25)] + ["TERM00".lower()])
    assert len(kept) == topics.MAX_TERMS and len(set(kept)) == len(kept)
    assert "term24" in dropped


def test_plural_handling():
    assert topics.plural("policy") == "policies"
    assert topics.plural("carbon tax") == "carbon taxes"
    assert topics.plural("climate") == "climates"
    assert topics.plural("crash") == "crashes"
    assert topics.plural("process") == "processes"
    assert topics.plural("tariffs") is None  # already plural
    assert topics.plural("EU") is None
    row = topics.derive(PHRASE)
    for t in ("carbon tax", "carbon taxes", "climate policy", "climate policies", "policy", "policies"):
        assert t in row["terms"]
    assert "tax" not in row["terms"]  # a 3-letter word on its own over-matches


def test_derive_shapes():
    row = topics.derive(PHRASE)
    assert row["slug"] == "climate-policy-carbon-tax"
    assert row["name"] == "Climate Policy and Carbon Tax"
    assert topics.derive("Ukraine")["slug"] == "ukraine-news"
    assert topics.SLUG_RE.match(topics.derive("the and of")["slug"])
    assert topics.SLUG_RE.match(topics.derive("Війна в Україні")["slug"])
    biden = topics.derive("Biden's EU tariffs")
    assert biden["slug"] == "bidens-eu-tariffs" and biden["name"] == "Biden's EU Tariffs"
    assert biden["terms"] == ["biden EU tariffs", "biden", "bidens", "EU", "tariffs"]  # possessive stripped, "tariffs" not re-pluralised


# -------------------------------------------------------- suggest: model path ----


def test_model_reply_is_validated(monkeypatch):
    seen = _fake(monkeypatch, _reply(terms=["carbon tax", "tax", "NATO", "carbon tax", "US"]))
    row = topics.suggest(PHRASE, dry_run=True)
    assert seen["task"] == "topic_terms" and seen["which"] == "default" and seen["payload"] == {"phrase": PHRASE}
    assert row["source"] == "model" and row["terms"] == ["carbon tax", "NATO"]
    assert "tax" in row["dropped"] and "US" in row["dropped"]


def test_language_hint_reaches_the_payload(monkeypatch):
    seen = _fake(monkeypatch, _reply())
    topics.suggest("клімат", dry_run=True, language_hint="uk")
    assert seen["payload"] == {"phrase": "клімат", "language_hint": "uk"}


# -------------------------------------------------------------- fallback ----


@pytest.mark.parametrize("exc", [RuntimeError("route down"), ValueError("topic_terms: model did not return JSON"), llm.RateLimitAbort("r")])
def test_fallback_on_raising_json_task(monkeypatch, exc):
    _fake(monkeypatch, exc=exc)
    row = topics.suggest(PHRASE, dry_run=False)
    assert row["source"] == "fallback" and type(exc).__name__ in row["reason"]
    assert row["slug"] == "climate-policy-carbon-tax" and "carbon tax" in row["terms"]


@pytest.mark.parametrize(
    "answer, why",
    [
        (None, "not a JSON object"),
        (["x"], "not a JSON object"),
        (_reply(slug="Climate Policy"), "slug"),
        (_reply(name="  "), "name"),
        (_reply(terms=["the", "tax", "US"]), "no usable terms"),
        (_reply(terms="carbon tax"), "no usable terms"),
    ],
)
def test_fallback_on_invalid_reply(monkeypatch, answer, why):
    _fake(monkeypatch, answer)
    row = topics.suggest(PHRASE, dry_run=True)
    assert row["source"] == "fallback" and why in row["reason"]
    assert topics.SLUG_RE.match(row["slug"]) and row["terms"]


@pytest.mark.parametrize("phrase", ["", "   ", "the", "tax", "!!!", "x" * 500, "Війна в Україні", None, 42])
def test_suggest_never_raises(monkeypatch, phrase):
    _fake(monkeypatch, exc=RuntimeError("boom"))
    row = topics.suggest(phrase, dry_run=True)  # type: ignore[arg-type]
    assert row["source"] == "fallback" and topics.SLUG_RE.match(row["slug"])
    assert isinstance(row["terms"], list) and isinstance(row["name"], str)


# --------------------------------------------------------- dry-run stand-in ----


def test_dry_run_stand_in_path(no_route):
    assert llm.is_dry_run(False)
    row = topics.suggest(PHRASE)
    assert row["source"] == "model" and row["dry_run"] is True
    assert row["slug"] == "climate-policy-carbon-tax" and row["notes"].startswith("dry run:")
    assert dryrun.topic_terms({"phrase": PHRASE})["terms"] == row["terms"]


def test_env_flag_forces_dry(monkeypatch):
    monkeypatch.setenv("QUORUM_DRY_RUN", "1")
    monkeypatch.setenv("MODEL_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("MODEL_API_KEY", "placeholder")
    row = topics.suggest(PHRASE)
    assert row["dry_run"] is True and row["source"] == "model"


# --------------------------------------------------------------------- CLI ----


def test_cli_sql_escapes_apostrophes(monkeypatch, capsys):
    _fake(monkeypatch, _reply(name="O'Rourke's Border Plan", terms=["o'rourke", "O'Rourke's", "border wall"]))
    assert topics.main(["--suggest", "O'Rourke's border plan", "--sql", "--dry-run"]) == 0
    out = capsys.readouterr().out.strip()
    assert out == (
        "INSERT INTO topics (id, name, query_terms) VALUES ('climate-policy-carbon-tax', 'O''Rourke''s Border Plan', "
        "ARRAY['o''rourke', 'o''rourke''s', 'border wall']) ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, "
        "query_terms = EXCLUDED.query_terms;"
    )


def test_cli_json_and_readable(no_route, capsys):
    assert topics.main(["--suggest", PHRASE, "--json"]) == 0
    row = json.loads(capsys.readouterr().out)
    assert row["slug"] == "climate-policy-carbon-tax" and row["source"] == "model"
    assert topics.main(["--suggest", PHRASE, "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "slug:   climate-policy-carbon-tax" in out and "  - carbon tax" in out


def test_cli_exit_zero_on_fallback(monkeypatch, capsys):
    _fake(monkeypatch, exc=RuntimeError("down"))
    assert topics.main(["--suggest", PHRASE, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["source"] == "fallback"


def test_prompt_carries_injection_paragraph():
    from pathlib import Path

    prompts = Path(topics.__file__).parent / "prompts"
    last = lambda name: (prompts / name).read_text(encoding="utf-8").strip().splitlines()[-1]  # noqa: E731
    assert last("topic_terms.md") == last("stance.md")
    assert "EPA" in (prompts / "topic_terms.md").read_text(encoding="utf-8")
