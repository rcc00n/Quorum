"""Typed-topic intake (`quorum_reasoning.topics`, docs/DECISIONS.md › Daily editions for users): the request key shared
with the web app, input validation, reading existing topics through Zetaris, the matching and overlap rules, and the
`--from-requests` batch. No credits and no network: Zetaris is a fake runner or a JSON file, models are `derive` or a
fake `llm.json_task`; an autouse fixture fails any test that reaches the real Zetaris route."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

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


KEY_VECTORS = [
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
    ("𝐁𝐫𝐞𝐱𝐢𝐭", "brexit"),  # mathematical bold: no lowercase until NFKD makes it ASCII, hence the second lowercase
    ("ℍ", "h"),
    ("Ukr\u00adaine war", "ukraine war"),  # soft hyphen (Cf) deleted, not a separator
    ("Ukr\u200baine war", "ukraine war"),  # zero-width space
    ("\u202eevil topic", "evil topic"),  # right-to-left override
    ("\ufeffClimate", "climate"),  # BOM
]


@pytest.mark.parametrize("text, key", KEY_VECTORS)
def test_request_key_contract(text, key):
    assert topics.request_key(text) == key


def _js_twin() -> str:
    doc = topics.request_key.__doc__
    start = doc.index("const STOP")
    end = doc.index('.join(" ");', start) + len('.join(" ");')
    return "\n".join(line.strip() for line in doc[start:end].splitlines())


def test_js_twin_in_the_source_is_the_javascript_to_copy():
    """The docstring is raw, so the source file shows `\\p{M}`, not `\\\\p{M}` (a regex SyntaxError in JavaScript)."""
    src = Path(topics.__file__).read_text(encoding="utf-8")
    twin = _js_twin()
    flat = "\n".join(line.strip() for line in src.splitlines())
    assert twin in flat and "\\\\" not in twin
    for piece in (r"/\p{Cf}/gu", r"/\p{M}/gu", r"/(?<=\p{L})\.(?=\p{L})/gu", r"/[\p{L}\p{N}]+/gu"):
        assert piece in twin


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_js_twin_matches_request_key(tmp_path):
    texts = [t for t, _ in KEY_VECTORS] + ["Texas: measles outbreak", "U.S.-China trade", "A.I. regulation", "COVID-19 in 2026",
                                           "\uff2d\uff49\uff58\uff45\uff44\u3000width", "na\u00efve caf\u00e9", "e.g.,x", "a.b.c", "\u1f48\u03b4\u03c5\u03c3\u03c3\u03b5\u03cd\u03c2"]
    (tmp_path / "vectors.json").write_text(json.dumps(texts), encoding="utf-8")
    script = tmp_path / "twin.js"
    script.write_text(_js_twin() + "\nconst fs = require('fs');\n"
                      "const texts = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));\n"
                      "process.stdout.write(JSON.stringify(texts.map(requestKey)));\n", encoding="utf-8")
    done = subprocess.run([shutil.which("node"), str(script), str(tmp_path / "vectors.json")], capture_output=True, timeout=60)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert json.loads(done.stdout.decode("utf-8")) == [topics.request_key(t) for t in texts]


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
        # any "@": an e-mail address needs no dotted domain, every other "@" is a handle
        ("contact jane.doe@gmail", "contains an e-mail address", True),
        ("john@localhost", "contains an e-mail address", True),
        ("someone\u200b@example.com", "contains an e-mail address", True),  # a zero-width space hides nothing
        ("a @ b", "contains an @handle", True),
        ("news \uff20bob", "contains an @handle", True),  # full-width "@", scanned in NFKC form
        # dotted names with a common TLD or a path
        ("janedoe.blog", "contains a URL", True),
        ("my site janedoe.shop", "contains a URL", True),
        ("mysite.store sale", "contains a URL", True),
        ("janedoe.foo/post", "contains a URL", True),
        # C1 controls, private use, unpaired surrogates, unassigned code points
        ("x\x85y topic", "contains markup or control characters", False),
        ("topic \x9b", "contains markup or control characters", False),
        ("\ue000 topic", "contains private-use, unpaired surrogate or unassigned characters", False),
        ("\ud800 topic", "contains private-use, unpaired surrogate or unassigned characters", False),
        ("\u0378 topic", "contains private-use, unpaired surrogate or unassigned characters", False),
        ("\u00ad\u200b", "empty", False),  # only format characters
    ],
)
def test_rejections(text, why, withheld):
    assert topics.check_request(text) == (why, withheld)


@pytest.mark.parametrize(
    "text",
    ["war in Ukraine", "fiscal year 2026-2027", "Top 100 2026", "Boeing 737-800", "Node.js security flaw", "AT&T merger",
     "A.I. regulation", "S&P 500 crash", "U.S.-China trade", "Війна в Україні", "x" * 80, "COVID-19 in 2026",
     "Ukr\u00adaine war", "\u202eevil topic", "x" * 80 + "\u00ad\u200b"],
)
def test_acceptable_requests(text):
    assert topics.check_request(text) == ("", False)


def test_format_characters_are_deleted_before_keying_and_naming(existing):
    soft, bidi = resolve(["Ukr\u00adaine war", "\u202eevil topic"], existing)
    assert (soft["status"], soft["topic_id"], soft["text"]) == ("existing", "russia-ukraine-war", "Ukraine war")
    assert soft["key"] == topics.request_key("Ukraine war")
    assert bidi["status"] == "new" and bidi["name"] == "Evil Topic" and bidi["text"] == "evil topic"
    assert all("\u202e" not in t for t in bidi["terms"])


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
        ("Zelensky", "russia-ukraine-war", "Zelensky"),
        ("Ukrainian war", "russia-ukraine-war", "Ukrainian"),  # "war" is in the slug, "Ukrainian" is the matching term
        ("export controls", "tariffs-trade-war-china", "export controls"),  # the older of two covering topics wins, as in collection
        ("AI chips export controls", "ai-regulation-export-controls", "export controls"),  # the older topic lacks "AI chips"
    ],
)
def test_a_headline_collected_under_an_existing_topic_maps_to_it(existing, text, topic_id, term):
    (r,) = resolve([text], existing)
    assert (r["status"], r["topic_id"], r["match"]) == ("existing", topic_id, "headline")
    assert repr(term) in r["reason"] and r["terms"] == next(t["terms"] for t in existing if t["id"] == topic_id)
    assert "every word of the request is in its name, slug or matching terms" in r["reason"]


@pytest.mark.parametrize(
    "text, topic_id, term",
    [
        ("nuclear plant shutdown in Germany", "federal-budget-shutdown", "shutdown"),
        ("Julian Assange asylum", "immigration-southern-border", "asylum"),
        ("carbon monoxide poisoning", "climate-policy", "carbon"),
        ("carbon fiber bicycles", "climate-policy", "carbon"),
        ("climate of fear in Hollywood", "climate-policy", "climate"),
        ("Ukrainian cuisine", "russia-ukraine-war", "Ukrainian"),
        ("Kyiv ballet tour", "russia-ukraine-war", "Kyiv"),
        ("Ukraine peace talks", "russia-ukraine-war", "Ukraine"),
        ("data centers water use", "ai-regulation-export-controls", "data centers"),
        ("semiconductors in cars", "tariffs-trade-war-china", "semiconductors"),
    ],
)
def test_one_shared_term_does_not_make_a_request_existing(existing, text, topic_id, term):
    """A headline hit maps to that topic only when every word of the request is in its name, slug or matching terms."""
    (r,) = resolve([text], existing)
    assert (r["status"], r["match"]) == ("new", None) and r["topic_id"] not in {t["id"] for t in existing}
    assert f"also matches {term!r} of {topic_id}" in r["reason"]
    assert term.lower() not in {t.lower() for t in r["terms"]} and topic_id in {c["topic_id"] for c in r["conflicts"]}


def test_shared_terms_with_new_rows_of_the_batch_do_not_make_requests_existing(existing):
    res = resolve([{"text": "Mars sample return mission", "count": 3}, {"text": "Taylor Swift tour", "count": 3},
                   "Tax return deadline", "Tour de France doping", "Swift banking sanctions"], existing)
    assert [(r["status"], r["topic_id"]) for r in res] == [
        ("new", "mars-sample-return-mission"), ("new", "taylor-swift-tour"), ("new", "tax-return-deadline"),
        ("new", "tour-de-france-doping"), ("new", "swift-banking-sanctions")]
    assert "also matches 'return' of mars-sample-return-mission" in res[2]["reason"]
    assert "return" not in res[2]["terms"] and "swift" not in res[4]["terms"]


def test_new_topic_keeps_only_non_overlapping_terms(existing):
    (r,) = resolve(["Ukrainian refugees in Poland"], existing)  # "Ukrainian" is a term of russia-ukraine-war; Poland is not
    assert r["status"] == "new" and "ukrainian" not in [t.lower() for t in r["terms"]] and "poland" in r["terms"]
    assert ("ukrainian", "russia-ukraine-war", "equal") in {(c["term"], c["topic_id"], c["relation"]) for c in r["conflicts"]}
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
    assert r["reason"] == ("the terms that would collect a headline saying 'China' ('china') overlap older topics, "
                           "and none of the kept terms would")


def model_row(terms, slug=None):
    """A live-shaped proposal: what `suggest` returns for a validated model reply."""
    return lambda text: {"slug": slug or topics.slug_for(text), "name": text, "terms": list(terms), "source": "model"}


@pytest.mark.parametrize(
    "text, terms",
    [
        ("Wahlen in Deutschland", ["German election", "Bundestag", "Friedrich Merz", "CDU", "German elections"]),
        ("Выборы в Молдове", ["Moldova election", "Moldovan election", "Maia Sandu", "PAS", "Chisinau"]),
        ("the Fed raising rates", ["Federal Reserve", "interest rates", "rate hike", "rate hikes", "FOMC"]),
    ],
)
def test_terms_that_translate_or_paraphrase_the_request_are_new(existing, text, terms):
    """No term overlaps anything, so the typed words need not occur in a kept term (prompts/topic_terms.md: English
    terms even for a phrase in another language)."""
    (r,) = resolve([text], existing, propose=model_row(terms))
    assert (r["status"], r["conflicts"], r["source"]) == ("new", [], "model")
    assert r["terms"] == [topics.normalize_term(t) for t in terms] and topics._COLLECTION_ID.match(r["topic_id"])


def test_overlap_that_spares_the_typed_words_still_gives_a_new_row(existing):
    # "border wall art" overlaps "border wall" but does not occur in the typed text: the paraphrases stay
    (r,) = resolve(["murals on the Mexican frontier"], existing,
                   propose=model_row(["border wall art", "border murals", "frontier murals"]))
    assert r["status"] == "new" and r["terms"] == ["border murals", "frontier murals"]


@pytest.mark.parametrize("text", ["us", "it", "who", "May", "WHO", "IS"])
def test_a_row_whose_only_terms_are_too_generic_is_needs_review(existing, text):
    (r,) = resolve([text], existing)
    assert r["status"] == "needs_review" and r["terms"] == [] and r["reason"].startswith("terms too generic to collect: ")
    assert topics.rows_sql([r]).count("INSERT") == 0


def test_generic_rows_never_capture_later_requests(existing):
    res = resolve([{"text": "WHO", "count": 3}, {"text": "US", "count": 2}, "Who will win the Senate", "Join us for the Super Bowl"],
                  existing)
    assert [r["status"] for r in res] == ["needs_review", "needs_review", "new", "new"]
    assert all(r["match"] is None for r in res)
    sql = topics.rows_sql(res)
    assert "'who'" not in sql and "'us'" not in sql and sql.count("INSERT") == 2


def test_generic_terms_are_dropped_from_a_row_that_has_others(existing):
    (r,) = resolve(["measles cases"], existing, propose=model_row(["measles cases", "it", "may"]))
    assert r["status"] == "new" and r["terms"] == ["measles cases"] and "too generic, dropped: 'it', 'may'" in r["reason"]


def test_a_row_with_no_term_at_all_is_needs_review(existing):
    (r,) = resolve(["Gaza ceasefire"], existing, propose=model_row([]))
    assert r["status"] == "needs_review" and r["reason"] == "no usable term could be derived from the phrase"
    (r,) = resolve(["x" * 70], existing)  # every candidate is over 40 characters
    assert r["status"] == "needs_review" and r["reason"] == "no usable term could be derived from the phrase"
    assert r["topic_id"].startswith("topic-") and topics._COLLECTION_ID.match(r["topic_id"])


def test_a_phrase_of_short_words_is_kept_whole():
    assert topics.derive("Me Too")["terms"] == ["me too"]  # a valid term as a whole, though no word of it is significant
    assert topics.derive("tax")["terms"] == ["tax"]  # not a valid term: kept as typed, and the intake calls it too generic


def test_me_too_is_a_new_topic(existing):
    (r,) = resolve(["Me Too"], existing)
    assert r["status"] == "new" and r["terms"] == ["me too"]


@pytest.mark.parametrize(
    "text, topic_id",
    [
        ("counterintelligence telecommunications infrastructure investigations", "counterintelligence-telecommunications-infrastructure"),
        ("Bundesverfassungsgerichtsentscheidung Klimaschutzgesetz Verfassungsbeschwerde",
         "bundesverfassungsgerichtsentscheidung-klimaschutzgesetz"),
        ("pneumonoultramicroscopicsilicovolcanoconiosis outbreak hospitalizations",
         "pneumonoultramicroscopicsilicovolcanoconiosis-outbreak"),
    ],
)
def test_long_ids_are_cut_at_a_hyphen_to_fit_collections_rule(existing, text, topic_id):
    (r,) = resolve([text], existing)
    assert r["status"] == "new" and r["topic_id"] == topic_id and len(topic_id) <= topics.ID_BASE_MAX
    ids = re.findall(r"VALUES \('([^']*)'", topics.rows_sql([r]))
    assert ids == [topic_id] and all(topics._COLLECTION_ID.match(i) for i in ids)


def test_id_base_rules():
    assert topics._id_base("x" * 70 + "-news").startswith("topic-")  # one long word: no hyphen to cut at
    long_model_slug = "a" * 30 + "-" + "b" * 30 + "-" + "c" * 30  # passes SLUG_RE, which has no length cap
    assert topics.SLUG_RE.match(long_model_slug) and topics._id_base(long_model_slug) == "a" * 30
    assert topics._id_base("b" * 60) == "b" * 60 and topics._id_base("").startswith("topic-")
    full = "c" * 60
    taken = {full} | {f"{full}-{n}" for n in range(2, 999)}
    assert topics._free_slug(full, taken) == f"{full}-999" and topics._COLLECTION_ID.match(f"{full}-999")


def test_rows_sql_refuses_an_id_collection_would_reject():
    bad = {"status": "new", "order": 1, "topic_id": "x" * 65, "name": "X", "terms": ["xylophone"], "count": 1}
    with pytest.raises(ValueError, match="breaks collection's id rule"):
        topics.rows_sql([bad])


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
    res = resolve([{"text": "measles in Texas", "count": 1}, {"text": "measles outbreak Texas", "count": 6},
                   {"text": "measles vaccine exemptions", "count": 1}], existing)
    first, second, third = res
    assert second["status"] == "new" and second["order"] == 1
    assert (first["status"], first["topic_id"], first["match"]) == ("existing", "measles-outbreak-texas", "headline")
    assert "a new row of this batch" in first["reason"]
    # "vaccine exemptions" is in no name, slug or term of the batch row: a row of its own, without the shared "measles"
    assert (third["status"], third["topic_id"], third["order"]) == ("new", "measles-vaccine-exemptions", 2)
    assert "measles" not in third["terms"] and "also matches 'measles' of measles-outbreak-texas" in third["reason"]


def test_terms_overlapping_an_earlier_row_of_the_batch_are_dropped(existing):
    """The overlap rule checks this batch's new rows too (docs/DECISIONS.md › Daily editions for users)."""
    proposals = {"measles cases": ["measles cases"], "vaccine exemptions in Texas": ["measles cases texas", "vaccine exemptions"]}
    res = resolve([{"text": "measles cases", "count": 2}, "vaccine exemptions in Texas"], existing,
                  propose=lambda t: {"slug": topics.slug_for(t), "name": t, "terms": proposals[t], "source": "model"})
    first, second = res
    assert (first["status"], first["topic_id"]) == ("new", "measles-cases") and second["match"] is None
    assert second["status"] == "new" and second["terms"] == ["vaccine exemptions"]
    assert second["conflicts"] == [{"term": "measles cases texas", "topic_id": "measles-cases", "topic_term": "measles cases",
                                    "relation": "contains"}]


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


def _batch(tmp_path, entries, *flags):
    out = tmp_path / "out"
    code = topics.main(["--from-requests", _write(tmp_path, "req.json", entries), "--out", str(out),
                        "--existing", _write(tmp_path, "topics.json", ZETARIS_ROWS), *flags])
    if code != 0:
        return code, None, None, None
    return (code, json.loads((out / "mapping.json").read_text(encoding="utf-8")), (out / "rows.sql").read_text(encoding="utf-8"),
            (out / "report.txt").read_text(encoding="utf-8"))


def _recording_json_task(monkeypatch, reply=None):
    """Patch llm.json_task with a fake that records every call (a raising guard would be swallowed: suggest catches it)."""
    calls = []

    def fake(task, payload, *, dry_run, which="default"):
        calls.append((task, payload["phrase"], dry_run))
        if isinstance(reply, BaseException):
            raise reply
        return reply(payload["phrase"]) if callable(reply) else reply

    monkeypatch.setattr(llm, "json_task", fake)
    return calls


def _route(monkeypatch, live):
    """The route as llm.is_dry_run resolves it, without a real route: json_task is always a fake in these tests."""
    monkeypatch.setattr(llm, "is_dry_run", lambda flag: bool(flag) or not live)


MARS_REPLY = {"slug": "mars-sample-return", "name": "Mars Sample Return", "terms": ["Mars sample return", "MSR", "Perseverance"],
              "notes": "n"}


def test_cli_dry_run_batch_writes_three_files(tmp_path, monkeypatch, capsys):
    calls = _recording_json_task(monkeypatch, MARS_REPLY)
    _route(monkeypatch, live=True)  # a configured route: --dry-run alone must keep the batch off it
    code, mapping, sql, report = _batch(tmp_path, SAMPLE, "--dry-run")
    assert code == 0 and calls == []
    assert [m["status"] for m in mapping] == ["existing", "existing", "new", "needs_review", "rejected"]
    assert {m["source"] for m in mapping if m["status"] in ("new", "needs_review") and m["source"]} == {"derive"}
    assert mapping[0]["topic_id"] == "russia-ukraine-war" and mapping[4]["text"] == topics.WITHHELD
    assert sql.count("INSERT INTO topics") == 1 and "'mars-sample-return-mission'" in sql and "DO NOTHING RETURNING id" in sql
    assert ", dry run)." in sql.splitlines()[0]
    assert "existing 2, new 1, needs_review 1, rejected 1" in report and "mode:       dry run (derive, no model call)" in report
    assert "example.com" not in report and "example.com" not in json.dumps(mapping)
    assert "status:" in capsys.readouterr().out


def test_cli_live_batch_uses_suggest(tmp_path, monkeypatch):
    calls = _recording_json_task(monkeypatch, MARS_REPLY)
    _route(monkeypatch, live=True)
    code, (m,), sql, report = _batch(tmp_path, SAMPLE[2:3])
    assert code == 0 and calls == [("topic_terms", "Mars sample return mission", False)]
    assert m["status"] == "new" and m["source"] == "model" and m["topic_id"] == "mars-sample-return"
    assert m["terms"] == ["mars sample return", "MSR", "perseverance"]
    assert f"mode:       {topics.MODE_LIVE}" in report and ", live)." in sql.splitlines()[0]


def test_cli_batch_in_a_dry_environment_says_so(tmp_path, monkeypatch):
    """No --dry-run, but QUORUM_DRY_RUN=1 (or no route): suggest answers with its stand-in, and every label says so."""
    calls = _recording_json_task(monkeypatch, MARS_REPLY)
    monkeypatch.setenv("QUORUM_DRY_RUN", "1")
    code, (m,), sql, report = _batch(tmp_path, SAMPLE[2:3])
    assert code == 0 and calls == [("topic_terms", "Mars sample return mission", True)]
    assert m["status"] == "new" and m["source"] == "dry-run stand-in"
    assert f"mode:       {topics.MODE_DRY_ENV}" in report and "live" not in report.splitlines()[2]
    assert "dry environment, stand-in terms" in sql.splitlines()[0] and ", live)" not in sql


def test_cli_batch_keeps_the_fallback_reason(tmp_path, monkeypatch):
    calls = _recording_json_task(monkeypatch, RuntimeError("route down"))
    _route(monkeypatch, live=True)
    code, (m,), _, _ = _batch(tmp_path, SAMPLE[2:3])
    assert code == 0 and len(calls) == 1
    assert m["status"] == "new" and m["source"] == "fallback" and m["topic_id"] == "mars-sample-return-mission"
    assert "terms from the fallback (model call failed: RuntimeError: route down)" in m["reason"]


def test_cli_live_batch_is_capped(tmp_path, monkeypatch):
    calls = _recording_json_task(monkeypatch, lambda phrase: {**topics.derive(phrase), "notes": ""})
    _route(monkeypatch, live=True)
    monkeypatch.setattr(topics, "MAX_MODEL_CALLS", 1)
    code, mapping, sql, _ = _batch(tmp_path, [{"text": "Mars sample return mission", "count": 3}, {"text": "Gaza ceasefire", "count": 2}])
    assert code == 0 and [c[1] for c in calls] == ["Mars sample return mission"]
    assert mapping[0]["status"] == "new" and mapping[1]["status"] == "needs_review"
    assert mapping[1]["reason"].startswith("deferred: this batch reached its cap of 1 model calls")
    assert sql.count("INSERT") == 1


def test_cli_dry_environment_has_no_cap(tmp_path, monkeypatch):
    calls = _recording_json_task(monkeypatch, lambda phrase: {**topics.derive(phrase), "notes": ""})
    monkeypatch.setenv("QUORUM_DRY_RUN", "1")
    monkeypatch.setattr(topics, "MAX_MODEL_CALLS", 1)
    code, mapping, _, _ = _batch(tmp_path, [{"text": "Mars sample return mission", "count": 3}, {"text": "Gaza ceasefire", "count": 2}])
    assert code == 0 and len(calls) == 2 and all(c[2] is True for c in calls)
    assert [m["status"] for m in mapping] == ["new", "new"] and {m["source"] for m in mapping} == {"dry-run stand-in"}


def test_cli_text_that_utf8_cannot_encode_is_rejected_and_echoed_safely(tmp_path):
    path = tmp_path / "req.json"
    path.write_text(json.dumps([{"text": "\ud800 topic", "key": "\ud800"}, {"text": "x\x85y topic"}, {"text": "Gaza ceasefire"}]),
                    encoding="utf-8")  # ensure_ascii: the lone surrogate travels as a JSON escape
    out = tmp_path / "out"
    assert topics.main(["--from-requests", str(path), "--out", str(out), "--dry-run",
                        "--existing", _write(tmp_path, "topics.json", ZETARIS_ROWS)]) == 0
    mapping = json.loads((out / "mapping.json").read_text(encoding="utf-8"))
    assert [m["status"] for m in mapping] == ["rejected", "rejected", "new"]
    assert mapping[0]["text"] == "\ufffd topic" and mapping[0]["key"] == "\ufffd" and mapping[1]["text"] == "x y topic"  # NEL is whitespace: collapsed


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
