"""Typed-topic intake (`quorum_reasoning.topics`, docs/DECISIONS.md › Daily editions for users): the request key shared
with the web app, input validation, reading existing topics through Zetaris, the matching and overlap rules, and the
`--from-requests` batch. No credits and no network: Zetaris is a fake runner or a JSON file, models are `derive` or a
fake `llm.json_task`; an autouse fixture fails any test that reaches the real Zetaris route."""

from __future__ import annotations

import json

import pytest

from quorum_reasoning import llm, topics
from quorum_reasoning.tools import corpus

# The rehearsal dump of 2026-10-26 as Zetaris returns it (query_terms is a string with SQL quotes), collection order.
ZETARIS_ROWS = [
    {"id": "russia-ukraine-war", "name": "Russia–Ukraine war and US aid", "query_terms": "'{Ukraine,Zelensky,Zelenskyy,Kyiv,Ukrainian}'"},
    {"id": "tariffs-trade-war-china", "name": "US Tariffs and Trade War with China",
     "query_terms": "'{tariff,tariffs,\"trade war\",\"trade wars\",\"china tariffs\",\"chinese tariffs\",\"section 301\",\"steel tariffs\","
                    "\"aluminum tariffs\",semiconductors,\"export controls\",\"trade deal\",\"trade deals\"}'"},
    {"id": "immigration-southern-border", "name": "Immigration Enforcement and the Southern Border",
     "query_terms": "'{immigration,immigrants,deportation,deportations,\"border security\",\"southern border\",\"border patrol\",\"border wall\","
                    "asylum,\"asylum seekers\",migrants,\"migrant caravans\",\"ICE raids\",\"customs and border protection\",\"immigration reform\"}'"},
    {"id": "ai-regulation-export-controls", "name": "AI Regulation and Chip Export Controls",
     "query_terms": "'{\"artificial intelligence\",\"AI regulation\",\"AI act\",\"AI safety\",\"chip export controls\",\"export controls\",\"AI chips\","
                    "\"nvidia chips\",\"AI executive order\",\"AI legislation\",\"frontier models\",\"data centers\",semiconductors}'"},
    {"id": "federal-budget-shutdown", "name": "Federal Budget and Government Shutdown",
     "query_terms": "'{\"government shutdown\",shutdown,appropriations,\"spending bill\",\"spending bills\",\"continuing resolution\",\"debt ceiling\","
                    "\"omnibus bill\",\"budget resolution\",\"federal budget\",\"defense spending\",\"funding bill\",\"fiscal year 2027\"}'"},
    {"id": "climate-policy", "name": "Climate policy",
     "query_terms": "'{climate,emissions,carbon,\"clean energy\",renewable,renewables,\"Paris Agreement\",\"net zero\",greenhouse,decarbonization}'"},
]


@pytest.fixture(autouse=True)
def no_real_zetaris(monkeypatch):
    def refuse(sql, limit):
        pytest.fail(f"a test reached the real Zetaris route: {sql}", pytrace=False)

    monkeypatch.setattr(corpus, "_run_sql", refuse)
    monkeypatch.delenv("ZETARIS_COLLECTION_DB", raising=False)
    monkeypatch.delenv("ZETARIS_COLLECTION_SCHEMA", raising=False)


@pytest.fixture
def existing():
    return [topics.normalise_topic(r) for r in ZETARIS_ROWS]


def dry(text):
    return {**topics.derive(text), "source": "derive"}


def resolve(texts, existing, **kw):
    entries = [t if isinstance(t, dict) else {"text": t, "count": 1} for t in texts]
    return topics.resolve_requests(entries, existing, propose=kw.pop("propose", dry), **kw)


# ---------------------------------------------------------------- request key ----


@pytest.mark.parametrize(
    "text, key",
    [
        ("war in Ukraine", "ukraine war"),
        ("Ukraine war", "ukraine war"),
        ("  UKRAINE   war!!! ", "ukraine war"),
        ("Russia–Ukraine war", "russia ukraine war"),
        ("russia-ukraine-war", "russia ukraine war"),
        ("U.S. tariffs on China!", "china tariffs us"),
        ("US tariffs on China", "china tariffs us"),
        ("Biden's EU tariffs", "biden eu tariffs"),
        ("Biden’s EU tariffs", "biden eu tariffs"),
        ("Café  Économie", "cafe economie"),
        ("Ｆｕｌｌｗｉｄｔｈ news", "fullwidth"),
        ("İstanbul", "istanbul"),
        ("war war WAR", "war"),
        ("e.g. net-zero", "eg net zero"),
        ("Fiscal year 2027", "2027 fiscal year"),
        ("the of and", ""),
        ("", ""),
        (None, ""),
        ("Війна в Україні", "в віина украіні"),
    ],
)
def test_request_key_contract(text, key):
    assert topics.request_key(text) == key


def test_request_key_is_idempotent_and_order_free():
    for text in ("measles outbreak in Texas", "Texas: measles outbreak", "Mars sample-return mission", "Війна в Україні"):
        key = topics.request_key(text)
        assert topics.request_key(key) == key
        assert key == " ".join(sorted(set(key.split())))
    assert topics.request_key("Texas: measles outbreak") == topics.request_key("measles outbreak in Texas")


def test_key_stopwords_are_small_and_keep_meaningful_words():
    assert len(topics.KEY_STOPWORDS) <= 25
    for word in ("us", "war", "ai", "not", "no"):
        assert word not in topics.KEY_STOPWORDS


# ---------------------------------------------------------------- validation ----


@pytest.mark.parametrize(
    "text, why, withheld",
    [
        (None, "not text", False),
        (42, "not text", False),
        ("", "empty", False),
        ("   \n\t ", "empty", False),
        ("https://example.com/news", "contains a URL", True),
        ("see example.com today", "contains a URL", True),
        ("www.example", "contains a URL", True),
        ("ftp://files", "contains a URL", True),
        ("write to someone@example.com", "contains an e-mail address", True),
        ("@elonmusk", "contains an @handle", True),
        ("news from (@bob)", "contains an @handle", True),
        ("call 555-123-4567", "contains a phone number", True),
        ("(555) 123 4567", "contains a phone number", True),
        ("+44 20 7946 0958", "contains a phone number", True),
        ("5551234567", "contains a phone number", True),
        ("dial 555.1234", "contains a phone number", True),
        ("<script>alert(1)</script>", "contains markup or control characters", False),
        ("bell\x07topic", "contains markup or control characters", False),
        ("x" * 81, "longer than 80 characters (81)", False),
        ("2026", "no letters", False),
        ("!!! ???", "no letters", False),
        ("the and of", "nothing left after normalising (only stopwords and punctuation)", False),
    ],
)
def test_rejections(text, why, withheld):
    assert topics.check_request(text) == (why, withheld)


@pytest.mark.parametrize(
    "text",
    ["war in Ukraine", "fiscal year 2026-2027", "Top 100 2026", "Boeing 737-800", "Node.js security flaw", "AT&T merger",
     "A.I. regulation", "S&P 500 crash", "U.S.-China trade", "Війна в Україні", "x" * 80, "COVID-19 in 2026"],
)
def test_acceptable_requests(text):
    assert topics.check_request(text) == ("", False)


def test_huge_input_is_not_scanned_and_is_withheld():
    why, withheld = topics.check_request("a " * 5000)
    assert why.startswith("longer than 80 characters") and withheld


# ----------------------------------------------------------- existing topics ----


@pytest.mark.parametrize(
    "value, terms",
    [
        ("'{Ukraine,Zelensky,\"trade war\"}'", ["Ukraine", "Zelensky", "trade war"]),
        ("{Ukraine, \"trade war\" ,NULL,\"NULL\"}", ["Ukraine", "trade war", "NULL"]),
        ("'{\"o''rourke\",\"say \\\"no\\\"\",\"back\\\\slash\"}'", ["o'rourke", 'say "no"', "back\\slash"]),
        ("{\"a,b\",c}", ["a,b", "c"]),
        ("{}", []),
        ("'{}'", []),
        ('["carbon tax", "EPA"]', ["carbon tax", "EPA"]),
        (["carbon tax", " EPA ", "", None], ["carbon tax", "EPA"]),
        ("carbon tax, EPA", ["carbon tax", "EPA"]),
        (None, []),
    ],
)
def test_parse_terms_shapes(value, terms):
    assert topics.parse_terms(value) == terms


def test_rehearsal_rows_parse(existing):
    assert [t["id"] for t in existing][:2] == ["russia-ukraine-war", "tariffs-trade-war-china"]
    assert existing[0]["name"] == "Russia–Ukraine war and US aid"  # names are kept as stored
    assert existing[0]["terms"] == ["Ukraine", "Zelensky", "Zelenskyy", "Kyiv", "Ukrainian"]
    assert "customs and border protection" in existing[2]["terms"] and "ICE raids" in existing[2]["terms"]
    assert all(t["active"] for t in existing) and len(existing[1]["terms"]) == 13


@pytest.mark.parametrize("value, active", [(None, True), (True, True), (False, False), ("t", True), ("f", False),
                                           ("false", False), ("TRUE", True), (0, False), (1, True)])
def test_active_values(value, active):
    assert topics.normalise_topic({"id": "a-b", "name": "A", "query_terms": "{x}", "active": value})["active"] is active


def test_normalise_topic_upper_case_columns_and_missing_id():
    row = topics.normalise_topic({"ID": "a-b", "NAME": "A  b", "QUERY_TERMS": "{x,y}"})
    assert row == {"id": "a-b", "name": "A b", "terms": ["x", "y"], "active": True, "created_at": None}
    assert topics.normalise_topic({"name": "no id"}) is None


def test_order_topics_by_created_at_then_id():
    rows = [{"id": "c", "created_at": "2026-10-25 06:57:39.7+00"}, {"id": "b", "created_at": "2026-10-25 06:26:43+00"},
            {"id": "a", "created_at": "2026-10-25 06:57:39.7+00"}]
    ordered, note = topics.order_topics(rows)
    assert [r["id"] for r in ordered] == ["b", "a", "c"] and note == "collection order: created_at, id"
    kept, note = topics.order_topics([{"id": "z", "created_at": None}, {"id": "y", "created_at": "2026-10-25"}])
    assert [r["id"] for r in kept] == ["z", "y"] and "order returned" in note


def test_read_topics_widest_query_first():
    seen = []

    def runner(sql, limit):
        seen.append((sql, limit))
        return [{**ZETARIS_ROWS[0], "active": "f", "created_at": "2026-10-25T06:26:43+00:00"}]

    found, note = topics.read_topics(runner)
    assert seen == [("SELECT id, name, query_terms, active, created_at FROM QUORUM_COLLECT.topics", topics.TOPIC_READ_LIMIT)]
    assert found[0]["active"] is False and "created_at, id" in note and "wider queries failed" not in note


def test_read_topics_falls_back_when_zetaris_lacks_columns(monkeypatch):
    """The rehearsal registration answers HTTP 400 for `active`/`created_at` (DECISION at _TOPIC_COLUMNS)."""
    monkeypatch.setenv("ZETARIS_COLLECTION_DB", "OTHER_DB")
    seen = []

    def runner(sql, limit):
        seen.append(sql)
        if "active" in sql:
            raise RuntimeError("Zetaris REST HTTP 400; body withheld")
        return ZETARIS_ROWS

    found, note = topics.read_topics(runner)
    assert seen == ["SELECT id, name, query_terms, active, created_at FROM OTHER_DB.topics",
                    "SELECT id, name, query_terms, active FROM OTHER_DB.topics", "SELECT id, name, query_terms FROM OTHER_DB.topics"]
    assert [t["id"] for t in found] == [r["id"] for r in ZETARIS_ROWS] and all(t["active"] for t in found)
    assert "`active` not exposed" in note and "order returned" in note and "HTTP 400" in note
    assert all(s.startswith("SELECT ") and ";" not in s for s in seen)


def test_read_topics_raises_when_nothing_works():
    def runner(sql, limit):
        raise RuntimeError("ZETARIS_API_KEY is missing from .env or .env.local")

    with pytest.raises(RuntimeError, match="cannot read existing topics"):
        topics.read_topics(runner)


def test_read_topics_uses_the_corpus_route_by_default(monkeypatch):
    monkeypatch.setattr(corpus, "_run_sql", lambda sql, limit: ZETARIS_ROWS[:1])
    found, _ = topics.read_topics()
    assert found[0]["id"] == "russia-ukraine-war"


# ---------------------------------------------------------------- overlap ----


@pytest.mark.parametrize(
    "term, other, rel",
    [
        ("Ukraine", "ukraine", "equal"),
        ("ukraine peace talks", "Ukraine", "contains"),
        ("china", "china tariffs", "contained_in"),
        ("war", "Warsaw", None),
        ("trade", "trader", None),
        ("net-zero", "net-zero target", "contained_in"),
        ("AI", "AI regulation", "contained_in"),
    ],
)
def test_term_relation(term, other, rel):
    assert topics.term_relation(term, other) == rel


# ----------------------------------------------------------------- matching ----


def test_same_words_as_a_name_or_slug_is_that_topic(existing):
    res = resolve(["Climate policy", "policy on climate", "Russia Ukraine war", "war, Russia, Ukraine"], existing)
    assert [(r["status"], r["topic_id"], r["match"]) for r in res] == [
        ("existing", "climate-policy", "name"), ("existing", "climate-policy", "name"),
        ("existing", "russia-ukraine-war", "slug"), ("existing", "russia-ukraine-war", "slug"),
    ]
    assert res[2]["name"] == "Russia–Ukraine war and US aid"  # the seed is reported, never re-proposed or overwritten


@pytest.mark.parametrize(
    "text, topic_id, term",
    [
        ("war in Ukraine", "russia-ukraine-war", "Ukraine"),
        ("immigration", "immigration-southern-border", "immigration"),
        ("tariffs on China", "tariffs-trade-war-china", "tariffs"),
        ("Ukraine peace talks", "russia-ukraine-war", "Ukraine"),
        ("export controls on chips", "tariffs-trade-war-china", "export controls"),  # the older of two topics wins, as in collection
    ],
)
def test_a_headline_collected_under_an_existing_topic_maps_to_it(existing, text, topic_id, term):
    (r,) = resolve([text], existing)
    assert (r["status"], r["topic_id"], r["match"]) == ("existing", topic_id, "headline")
    assert repr(term) in r["reason"] and r["terms"] == next(t["terms"] for t in existing if t["id"] == topic_id)


def test_new_topic_keeps_only_non_overlapping_terms(existing):
    (r,) = resolve(["Ukrainian refugees in Poland"], existing)  # "Ukrainian" alone would capture it; a phrase with Poland does not
    assert r["status"] == "existing"  # "Ukrainian" is a term of russia-ukraine-war
    (r,) = resolve(["refugee chess tournaments"], existing, propose=lambda t: {"slug": "refugee-chess", "name": "Refugee chess",
                                                                              "terms": ["refugee chess", "asylum seekers", "chess", "border wall art"],
                                                                              "source": "model"})
    assert r["status"] == "new" and r["terms"] == ["refugee chess", "chess"] and r["source"] == "model"
    assert {(c["term"], c["topic_id"], c["topic_term"], c["relation"]) for c in r["conflicts"]} == {
        ("asylum seekers", "immigration-southern-border", "asylum", "contains"),
        ("asylum seekers", "immigration-southern-border", "asylum seekers", "equal"),
        ("border wall art", "immigration-southern-border", "border wall", "contains"),
    }
    assert "2 overlapping dropped" in r["reason"]


def test_needs_review_when_every_term_overlaps(existing):
    (r,) = resolve(["AI"], existing)
    assert r["status"] == "needs_review" and r["terms"] == [] and r["topic_id"] == "ai-news"
    assert {c["topic_id"] for c in r["conflicts"]} == {"ai-regulation-export-controls"}
    assert "every proposed term overlaps" in r["reason"]


def test_needs_review_when_the_kept_terms_miss_the_request_itself(existing):
    (r,) = resolve(["China"], existing)
    assert r["status"] == "needs_review" and r["terms"] == ["chinas"]
    assert r["conflicts"] == [{"term": "china", "topic_id": "tariffs-trade-war-china", "topic_term": "china tariffs", "relation": "contained_in"}]


def test_truly_new_topics(existing):
    res = resolve(["Mars sample return mission", "measles outbreak Texas", "Gaza ceasefire"], existing)
    assert [(r["status"], r["topic_id"], r["order"]) for r in res] == [
        ("new", "mars-sample-return-mission", 1), ("new", "measles-outbreak-texas", 2), ("new", "gaza-ceasefire", 3)]
    assert all(r["conflicts"] == [] and r["source"] == "derive" for r in res)
    assert "measles outbreak texas" in res[1]["terms"]


def test_retired_topics(existing):
    retired = existing + [topics.normalise_topic({"id": "measles-news", "name": "Measles", "query_terms": "{measles}", "active": "f"})]
    (same,) = resolve(["Measles"], retired)
    assert same["status"] == "needs_review" and same["topic_id"] == "measles-news" and "retired topic" in same["reason"]
    (other,) = resolve(["measles cases"], retired)  # a retired topic captures nothing and blocks no term
    assert other["status"] == "new" and other["conflicts"] == [] and "measles" in other["terms"]
    (reused,) = resolve(["measles cases"], retired, propose=lambda t: {"slug": "measles-news", "name": t, "terms": ["measles cases"]})
    assert reused["status"] == "new" and reused["topic_id"] == "measles-news-2"  # its id is never reused


def test_taken_slug_gets_a_suffix(existing):
    # slug_for drops "during" (a term stopword) but the key keeps it: same slug, different words
    taken = existing + [topics.normalise_topic({"id": "measles-winter", "name": "Winter measles", "query_terms": "{flu}"})]
    (r,) = resolve(["measles during winter"], taken)
    assert topics.request_key("measles during winter") != topics.request_key("measles-winter")
    assert r["status"] == "new" and r["topic_id"] == "measles-winter-2"
    res = resolve(["measles cases", "measles case counts"], existing,
                  propose=lambda t: {"slug": "measles-cases", "name": t, "terms": [t.lower()]})
    assert [(x["status"], x["topic_id"]) for x in res] == [("new", "measles-cases"), ("new", "measles-cases-2")]


def test_same_key_is_resolved_once_and_shared(existing):
    calls = []

    def propose(text):
        calls.append(text)
        return dry(text)

    res = resolve([{"text": "measles outbreak Texas", "count": 6}, {"text": "Measles outbreak in Texas", "count": 2},
                   {"text": "Texas: measles outbreak", "count": 1}], existing, propose=propose)
    assert calls == ["measles outbreak Texas"]
    assert {r["topic_id"] for r in res} == {"measles-outbreak-texas"} and {r["status"] for r in res} == {"new"}
    assert [r["index"] for r in res] == [0, 1, 2] and [r["count"] for r in res] == [6, 2, 1]


def test_later_requests_match_new_rows_of_the_batch_and_count_sets_the_order(existing):
    res = resolve([{"text": "measles vaccine exemptions", "count": 1}, {"text": "measles outbreak Texas", "count": 6}], existing)
    first, second = res
    assert second["status"] == "new" and second["order"] == 1
    assert (first["status"], first["topic_id"], first["match"]) == ("existing", "measles-outbreak-texas", "headline")
    assert "a new row of this batch" in first["reason"]


def test_model_call_cap_defers_the_rest(existing):
    calls = []

    def propose(text):
        calls.append(text)
        return dry(text)

    res = resolve([{"text": "Mars sample return mission", "count": 3}, {"text": "Gaza ceasefire", "count": 2}], existing,
                  propose=propose, max_proposals=1)
    assert calls == ["Mars sample return mission"]
    assert res[0]["status"] == "new" and res[1]["status"] == "needs_review" and res[1]["reason"].startswith("deferred:")


def test_rejected_entries_and_withheld_personal_data(existing):
    calls = []
    res = topics.resolve_requests(
        [{"key": "com example someone", "text": "write to someone@example.com", "count": 1}, "not an object",
         {"text": "y" * 120}, {"text": "", "count": "many"}, {"count": 3}],
        existing, propose=lambda t: calls.append(t) or dry(t))
    assert [r["status"] for r in res] == ["rejected"] * 5 and calls == []
    assert res[0]["text"] == res[0]["key"] == topics.WITHHELD and res[0]["reason"] == "contains an e-mail address"
    assert res[1]["reason"] == "entry is not an object" and res[1]["text"] is None
    assert res[2]["text"] == "y" * 80 + "…" and res[2]["reason"] == "longer than 80 characters (120)"
    assert res[3]["count"] == 1 and res[3]["reason"] == "empty" and res[4]["reason"] == "not text"


def test_mapping_shape_and_key_mismatch(existing):
    res = topics.resolve_requests([{"key": "gaza ceasefire", "text": "Gaza ceasefire", "count": 2},
                                   {"key": "ukraine war", "text": "war in Ukraine", "count": 1}], existing, propose=dry)
    for r in res:
        assert tuple(r) == topics.MAPPING_FIELDS and r["status"] in topics.INTAKE_STATUSES
    assert res[0]["key"] == "gaza ceasefire" and res[0]["key_mismatch"] == "ceasefire gaza"
    assert res[1]["key"] == "ukraine war" and res[1]["key_mismatch"] is None
    json.dumps(res)  # serialisable as is


def test_existing_and_rejected_never_call_the_model(existing):
    def boom(text):
        raise AssertionError(f"propose called for {text!r}")

    res = resolve(["war in Ukraine", "Climate policy", "https://x.com", ""], existing, propose=boom)
    assert [r["status"] for r in res] == ["existing", "existing", "rejected", "rejected"]


# ------------------------------------------------------------------ outputs ----


def test_rows_sql_is_insert_only_in_collection_order(existing):
    res = resolve([{"text": "Gaza ceasefire", "count": 1}, {"text": "measles outbreak Texas", "count": 5},
                   {"text": "Measles outbreak in Texas", "count": 2}, {"text": "war in Ukraine", "count": 9}], existing)
    sql = topics.rows_sql(res, header="test")
    inserts = [line for line in sql.splitlines() if line.startswith("INSERT")]
    assert len(inserts) == 2 and "'measles-outbreak-texas'" in inserts[0] and "'gaza-ceasefire'" in inserts[1]
    assert all(line.endswith("ON CONFLICT (id) DO NOTHING RETURNING id;") for line in inserts)
    statements = [line for line in sql.splitlines() if line and not line.startswith("--")]
    assert statements == inserts  # comments and inserts only: no BEGIN/COMMIT, no UPDATE
    assert "DO UPDATE" not in sql and "russia-ukraine-war" not in sql
    assert "-- 1. Measles Outbreak Texas (requests: 7)" in sql and "autocommit" in sql and "older one" in sql
    assert "no new topics" in topics.rows_sql(resolve(["war in Ukraine"], existing))


# ---------------------------------------------------------------------- CLI ----


def _write(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


SAMPLE = [
    {"key": "ukraine war", "text": "war in Ukraine", "count": 7},
    {"key": "immigration", "text": "immigration", "count": 5},
    {"key": "mars mission return sample", "text": "Mars sample return mission", "count": 3},
    {"key": "ai", "text": "AI", "count": 2},
    {"key": "com example news", "text": "https://example.com/news", "count": 1},
]


def test_cli_dry_run_batch_writes_three_files(tmp_path, monkeypatch, capsys):
    def no_model(*a, **k):
        raise AssertionError("--dry-run made a model call")

    monkeypatch.setattr(llm, "json_task", no_model)
    out = tmp_path / "out"
    code = topics.main(["--from-requests", _write(tmp_path, "req.json", SAMPLE), "--out", str(out), "--dry-run",
                        "--existing", _write(tmp_path, "topics.json", ZETARIS_ROWS)])
    assert code == 0
    mapping = json.loads((out / "mapping.json").read_text(encoding="utf-8"))
    assert [m["status"] for m in mapping] == ["existing", "existing", "new", "needs_review", "rejected"]
    assert mapping[0]["topic_id"] == "russia-ukraine-war" and mapping[4]["text"] == topics.WITHHELD
    sql = (out / "rows.sql").read_text(encoding="utf-8")
    assert sql.count("INSERT INTO topics") == 1 and "'mars-sample-return-mission'" in sql and "DO NOTHING RETURNING id" in sql
    report = (out / "report.txt").read_text(encoding="utf-8")
    assert "existing 2, new 1, needs_review 1, rejected 1" in report and "dry run (derive, no model call)" in report
    assert "example.com" not in report and "example.com" not in json.dumps(mapping)
    assert "status:" in capsys.readouterr().out


def test_cli_live_batch_uses_suggest(tmp_path, monkeypatch):
    seen = []

    def fake(task, payload, *, dry_run, which="default"):
        seen.append((task, payload["phrase"], dry_run))
        return {"slug": "mars-sample-return", "name": "Mars Sample Return", "terms": ["Mars sample return", "MSR", "Perseverance"], "notes": "n"}

    monkeypatch.setattr(llm, "json_task", fake)
    monkeypatch.setenv("QUORUM_DRY_RUN", "1")  # even so: the stand-in path must go through suggest
    out = tmp_path / "out"
    assert topics.main(["--from-requests", _write(tmp_path, "req.json", SAMPLE[2:3]), "--out", str(out),
                        "--existing", _write(tmp_path, "topics.json", ZETARIS_ROWS)]) == 0
    (m,) = json.loads((out / "mapping.json").read_text(encoding="utf-8"))
    assert seen == [("topic_terms", "Mars sample return mission", True)]
    assert m["status"] == "new" and m["source"] == "model" and m["topic_id"] == "mars-sample-return"
    assert m["terms"] == ["mars sample return", "MSR", "perseverance"]
    assert "live (suggest" in (out / "report.txt").read_text(encoding="utf-8")


def test_cli_reads_zetaris_when_no_file_is_given(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, "_run_sql", lambda sql, limit: ZETARIS_ROWS)
    out = tmp_path / "out"
    assert topics.main(["--from-requests", _write(tmp_path, "req.json", SAMPLE[:1]), "--out", str(out), "--dry-run"]) == 0
    assert "Zetaris QUORUM_COLLECT.topics" in (out / "report.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("payload", ["not json at all", json.dumps({"text": "x"})])
def test_cli_bad_request_file_exits_2(tmp_path, payload):
    path = tmp_path / "req.json"
    path.write_text(payload, encoding="utf-8")
    out = tmp_path / "out"
    assert topics.main(["--from-requests", str(path), "--out", str(out), "--dry-run", "--existing", _write(tmp_path, "t.json", [])]) == 2
    assert not out.exists()


def test_cli_without_existing_topics_writes_nothing(tmp_path, monkeypatch, capsys):
    def down(sql, limit):
        raise RuntimeError("Zetaris REST HTTP 503; body withheld")

    monkeypatch.setattr(corpus, "_run_sql", down)
    out = tmp_path / "out"
    assert topics.main(["--from-requests", _write(tmp_path, "req.json", SAMPLE), "--out", str(out), "--dry-run"]) == 2
    assert not out.exists() and "nothing written" in capsys.readouterr().err
    assert topics.main(["--from-requests", _write(tmp_path, "req.json", SAMPLE), "--out", str(out), "--dry-run",
                        "--existing", _write(tmp_path, "t.json", {"not": "a list"})]) == 2


def test_cli_argument_rules(tmp_path):
    with pytest.raises(SystemExit) as exc:
        topics.main(["--from-requests", "x.json"])  # --out is required for a batch
    assert exc.value.code == 2
    with pytest.raises(SystemExit):
        topics.main(["--from-requests", "x.json", "--suggest", "y", "--out", str(tmp_path)])
    with pytest.raises(SystemExit):
        topics.main([])
