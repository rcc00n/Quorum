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
    # vowel signs of Indic and Thai scripts are marks but not diacritics: kept, and part of the word
    ("\u091a\u0940\u0928", "\u091a\u0940\u0928"),  # China
    ("\u091a\u0928\u093e", "\u091a\u0928\u093e"),  # chickpea: a different key from China
    ("\u092d\u093e\u0930\u0924", "\u092d\u093e\u0930\u0924"),
    ("\u091a\u0940\u0928 \u0914\u0930 \u092d\u093e\u0930\u0924", "\u0914\u0930 \u091a\u0940\u0928 \u092d\u093e\u0930\u0924"),
    ("\u0e1b\u0e35\u0e43\u0e2b\u0e21\u0e48", "\u0e1b\u0e35\u0e43\u0e2b\u0e21\u0e48"),
    ("\u0e01\u0e23\u0e38\u0e07\u0e40\u0e17\u0e1e", "\u0e01\u0e23\u0e38\u0e07\u0e40\u0e17\u0e1e"),
    # every key stopword, so that both implementations are held to the whole list
    ("a about an and at by for from in into of on or over s the to vs with news", ""),
    ("Ukraine vs Russia with news about war", "russia ukraine war"),
]

# The key's stopwords exactly as docs/DECISIONS.md › Daily editions for users lists them (the contract with the web app).
DOCUMENTED_KEY_STOPWORDS = "a about an and at by for from in into of on or over s the to vs with news"


@pytest.mark.parametrize("text, key", KEY_VECTORS)
def test_request_key_contract(text, key):
    assert topics.request_key(text) == key


def _js_twin() -> str:
    doc = topics.request_key.__doc__
    start = doc.index("const STOP")
    end = doc.index('.join(" ");', start) + len('.join(" ");')
    return "\n".join(line.strip() for line in doc[start:end].splitlines())


def test_js_twin_in_the_source_is_the_javascript_to_copy():
    """The docstring is raw, so the source file shows `\\p{L}`, not `\\\\p{L}` (a regex SyntaxError in JavaScript)."""
    src = Path(topics.__file__).read_text(encoding="utf-8")
    twin = _js_twin()
    flat = "\n".join(line.strip() for line in src.splitlines())
    assert twin in flat and "\\\\" not in twin
    for piece in (r"/\p{Cf}/gu", r"/[\u0300-\u036f\u1ab0-\u1aff\u1dc0-\u1dff\u20d0-\u20ff\ufe20-\ufe2f]/gu",
                  r"/(?<=\p{L})\.(?=\p{L})/gu", r"/[\p{L}\p{M}\p{N}]+/gu"):
        assert piece in twin
    assert r"/\p{M}/gu" not in twin  # not every combining mark is deleted: Indic and Thai vowel signs stay


def test_js_twin_folds_the_same_diacritic_blocks():
    ranges = re.search(r"\.replace\(/\[((?:\\u[0-9a-f]{4}-\\u[0-9a-f]{4})+)\]/gu", _js_twin()).group(1)
    pairs = re.findall(r"\\u([0-9a-f]{4})-\\u([0-9a-f]{4})", ranges)
    assert tuple((int(a, 16), int(b, 16)) for a, b in pairs) == topics._DIACRITICS


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


def test_key_stopwords_are_the_documented_list_in_python_and_in_the_js_twin():
    """Runs without node: the JavaScript twin's STOP list is read from the docstring and compared."""
    documented = frozenset(DOCUMENTED_KEY_STOPWORDS.split())
    assert topics.KEY_STOPWORDS == documented
    js_stop = re.search(r'const STOP = new Set\("([^"]*)"\.split\(" "\)\);', topics.request_key.__doc__).group(1)
    assert js_stop.split(" ") == DOCUMENTED_KEY_STOPWORDS.split(" ")
    decisions = Path(topics.__file__).resolve().parents[2] / "docs" / "DECISIONS.md"
    if decisions.exists():  # the repository checkout; an installed package has no docs
        assert f"drop the stopwords `{DOCUMENTED_KEY_STOPWORDS}`" in decisions.read_text(encoding="utf-8")


def test_indic_words_that_differ_by_vowel_sign_are_different_requests(existing):
    china, chickpea = resolve([{"text": "चीन", "count": 2}, "चना"], existing)
    assert china["key"] != chickpea["key"] and china["text"] == "चीन" and chickpea["text"] == "चना"
    assert china["topic_id"] != chickpea["topic_id"]


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
        # markup in the NFKC form, which the intake matches and derives from
        ("\uff1cscript\uff1e topic", "contains markup or control characters", False),
        ("\ufe64b\ufe65 topic", "contains markup or control characters", False),
        # host labels in any script, a TLD in any script before "/", ideographic full stops (closing round 1)
        ("j\u0430nedoe.com/profile", "contains a URL", True),  # a Cyrillic "a"
        ("m\u00fcnchen.de/news", "contains a URL", True),
        ("b\u00fccher.de/jane-doe", "contains a URL", True),
        ("m\u00fcnchen.de", "contains a URL", True),
        ("\u043f\u0440\u0438\u043c\u0435\u0440.\u0440\u0444/ivan-petrov", "contains a URL", True),
        ("example\u3002com/jane", "contains a URL", True),
        ("example\uff0ecom/jane", "contains a URL", True),
        ("example\uff61com/jane", "contains a URL", True),
        ("x.xn--p1ai/path", "contains a URL", True),
        # dash-like separators, "/" and "_" between phone digits; 9+ digits in 2+ groups
        ("call 555\u2011123\u20114567", "contains a phone number", True),  # non-breaking hyphen (NFKC: U+2010)
        ("Jane Doe 555\u2010123\u20104567", "contains a phone number", True),
        ("call 555\u2212123\u22124567", "contains a phone number", True),  # minus sign
        ("call 555\u2013123\u20134567", "contains a phone number", True),  # en dash
        ("call 555/123/4567", "contains a phone number", True),
        ("call 555_123_4567", "contains a phone number", True),
        ("call 0170 1234567", "contains a phone number", True),
        ("+49\u2011170\u20111234567", "contains a phone number", True),
        ("555\u2011123\u20114567", "contains a phone number", True),  # digits alone: withheld, not "no letters"
        ("dial 555\u20101234", "contains a phone number", True),
    ],
)
def test_rejections(text, why, withheld):
    assert topics.check_request(text) == (why, withheld)


@pytest.mark.parametrize(
    "text",
    ["war in Ukraine", "fiscal year 2026-2027", "Top 100 2026", "Boeing 737-800", "Node.js security flaw", "AT&T merger",
     "A.I. regulation", "S&P 500 crash", "U.S.-China trade", "Війна в Україні", "x" * 80, "COVID-19 in 2026",
     "Ukr\u00adaine war", "\u202eevil topic", "x" * 80 + "\u00ad\u200b",
     # closing round 1: years, fractions and big numbers are no phone numbers; a non-ASCII word or full stop is no URL
     "2024-2025 season", "2024\u20132025 budget", "24/7 news", "9/11 anniversary", "1 000 000 dollars",
     "St. Louis floods", "\u6771\u4eac\u3002\u9078\u6319", "M\u00fcnchen Oktoberfest", "version 1.25 release"],
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


def test_unicode_personal_data_never_becomes_a_row(existing):
    """Before closing round 1 these became `new` rows named "Jane Doe 555‐123‐4567" or "Jаnedoe.com/profile"."""
    texts = ["jаnedoe.com/profile", "Jane Doe 555‐123‐4567", "555‑123‑4567",
             "пример.рф/ivan-petrov", "example。com/jane"]
    res = resolve(texts, existing)
    assert [r["status"] for r in res] == ["rejected"] * len(texts)
    assert all(r["text"] == r["key"] == topics.WITHHELD for r in res)
    assert topics.rows_sql(res).count("INSERT") == 0


@pytest.mark.parametrize(
    "web_key, text, status",
    [
        ("john.doe@example.com +1 555 123 4567", "Iran", "new"),
        ("call 555-123-4567 john@x.org", "", "rejected"),
        ("jane doe 0170 1234567", "Iran", "new"),
        ("jаnedoe.com/profile", "Iran", "new"),
        ("k" * 5000, "Iran", "new"),
        ("k" * 81, "Iran", "new"),
    ],
)
def test_a_web_key_that_may_carry_personal_data_is_withheld(existing, web_key, text, status):
    (r,) = topics.resolve_requests([{"key": web_key, "text": text, "count": 1}], existing, propose=dry)
    assert r["status"] == status and r["key"] == topics.WITHHELD
    assert r["key_mismatch"] == ("iran" if text else None)  # the contract's key is still shown


def test_a_web_key_equal_to_the_contract_key_is_not_scanned(existing):
    """The contract's key of an accepted text is built from text that passed check_request; its sorted tokens may
    put digits side by side ("100 2026 2027") without being a phone number."""
    text = "budget 2026 plan 2027 vote 100"
    key = topics.request_key(text)
    assert key == "100 2026 2027 budget plan vote" and topics.check_request(text) == ("", False)
    (r,) = topics.resolve_requests([{"key": key, "text": text, "count": 1}], existing, propose=dry)
    assert r["key"] == key and r["key_mismatch"] is None
    (other,) = topics.resolve_requests([{"key": "ceasefire gaza now", "text": "Gaza ceasefire", "count": 1}], existing, propose=dry)
    assert other["key"] == "ceasefire gaza now" and other["key_mismatch"] == "ceasefire gaza"  # a harmless key is echoed


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


@pytest.mark.parametrize(
    "rows",
    [
        [],  # an empty or stale registration, a wrong ZETARIS_COLLECTION_DB
        [{"col0": "russia-ukraine-war", "col1": "Russia", "col2": "{Ukraine}"}],  # tools_zetaris without column names
        [{"id": "", "name": "no id", "query_terms": "{x}"}],
        None,
    ],
)
def test_read_topics_refuses_a_read_that_yields_no_topic(rows):
    """Collection always holds its seed topic, so zero topics is a misread, never an empty table (DECISION at read_topics)."""
    seen = []

    def runner(sql, limit):
        seen.append(sql)
        return rows

    with pytest.raises(RuntimeError, match="none with an id") as exc:
        topics.read_topics(runner)
    assert len(seen) == len(topics._TOPIC_COLUMNS) and "cannot read existing topics" in str(exc.value)


def test_read_topics_takes_a_narrower_query_when_a_wider_one_yields_no_topic():
    found, note = topics.read_topics(lambda sql, limit: [] if "active" in sql else ZETARIS_ROWS)
    assert [t["id"] for t in found] == [r["id"] for r in ZETARIS_ROWS]
    assert "wider queries failed" in note and "0 rows, none with an id" in note


def test_read_topics_counts_rows_dropped_without_an_id():
    found, note = topics.read_topics(lambda sql, limit: [ZETARIS_ROWS[0], {"name": "no id", "query_terms": "{x}"}])
    assert [t["id"] for t in found] == ["russia-ukraine-war"] and "WARNING: 1 of 2 rows dropped, no id" in note
    _, clean = topics.read_topics(lambda sql, limit: ZETARIS_ROWS)
    assert "dropped" not in clean


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
    ],
)
def test_a_headline_collected_under_an_existing_topic_maps_to_it(existing, text, topic_id, term):
    (r,) = resolve([text], existing)
    assert (r["status"], r["topic_id"], r["match"]) == ("existing", topic_id, "headline")
    assert repr(term) in r["reason"] and r["terms"] == next(t["terms"] for t in existing if t["id"] == topic_id)
    assert f"collection gives a headline saying {text!r} to {topic_id} (term {term!r}), the first active topic" in r["reason"]
    assert "every word of the request is in its name, slug or matching terms" in r["reason"]
    assert "collection order unknown" not in r["reason"]


def test_a_covering_topic_that_does_not_get_the_headline_is_needs_review(existing):
    """collectors/common.py first_topic_match gives "AI chips export controls" to the older tariffs-trade-war-china
    ("export controls"), although only ai-regulation-export-controls covers "AI chips": the operator chooses."""
    (r,) = resolve(["AI chips export controls"], existing)
    assert (r["status"], r["topic_id"], r["match"]) == ("needs_review", "ai-regulation-export-controls", "headline")
    assert r["reason"] == ("every word of the request is in the name, slug or matching terms of ai-regulation-export-controls "
                           "(term 'export controls'), but collection gives a headline saying 'AI chips export controls' to "
                           "tariffs-trade-war-china (term 'export controls'), the first active topic whose terms match it; "
                           "map the request to one of them")
    assert topics.rows_sql([r]).count("INSERT") == 0


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
        # other wordings and narrower topics of an existing topic (review round 2)
        ("climate change", "climate-policy", "climate"),
        ("Russian invasion of Ukraine", "russia-ukraine-war", "Ukraine"),
        ("Zelensky visit to Washington", "russia-ukraine-war", "Zelensky"),
        ("tariffs on Canada", "tariffs-trade-war-china", "tariffs"),
        ("Ukraine drone attacks", "russia-ukraine-war", "Ukraine"),
        ("ICE raids in Los Angeles", "immigration-southern-border", "ICE raids"),
        ("AI safety bill California", "ai-regulation-export-controls", "AI safety"),
        ("deportation flights to Venezuela", "immigration-southern-border", "deportation"),
    ],
)
def test_one_shared_term_does_not_make_a_request_existing(existing, text, topic_id, term):
    """A headline hit maps to that topic only when every word of the request is in its name, slug or matching terms.
    Otherwise the row would be `new` in name only: collection gives every headline that says the typed words to the
    older topic, so the request is needs_review, with the proposed row and the older topic to choose from."""
    (r,) = resolve([text], existing)
    assert (r["status"], r["match"]) == ("needs_review", None) and r["topic_id"] not in {t["id"] for t in existing}
    assert r["reason"].startswith(f"collection gives a headline saying {text!r} to {topic_id} (term {term!r}), the first "
                                  "active topic whose terms match it, so this row would not receive the headlines")
    assert f"map the request to {topic_id} or accept the row" in r["reason"]
    assert term.lower() not in {t.lower() for t in r["terms"]} and topic_id in {c["topic_id"] for c in r["conflicts"]}
    assert r["terms"] and topics.rows_sql([r]).count("INSERT") == 0  # the proposed row is shown, never inserted


def test_unknown_collection_order_is_stated_where_two_existing_topics_match(existing):
    (ordered,) = resolve(["export controls"], existing)
    (unknown,) = resolve(["export controls"], existing, order_known=False)
    assert "collection order unknown" not in ordered["reason"] and unknown["status"] == "existing"
    assert unknown["reason"].endswith("; collection order unknown (created_at not readable, topics taken in the order "
                                      "returned), so which of tariffs-trade-war-china, ai-regulation-export-controls keeps "
                                      "such a headline is not certain")
    (one,) = resolve(["war in Ukraine"], existing, order_known=False)  # one matching topic: the order does not matter
    assert one["status"] == "existing" and "collection order unknown" not in one["reason"]
    (both,) = resolve(["AI chips export controls"], existing, order_known=False)
    assert both["status"] == "needs_review" and "collection order unknown" in both["reason"]


def test_model_terms_that_avoid_every_overlap_still_miss_the_headline(existing):
    """A live proposal for "Ukraine peace talks" may overlap nothing; collection still gives the headline to
    russia-ukraine-war, and the row would fill with Gaza and trade talks."""
    (r,) = resolve(["Ukraine peace talks"], existing, propose=model_row(["peace talks", "istanbul talks", "peace deal", "Witkoff"]))
    assert (r["status"], r["conflicts"], r["source"]) == ("needs_review", [], "model")
    assert "to russia-ukraine-war (term 'Ukraine')" in r["reason"] and "dropped as overlapping" not in r["reason"]


def test_shared_terms_with_new_rows_of_the_batch_do_not_make_requests_existing(existing):
    res = resolve([{"text": "Mars sample return mission", "count": 3}, {"text": "Taylor Swift tour", "count": 3},
                   "Tax return deadline", "Tour de France doping", "Swift banking sanctions"], existing)
    assert [(r["status"], r["topic_id"]) for r in res] == [
        ("new", "mars-sample-return-mission"), ("new", "taylor-swift-tour"), ("needs_review", "tax-return-deadline"),
        ("needs_review", "tour-de-france-doping"), ("needs_review", "swift-banking-sanctions")]
    assert all(r["match"] is None for r in res)
    assert res[2]["reason"].startswith("collection gives a headline saying 'Tax return deadline' to mars-sample-return-mission "
                                       "(a new row of this batch) (term 'return')")
    assert "to taylor-swift-tour (a new row of this batch) (term 'swift')" in res[4]["reason"]
    assert "return" not in res[2]["terms"] and "swift" not in res[4]["terms"]
    assert topics.rows_sql(res).count("INSERT") == 2


def test_new_topic_keeps_only_non_overlapping_terms(existing):
    (r,) = resolve(["Ukrainian refugees in Poland"], existing)  # "Ukrainian" is a term of russia-ukraine-war; Poland is not
    assert r["status"] == "needs_review" and "to russia-ukraine-war (term 'Ukrainian')" in r["reason"]
    assert "ukrainian" not in [t.lower() for t in r["terms"]] and "poland" in r["terms"]
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
    assert r["reason"] == ("the overlap dropped terms that the typed words contain: 'china' (contained_in 'china tariffs' of "
                           "tariffs-trade-war-china); none of the kept terms occurs in a headline saying 'China', so this "
                           "row would miss its own subject; map the request to tariffs-trade-war-china or accept the row")
    (r,) = resolve(["China"], existing, propose=model_row(["China", "Beijing"]))  # a model's paraphrase does not help either
    assert r["status"] == "needs_review" and r["terms"] == ["beijing"]


def test_a_typed_word_held_only_inside_a_longer_older_term_keeps_the_row_new(existing):
    """"china" is dropped (it is contained in "china tariffs"), but a headline saying "China chess" matches no term of
    tariffs-trade-war-china, and the kept "chess" collects it."""
    (r,) = resolve(["China chess"], existing)
    assert r["status"] == "new" and "china" not in r["terms"] and {"china chess", "chess"} <= set(r["terms"])
    assert {(c["term"], c["relation"]) for c in r["conflicts"]} == {("china", "contained_in")}


@pytest.mark.parametrize(
    "text, topic_id, variant, term",
    [
        ("ICE raid", "immigration-southern-border", "ICE raids", "ICE raids"),
        ("Government shutdowns", "federal-budget-shutdown", "Government shutdown", "government shutdown"),
        ("Semiconductor", "tariffs-trade-war-china", "Semiconductors", "semiconductors"),  # the older of two
        ("Immigrant", "immigration-southern-border", "Immigrants", "immigrants"),
        ("Emission", "climate-policy", "Emissions", "emissions"),
        ("data center", "ai-regulation-export-controls", "data centers", "data centers"),
        ("AI chip", "ai-regulation-export-controls", "AI chips", "AI chips"),
        ("border walls", "immigration-southern-border", "border wall", "border wall"),
        ("debt ceilings", "federal-budget-shutdown", "debt ceiling", "debt ceiling"),
        ("continuing resolutions", "federal-budget-shutdown", "continuing resolution", "continuing resolution"),
        ("Migrant caravan", "immigration-southern-border", "Migrants caravan", "migrants"),
        ("Ukrainians", "russia-ukraine-war", "Ukrainian", "Ukrainian"),
    ],
)
def test_a_typed_word_in_its_other_number_is_needs_review(existing, text, topic_id, variant, term):
    """Collection does not stem: a headline saying the other number of a typed word goes to the older topic, so a new
    row would split the subject's documents with it (closing round 1; before, every one of these was `new`)."""
    (r,) = resolve([text], existing)
    assert (r["status"], r["match"]) == ("needs_review", None) and r["topic_id"] not in {t["id"] for t in existing}
    assert r["reason"].startswith(f"collection gives a headline saying {variant!r} (the typed ")
    assert f"to {topic_id} (term {term!r}), the first active topic whose terms match it" in r["reason"]
    assert f"map the request to {topic_id} or accept the row" in r["reason"]
    assert topics.rows_sql([r]).count("INSERT") == 0


def test_a_model_row_for_the_other_number_is_needs_review_too(existing):
    (r,) = resolve(["ICE raid"], existing, propose=model_row(["ICE raid", "workplace raid"]))
    assert (r["status"], r["source"], r["conflicts"], r["terms"]) == ("needs_review", "model", [], ["ICE raid", "workplace raid"])
    assert "saying 'ICE raids' (the typed 'raid' as 'raids') to immigration-southern-border" in r["reason"]


def test_number_variants_of_a_word():
    assert topics._other_numbers("raid") == ["raids"]
    assert topics._other_numbers("shutdowns") == ["shutdown"]
    assert topics._other_numbers("ceilings") == ["ceiling"]
    assert topics._other_numbers("policies") == ["policy", "polici", "policie"]
    assert topics._other_numbers("taxes") == ["tax", "taxe"]
    assert topics._other_numbers("ICE") == [] and topics._other_numbers("the") == [] and topics._other_numbers("café") == []


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


@pytest.mark.parametrize("text, terms", [("K-pop", ["k-pop", "k-pops"]), ("Wi-Fi", ["wi-fi", "wi-fis"]), ("X-ray", ["x-ray", "x-rays"])])
def test_a_hyphenated_word_stays_whole(existing, text, terms):
    """Split at the hyphen, "k pop" would never match a headline saying "K-pop" (collection matches whole words)."""
    assert topics.derive(text)["terms"] == terms
    (r,) = resolve([text], existing)
    assert r["status"] == "new" and r["terms"] == terms


def test_hyphenated_parts_are_also_single_terms():
    terms = topics.derive("Russia-Ukraine talks")["terms"]
    assert "russia-ukraine talks" in terms and {"russia-ukraine", "russia", "ukraine"} <= set(terms)
    assert topics.derive("Boeing 737-800")["terms"][:2] == ["boeing 737-800", "boeing 737-800s"]
    assert topics.derive("Ｋ-pop")["terms"] == ["k-pop", "k-pops"]  # NFKC first: a full-width letter is matched as ASCII


# A literal, not topics.DERIVED_SOURCES: removing a source from the constant must fail these cases, not drop them.
DERIVED = ("derive", "dry-run stand-in", "fallback")


def test_derived_sources_are_the_three_derive_paths():
    assert topics.DERIVED_SOURCES == DERIVED


@pytest.mark.parametrize("source", DERIVED)
@pytest.mark.parametrize("text", ["चीन", "ปีใหม่"])
def test_derived_terms_that_miss_the_typed_words_are_needs_review(existing, text, source):
    """derive splits words at a vowel sign ("चीन" -> "च न"); such terms would collect nothing on the subject."""
    (r,) = resolve([text], existing, propose=lambda t: {**topics.derive(t), "source": source})
    assert (r["status"], r["source"]) == ("needs_review", source) and r["terms"]
    assert r["reason"].startswith("the derived terms would not match the typed words: none of ")
    assert topics.rows_sql([r]).count("INSERT") == 0


@pytest.mark.parametrize("text", ["us", "it", "who", "May", "WHO", "IS", "F-35"])
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
    # not "measles case counts": a headline saying "measles cases counts" (one word in its other number) goes to the
    # first row, so that request is needs_review (test_a_typed_word_in_its_other_number_is_needs_review)
    res = resolve(["measles cases", "measles in schools"], existing,
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


@pytest.mark.parametrize("reverse", [False, True])
def test_a_key_group_resolves_alike_in_either_input_order(existing, reverse):
    """The key ignores word order and compatibility forms; the headline match and derive do not. Every text of the
    group is checked as a headline in NFKC form, so the shared result does not depend on which entry came first."""
    entries = [{"text": "war trade China", "count": 1}, {"text": "China trade war", "count": 50}]
    res = resolve(entries[::-1] if reverse else entries, existing)
    assert {(r["status"], r["topic_id"], r["match"]) for r in res} == {("existing", "tariffs-trade-war-china", "headline")}
    entries = [{"text": "Ｕｋｒａｉｎｅ war", "count": 1}, {"text": "Ukraine war", "count": 9}]
    res = resolve(entries[::-1] if reverse else entries, existing)
    assert {(r["status"], r["topic_id"]) for r in res} == {("existing", "russia-ukraine-war")}
    assert {r["text"] for r in res} == {"Ｕｋｒａｉｎｅ war", "Ukraine war"}  # each entry keeps its text
    entries = [{"text": "war trade China", "count": 2}, {"text": "China trade war", "count": 2}]  # a tie
    assert {r["status"] for r in resolve(entries[::-1] if reverse else entries, existing)} == {"existing"}


def test_a_new_row_is_proposed_from_the_most_requested_text_in_nfkc_form(existing):
    calls = []

    def propose(text):
        calls.append(text)
        return dry(text)

    full_width = "Ｍａｒｓ ｓａｍｐｌｅ ｒｅｔｕｒｎ"  # Mars sample return
    res = resolve([{"text": full_width, "count": 1}, {"text": "return sample Mars", "count": 4}], existing, propose=propose)
    assert calls == ["return sample Mars"] and {r["name"] for r in res} == {"Return Sample Mars"}
    (r,) = resolve([full_width], existing, propose=propose)
    assert calls[-1] == "Mars sample return" and r["status"] == "new" and r["name"] == "Mars Sample Return"
    assert all(t.isascii() for t in r["terms"]) and topics._occurs(r["terms"][0], "Mars sample return delayed again")


def test_later_requests_match_new_rows_of_the_batch_and_count_sets_the_order(existing):
    res = resolve([{"text": "measles in Texas", "count": 1}, {"text": "measles outbreak Texas", "count": 6},
                   {"text": "measles vaccine exemptions", "count": 1}], existing)
    first, second, third = res
    assert second["status"] == "new" and second["order"] == 1
    assert (first["status"], first["topic_id"], first["match"]) == ("existing", "measles-outbreak-texas", "headline")
    assert "a new row of this batch" in first["reason"]
    # "vaccine exemptions" is in no name, slug or term of the batch row, but the batch row gets the headline ("measles")
    assert (third["status"], third["topic_id"], third["order"]) == ("needs_review", "measles-vaccine-exemptions", None)
    assert "measles" not in third["terms"]
    assert "to measles-outbreak-texas (a new row of this batch) (term 'measles')" in third["reason"]


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
    assert m["caution"].startswith("terms derived from the phrase's own words (dry-run stand-in)")
    assert f"-- {topics.REVIEW_BEFORE_APPLYING}: 1 of 1 rows below" in sql
    assert f"mode:       {topics.MODE_DRY_ENV}" in report and "live" not in report.splitlines()[2]
    assert "dry environment, stand-in terms" in sql.splitlines()[0] and ", live)" not in sql


def test_cli_batch_keeps_the_fallback_reason(tmp_path, monkeypatch):
    calls = _recording_json_task(monkeypatch, RuntimeError("route down"))
    _route(monkeypatch, live=True)
    code, (m,), _, _ = _batch(tmp_path, SAMPLE[2:3])
    assert code == 0 and len(calls) == 1
    assert m["status"] == "new" and m["source"] == "fallback" and m["topic_id"] == "mars-sample-return-mission"
    assert "terms from the fallback (model call failed: RuntimeError: route down)" in m["reason"]
    assert m["caution"].startswith("terms derived from the phrase's own words (fallback), not chosen by a model")
    assert "'mission'" in m["caution"]


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


def test_cli_dry_environment_stand_in_for_a_phrase_derive_splits(tmp_path, monkeypatch):
    """No fake json_task: QUORUM_DRY_RUN=1 makes the real dry-run stand-in answer (dryrun.topic_terms -> derive). A live
    path would need llm._route, which fails the test here (pytest.fail is not caught by suggest)."""
    monkeypatch.setenv("QUORUM_DRY_RUN", "1")
    monkeypatch.setattr(llm, "_route", lambda *a, **k: pytest.fail("a model route was resolved", pytrace=False))
    code, (m,), sql, report = _batch(tmp_path, [{"text": "चीन", "count": 1}])
    assert code == 0 and (m["status"], m["source"]) == ("needs_review", "dry-run stand-in") and m["terms"]
    assert m["reason"].startswith("the derived terms would not match the typed words: none of ")
    assert "INSERT" not in sql and f"mode:       {topics.MODE_DRY_ENV}" in report


def test_cli_fallback_for_a_phrase_derive_splits(tmp_path, monkeypatch):
    calls = _recording_json_task(monkeypatch, RuntimeError("route down"))
    _route(monkeypatch, live=True)
    code, (m,), sql, _ = _batch(tmp_path, [{"text": "चीन", "count": 1}])
    assert code == 0 and len(calls) == 1 and (m["status"], m["source"]) == ("needs_review", "fallback")
    assert m["reason"].startswith("the derived terms would not match the typed words: none of ") and "INSERT" not in sql


def test_cli_rows_with_derived_terms_are_marked_for_review(tmp_path):
    """Derived single words of a longer phrase collect every headline that says them ("texas": 19 rehearsal titles and
    leads, none about measles; "TODAY"); the rows keep their status, and every output says to review them."""
    entries = [{"text": "measles outbreak Texas", "count": 3}, {"text": "THE NEWS TODAY", "count": 2}, {"text": "Ebola", "count": 1},
               {"text": "AI", "count": 1}]
    code, mapping, sql, report = _batch(tmp_path, entries, "--dry-run")
    measles, today, ebola, ai = mapping
    assert code == 0 and [m["status"] for m in mapping] == ["new", "new", "new", "needs_review"] and today["terms"] == ["TODAY"]
    assert ai["terms"] == [] and ai["caution"] is None  # no kept term, nothing to review
    prefix = "terms derived from the phrase's own words (derive), not chosen by a model: review them before applying"
    assert measles["caution"] == (prefix + "; single words of a longer phrase collect every headline that says them: "
                                  "'measles', 'outbreak', 'outbreaks', 'texas'")
    assert today["caution"] == prefix + "; single words of a longer phrase collect every headline that says them: 'TODAY'"
    assert ebola["caution"] == prefix  # a one-word phrase: its word is the topic
    assert f"-- {topics.REVIEW_BEFORE_APPLYING}: 3 of 3 rows below" in sql and sql.count("--    review: ") == 3
    review_lines = [line for line in sql.splitlines() if line.startswith("--    review: ")]
    assert "'texas'" in review_lines[0] and "'TODAY'" in review_lines[1]
    assert report.count("      caution: ") == 3


def test_cli_model_rows_carry_no_caution(tmp_path, monkeypatch):
    _recording_json_task(monkeypatch, MARS_REPLY)
    _route(monkeypatch, live=True)
    code, (m,), sql, report = _batch(tmp_path, SAMPLE[2:3])
    assert code == 0 and m["source"] == "model" and m["caution"] is None
    assert topics.REVIEW_BEFORE_APPLYING not in sql and "caution:" not in report
    assert topics.resolve_requests([{"text": "Me Too"}], [], propose=dry)[0]["caution"] == (
        "terms derived from the phrase's own words (derive), not chosen by a model: review them before applying")


def test_cli_an_empty_zetaris_read_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(corpus, "_run_sql", lambda sql, limit: [])
    out = tmp_path / "out"
    assert topics.main(["--from-requests", _write(tmp_path, "req.json", SAMPLE), "--out", str(out), "--dry-run"]) == 2
    assert not out.exists() and "none with an id" in capsys.readouterr().err


def test_cli_an_explicit_empty_existing_file_is_allowed(tmp_path):
    out = tmp_path / "out"
    assert topics.main(["--from-requests", _write(tmp_path, "req.json", SAMPLE[2:3]), "--out", str(out), "--dry-run",
                        "--existing", _write(tmp_path, "t.json", [])]) == 0
    assert "existing:   0 topics" in (out / "report.txt").read_text(encoding="utf-8")


def test_cli_never_echoes_a_web_key_with_personal_data(tmp_path):
    entries = [{"key": "john.doe@example.com +1 555 123 4567", "text": "Iran", "count": 1},
               {"key": "call 555-123-4567 john@x.org", "text": "", "count": 1}]
    code, mapping, _, report = _batch(tmp_path, entries, "--dry-run")
    assert code == 0 and [m["key"] for m in mapping] == [topics.WITHHELD, topics.WITHHELD]
    assert mapping[0]["key_mismatch"] == "iran" and f"the web sent {topics.WITHHELD!r}, the contract gives 'iran'" in report
    for leaked in ("john", "example.com", "555"):
        assert leaked not in report and leaked not in json.dumps(mapping)


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


def test_cli_states_an_unknown_collection_order_in_the_reason(tmp_path):
    """The rehearsal registration exposes no created_at: report.txt says so, and so does the reason that depends on it."""
    code, (m,), _, report = _batch(tmp_path, [{"text": "export controls"}], "--dry-run")
    assert code == 0 and "created_at not available" in report and "collection order unknown" in m["reason"]
    dated = [{**r, "created_at": f"2026-10-25T06:0{i}:00+00:00"} for i, r in enumerate(ZETARIS_ROWS)]
    out = tmp_path / "dated"
    assert topics.main(["--from-requests", _write(tmp_path, "one.json", [{"text": "export controls"}]), "--out", str(out),
                        "--dry-run", "--existing", _write(tmp_path, "dated.json", dated)]) == 0
    (m,) = json.loads((out / "mapping.json").read_text(encoding="utf-8"))
    assert m["topic_id"] == "tariffs-trade-war-china" and "collection order unknown" not in m["reason"]


# The operator's sample batch (ws-intake/sample/requests.json, run through Zetaris on the rehearsal dump): its
# report.txt must show these statuses.
SAMPLE_BATCH = [
    ("war in Ukraine", 7, "existing", "russia-ukraine-war"),
    ("Russia Ukraine war", 2, "existing", "russia-ukraine-war"),
    ("immigration", 5, "existing", "immigration-southern-border"),
    ("tariffs on China", 4, "existing", "tariffs-trade-war-china"),
    ("Climate policy", 1, "existing", "climate-policy"),
    ("Mars sample return mission", 3, "new", "mars-sample-return-mission"),
    ("measles outbreak Texas", 6, "new", "measles-outbreak-texas"),
    ("Measles outbreak in Texas", 2, "new", "measles-outbreak-texas"),
    ("measles vaccine exemptions", 1, "needs_review", "measles-vaccine-exemptions"),
    ("AI", 2, "needs_review", "ai-news"),
    ("China", 1, "needs_review", "china-news"),
    ("Gaza ceasefire", 2, "new", "gaza-ceasefire"),
    ("https://example.com/news", 1, "rejected", None),
    ("write to someone@example.com", 1, "rejected", None),
    ("", 1, "rejected", None),
    ("This is a deliberately long request that keeps going well past the limit of eighty characters so that the "
     "intake must reject it as too long for a topic name, which it does, twice over.", 1, "rejected", None),
    ("@elonmusk", 1, "rejected", None),
    ("Ukraine peace talks", 2, "needs_review", "ukraine-peace-talks"),
    ("export controls on chips", 1, "needs_review", "export-controls-chips"),
    ("call 555-123-4567", 1, "rejected", None),
]


def test_cli_sample_batch_on_the_rehearsal_topics(tmp_path):
    entries = [{"key": topics.request_key(text), "text": text, "count": count} for text, count, _, _ in SAMPLE_BATCH]
    code, mapping, sql, report = _batch(tmp_path, entries, "--dry-run")
    assert code == 0 and [(m["status"], m["topic_id"]) for m in mapping] == [(s, t) for _, _, s, t in SAMPLE_BATCH]
    assert "status:     existing 5, new 4, needs_review 5, rejected 6" in report
    assert re.findall(r"VALUES \('([^']*)'", sql) == ["measles-outbreak-texas", "mars-sample-return-mission", "gaza-ceasefire"]


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
