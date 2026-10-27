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

# The contract's shared test vectors (docs/DECISIONS.md › Daily editions for users): [{"text", "key"}], the keys as the web
# app's `words()` in web/lib/topic-search.mjs gives them; the web app can run its own copy over the same file.
KEY_VECTORS_FILE = Path(__file__).parent / "data" / "topic_key_vectors.json"
KEY_VECTORS = json.loads(KEY_VECTORS_FILE.read_text(encoding="utf-8"))

# The key's stopwords exactly as docs/DECISIONS.md › Daily editions for users lists them: the web app's STOP list.
DOCUMENTED_KEY_STOPWORDS = "the a an of in on and or for to vs v at by with"

# Where the web app's copy of the rule lives: the checked-out file once the web branch is merged, else PR #24's head
# (fetched read-only: git fetch origin pull/24/head:refs/pr/24).
WEB_KEY_FILE = "web/lib/topic-search.mjs"
WEB_KEY_REF = "refs/pr/24"


def _web_key_source() -> str | None:
    root = Path(topics.__file__).resolve().parents[2]
    checked_out = root / WEB_KEY_FILE
    if checked_out.is_file():
        return checked_out.read_text(encoding="utf-8")
    git = shutil.which("git")
    if git is None:
        return None
    try:
        done = subprocess.run([git, "-C", str(root), "show", f"{WEB_KEY_REF}:{WEB_KEY_FILE}"], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.decode("utf-8") if done.returncode == 0 and done.stdout else None


def test_the_key_vectors_cover_the_contract():
    texts = [v["text"] for v in KEY_VECTORS]
    assert len(KEY_VECTORS) >= 25 and all(set(v) == {"text", "key"} for v in KEY_VECTORS) and len(set(texts)) == len(texts)
    keys = [v["key"] for v in KEY_VECTORS]
    assert any(not t.isascii() for t in texts) and any(not k.isascii() for k in keys)  # non-ASCII
    assert any(any(not (c.isalnum() or c.isspace()) for c in t) for t in texts)  # punctuation
    assert {w for t in texts for w in t.lower().split()} >= set(DOCUMENTED_KEY_STOPWORDS.split())  # every stopword
    assert any(len(w) == 1 for t in texts for w in re.findall(r"\w+", t))  # one-letter tokens
    assert any(re.search(r"\d", k) for k in keys)  # digits
    assert any(k == "" for k in keys) and any(ord(c) > 0xFFFF for k in keys for c in k)  # empty keys, astral letters


@pytest.mark.parametrize("text, key", [(v["text"], v["key"]) for v in KEY_VECTORS], ids=[str(i) for i in range(len(KEY_VECTORS))])
def test_request_key_contract(text, key):
    assert topics.request_key(text) == key


def test_request_key_of_nothing_is_empty():
    assert topics.request_key(None) == "" == topics.request_key("")


def _fuzz_texts(n: int = 400) -> list[str]:
    """Deterministic strings over the characters on which two copies of the rule would drift."""
    import random

    pieces = ["a", "b", "Z", "x", "1", "22", " ", "-", ".", "'", "’", "–", "­", "​", "‮", "\t", " ",
              "　", "é", "É", "ß", "İ", "Σ", "σ", "Й", "ї", "च", "ी",
              "ุ", "中", "Ａ", "₂", "½", "㎒", "ℌ", "\U0001d401", "\U00020000", "﨎",
              "\U0001f525", "the", "of", "v", "vs", "news", "with", "٢", "ệ", "ł", "Ⅰ", "ẞ"]
    rnd = random.Random(20261026)
    return ["".join(rnd.choice(pieces) for _ in range(rnd.randint(1, 12))) for _ in range(n)]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_web_apps_words_give_the_same_keys(tmp_path):
    """Runs the web app's own `words()` from a temporary copy of web/lib/topic-search.mjs over the shared vectors and a
    deterministic fuzz set: the web's key, `[...new Set(words(text))].sort().join(" ")`, must equal `request_key`."""
    source = _web_key_source()
    if source is None:
        pytest.skip(f"{WEB_KEY_FILE} is neither checked out nor readable at {WEB_KEY_REF}")
    (tmp_path / "topic-search.mjs").write_text(source, encoding="utf-8")
    (tmp_path / "keys.mjs").write_text(
        'import { readFileSync } from "node:fs";\n'
        'import { words } from "./topic-search.mjs";\n'
        'const texts = JSON.parse(readFileSync(process.argv[2], "utf8"));\n'
        'process.stdout.write(JSON.stringify(texts.map((t) => [...new Set(words(t))].sort().join(" "))));\n',
        encoding="utf-8")
    texts = [v["text"] for v in KEY_VECTORS] + _fuzz_texts()
    (tmp_path / "texts.json").write_text(json.dumps(texts), encoding="utf-8")
    done = subprocess.run([shutil.which("node"), str(tmp_path / "keys.mjs"), str(tmp_path / "texts.json")],
                          capture_output=True, timeout=60)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    web = json.loads(done.stdout.decode("utf-8"))
    assert web[: len(KEY_VECTORS)] == [v["key"] for v in KEY_VECTORS]
    assert [(t, w) for t, w in zip(texts, web) if topics.request_key(t) != w] == []


def test_key_stopwords_are_the_documented_list_and_the_web_apps():
    """Runs without node: the web app's STOP list is read from its source when it is available."""
    assert topics.KEY_STOPWORDS == frozenset(DOCUMENTED_KEY_STOPWORDS.split())
    decisions = Path(topics.__file__).resolve().parents[2] / "docs" / "DECISIONS.md"
    if decisions.exists():  # the repository checkout; an installed package has no docs
        assert f"drop the stopwords `{DOCUMENTED_KEY_STOPWORDS}`" in decisions.read_text(encoding="utf-8")
    source = _web_key_source()
    if source is None:
        pytest.skip(f"{WEB_KEY_FILE} is neither checked out nor readable at {WEB_KEY_REF}")
    web_stop = re.search(r"const STOP = new Set\(\[([^\]]*)\]\)", source).group(1)
    assert re.findall(r'"([^"]*)"', web_stop) == DOCUMENTED_KEY_STOPWORDS.split()


def test_request_key_is_idempotent_and_order_free():
    for text in ("measles outbreak in Texas", "Texas: measles outbreak", "Mars sample-return mission", "Війна в Україні"):
        key = topics.request_key(text)
        assert topics.request_key(key) == key
        assert key == " ".join(sorted(set(key.split())))
    assert topics.request_key("Texas: measles outbreak") == topics.request_key("measles outbreak in Texas")


def test_key_stopwords_are_small_and_keep_meaningful_words():
    assert len(topics.KEY_STOPWORDS) <= 25
    for word in ("us", "war", "ai", "not", "no", "news"):
        assert word not in topics.KEY_STOPWORDS


def test_one_letter_tokens_are_dropped_by_utf16_length():
    """JavaScript's `w.length > 1` counts UTF-16 code units: an astral-plane letter alone is a token, a BMP one is not."""
    assert topics.request_key("U.S. x 中 \U00020000") == "\U00020000"
    assert topics.request_key("﨎﨎 \U00020000") == "\U00020000 﨎﨎"  # UTF-16 order, not code points


def test_words_that_a_vowel_sign_splits_into_single_letters_are_rejected(existing):
    """Under the web app's rule a combining mark other than U+0300-036F separates words, so "चीन" (China) leaves only
    one-letter tokens: an empty key, rejected; "चना" (chickpea) keeps "चन" before its final vowel sign (the
    closing-round-4 DECISION at `request_key`)."""
    assert (topics.request_key("चीन"), topics.request_key("चना")) == ("", "चन")
    china, chickpea = resolve([{"text": "चीन", "count": 2}, "चना"], existing)
    assert china["status"] == "rejected" and china["text"] == "चीन"
    assert china["reason"] == "nothing left after normalising (only stopwords, one-letter words and punctuation)"
    assert chickpea["status"] != "rejected" and chickpea["key"] == "चन" and chickpea["text"] == "चना"


def test_the_web_key_is_checked_against_the_contract_of_the_text_as_sent(existing):
    """The batch keys the text after deleting format characters, the web app does not: its key for "Ukr\\u00adaine war"
    is "aine ukr war", which is the contract and no mismatch; the batch still resolves the request as "ukraine war"."""
    text = "Ukr­aine war"
    assert topics.request_key(text) == "aine ukr war" and topics.request_key(topics._clean(text)) == "ukraine war"
    follows, differs = topics.resolve_requests([{"key": "aine ukr war", "text": text, "count": 1},
                                                {"key": "ukraine war", "text": text, "count": 1}], existing, propose=dry)
    assert (follows["status"], follows["topic_id"], follows["key"], follows["key_mismatch"]) == (
        "existing", "russia-ukraine-war", "aine ukr war", None)
    assert (differs["status"], differs["topic_id"], differs["key"], differs["key_mismatch"]) == (
        "existing", "russia-ukraine-war", "ukraine war", "aine ukr war")


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
        ("the and of", "nothing left after normalising (only stopwords, one-letter words and punctuation)", False),
        ("U.S. v. A", "nothing left after normalising (only stopwords, one-letter words and punctuation)", False),
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
        # dash-like separators, "/" and "_" between phone digits; 9+ digits in a run of digits and separators
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
        # closing round 2: the boundary of 9 digits in groups, and 9+ digits with no separator at all
        ("call 030 123456", "contains a phone number", True),  # 9 digits (a Berlin landline)
        ("06 12 34 56 78", "contains a phone number", True),  # 10 digits in 5 groups (a French mobile)
        ("call 07911123456", "contains a phone number", True),
        ("Jane 447911123456", "contains a phone number", True),
        ("call 01701234567", "contains a phone number", True),
        ("Ivan 123456789", "contains a phone number", True),
        # closing round 3: caught only by the 9-digit run check, and only because it scans the form with "/", "_" and
        # the dash-like characters turned into "-" (no North American, international or local shape matches these)
        ("call 0170/1234567", "contains a phone number", True),
        ("Ivan 030_123456", "contains a phone number", True),
        ("Jane 0170‐1234567", "contains a phone number", True),  # U+2010 hyphen
        ("call 030/123/456", "contains a phone number", True),
        ("Jane 0170−1234567", "contains a phone number", True),  # U+2212 minus sign
        # closing round 4: a local number glued to a word by "-", ".", "/", "_" or a dash, or before a full stop
        ("jane-555-1234", "contains a phone number", True),
        ("jane.555-1234", "contains a phone number", True),
        ("jane/555-1234", "contains a phone number", True),
        ("jane_555-1234", "contains a phone number", True),
        ("jane–555-1234", "contains a phone number", True),  # en dash
        ("jane‑555‑1234", "contains a phone number", True),  # non-breaking hyphens
        ("jane−555.1234", "contains a phone number", True),  # minus sign
        ("call 555-1234.", "contains a phone number", True),
        ("call 555.1234.", "contains a phone number", True),
        ("call jane 555-1234。", "contains a phone number", True),  # ideographic full stop (a "." when scanned)
        ("555-1234-jane", "contains a phone number", True),
        ("555-1234.jane", "contains a phone number", True),
        ("jane-555-1234.", "contains a phone number", True),
        ("call 1-555-1234", "contains a phone number", True),  # another digit group joined by a separator
        ("hotline 1.555.1234", "contains a phone number", True),
        ("call 555-1234-5", "contains a phone number", True),  # a local number and an extension
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
     "St. Louis floods", "\u6771\u4eac\u3002\u9078\u6319", "M\u00fcnchen Oktoberfest", "version 1.25 release",
     # closing round 2: 8 digits in a row stay acceptable (9 are a phone number, test_rejections)
     "population 33000000",
     # closing round 4: the local-number pattern ends where the digit groups end; dates, years, bill and section numbers
     # have no 3-and-4-digit group pair, also next to a full stop, a hyphen or a slash
     "election 2026-10-26", "summit on 2026-10-26.", "26.10.2026 vote", "2026.10.26 summit", "2026/10/26 strike",
     "1999-2000 recession", "fiscal year 2026-2027.", "elections in 2026.", "H.R. 4521", "H.R. 4521 vote.", "H.R.4521",
     "Section 301 tariffs", "Section 301.", "Area 51", "Area 51 leak.", "Area-51 files", "Boeing 737-800.",
     "COVID-19 2026.", "troop range 500-10000"],
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


def test_phone_numbers_without_separators_never_become_a_row(existing):
    """Before closing round 2 "call Jane 07911123456" became a `new` row named "Call Jane 07911123456"; "call
    0170/1234567" and "Ivan 030_123456" are caught only because the run check scans the separator-converted form."""
    texts = ["call Jane 07911123456", "John Smith 01701234567", "Ivan 123456789", "call 0170/1234567", "Ivan 030_123456"]
    res = resolve(texts, existing)
    assert [r["status"] for r in res] == ["rejected"] * len(texts)
    assert all(r["text"] == r["key"] == topics.WITHHELD and r["reason"] == "contains a phone number" for r in res)
    sql = topics.rows_sql(res)
    assert sql.count("INSERT") == 0 and not any(d in sql for d in ("07911123456", "01701234567", "123456789", "1234567", "123456"))


def test_local_phone_numbers_glued_to_a_word_never_become_a_row(existing):
    """Before closing round 4 these were `new` rows named "Jane-555-1234" or "Call Jane 555-1234." (the local-number
    guard refused any "-" or "." next to the number, so a word joined by one, or a closing full stop, hid it)."""
    texts = ["jane-555-1234", "Jane Doe/555-1234", "call jane 555-1234.", "Jane_555.1234 Mars", "555-1234-jane"]
    res = resolve(texts, existing)
    assert [r["status"] for r in res] == ["rejected"] * len(texts)
    assert all(r["text"] == r["key"] == topics.WITHHELD and r["reason"] == "contains a phone number" for r in res)
    out = json.dumps(res) + topics.rows_sql(res)
    assert "INSERT" not in out and "1234" not in out and "jane" not in out.lower()


@pytest.mark.parametrize(
    "web_key, text, status",
    [
        ("john.doe@example.com +1 555 123 4567", "Iran", "new"),
        ("call 555-123-4567 john@x.org", "", "rejected"),
        ("jane doe 0170 1234567", "Iran", "new"),
        ("jаnedoe.com/profile", "Iran", "new"),
        ("k" * 5000, "Iran", "new"),
        ("k" * 81, "Iran", "new"),
        # closing round 2: personal data that shows only in the NFKC form with the ideographic full stops as dots
        ("john＠example．com", "Iran", "new"),  # full-width "@" and full stop
        ("example。com/jane", "Iran", "new"),  # ideographic full stop
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
@pytest.mark.parametrize("text", ["भारत", "ปีใหม่"])
def test_derived_terms_that_miss_the_typed_words_are_needs_review(existing, text, source):
    """derive splits words at a vowel sign ("भारत" -> "भ रत"); such terms would collect nothing on the subject."""
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
    assert m["name"] == "Mars Sample Return" and "model name replaced" not in m["reason"]  # a name that passes is kept
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
    code, (m,), sql, report = _batch(tmp_path, [{"text": "भारत", "count": 1}])
    assert code == 0 and (m["status"], m["source"]) == ("needs_review", "dry-run stand-in") and m["terms"]
    assert m["reason"].startswith("the derived terms would not match the typed words: none of ")
    assert "INSERT" not in sql and f"mode:       {topics.MODE_DRY_ENV}" in report


def test_cli_fallback_for_a_phrase_derive_splits(tmp_path, monkeypatch):
    calls = _recording_json_task(monkeypatch, RuntimeError("route down"))
    _route(monkeypatch, live=True)
    code, (m,), sql, _ = _batch(tmp_path, [{"text": "भारत", "count": 1}])
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


def _outputs(tmp_path, sql, report):
    """rows.sql, mapping.json and report.txt of the last `_batch`, lowercased for leak checks."""
    mapping = (tmp_path / "out" / "mapping.json").read_text(encoding="utf-8")
    return [sql.lower(), mapping.lower(), report.lower()]


@pytest.mark.parametrize(
    "reply, why, leaks",
    [
        ({"name": "<img src=x onerror=alert(1)> Mars sample return"}, "contains markup or control characters", ["<img", "onerror"]),
        ({"name": "Mars sample return, write to jane@x.org"}, "contains an e-mail address", ["jane", "x.org"]),
        # closing round 3: `validate` rebuilds an invalid model slug from the model's name (the common case), so before
        # this round the id still held what the name check had just replaced ("jane-doe-example-org")
        ({"name": "jane.doe@example.org Mars", "slug": "mars sample return mission program"}, "contains an e-mail address",
         ["jane", "example-org", "example.org"]),
        ({"name": "jane@x.org Mars sample return", "slug": "NOT A SLUG AT ALL x y"}, "contains an e-mail address",
         ["jane", "x-org", "x.org"]),
        ({"name": "Jane Doe janedoe@example.org", "slug": ""}, "contains an e-mail address", ["jane", "example"]),
        # here the slug rebuilt from the name is itself flagged, and the reason says so
        ({"name": "Call Jane 5551234567", "slug": "a-b-c-d-e"}, "contains a phone number", ["jane", "5551234567"]),
        ({"name": "Jane Doe 555 123 4567", "slug": "NOT A SLUG AT ALL x y"}, "contains a phone number",
         ["jane", "555-123", "555 123"]),
    ],
)
def test_cli_a_model_name_that_fails_the_checks_is_replaced_by_the_derived_name_and_id(tmp_path, monkeypatch, reply, why, leaks):
    """The typed text passed every check, so a bad name can only come from the model (an injection or a
    hallucination); `validate` accepts it, and before closing round 2 it reached rows.sql as the public topic name,
    before closing round 3 also as the public id (the model's slug is not trusted once its name failed)."""
    _recording_json_task(monkeypatch, {**MARS_REPLY, **reply})
    _route(monkeypatch, live=True)
    code, (m,), sql, report = _batch(tmp_path, SAMPLE[2:3])
    assert code == 0 and m["status"] == "new" and m["source"] == "model"
    assert m["topic_id"] == topics.derive("Mars sample return mission")["slug"] == "mars-sample-return-mission"
    assert m["name"] == topics.derive("Mars sample return mission")["name"] == "Mars Sample Return Mission"
    slug_why = "contains a phone number" if "5551234567" in reply["name"] else "it may be built from the replaced name"
    assert m["reason"].endswith(f"; model name replaced: {why}; model slug replaced: {slug_why}")
    assert m["terms"] == ["mars sample return", "MSR", "perseverance"]
    assert "VALUES ('mars-sample-return-mission', 'Mars Sample Return Mission'," in sql and sql.count("INSERT INTO topics") == 1
    for out in _outputs(tmp_path, sql, report):
        assert not [leak for leak in leaks if leak.lower() in out]


@pytest.mark.parametrize("slug", ["call-jane-555-1234567", "jane-doe-5551234567", "jane-555-123-4567", "call-jane-5551234567",
                                  "555-1234",
                                  # closing round 4: a local number joined to the words by the slug's own hyphens
                                  "call-jane-555-1234", "jane-doe-555-1234", "555-1234-jane"])
def test_cli_a_model_slug_that_may_carry_personal_data_is_replaced_by_the_derived_id(tmp_path, monkeypatch, slug):
    """A valid model slug was used as the id unchecked before closing round 3; a hyphen counts as a phone separator."""
    _recording_json_task(monkeypatch, {**MARS_REPLY, "slug": slug})
    _route(monkeypatch, live=True)
    code, (m,), sql, report = _batch(tmp_path, SAMPLE[2:3])
    assert code == 0 and m["status"] == "new" and m["source"] == "model" and m["topic_id"] == "mars-sample-return-mission"
    assert m["name"] == "Mars Sample Return" and "model name replaced" not in m["reason"]  # a name that passes is kept
    assert m["reason"].endswith("; model slug replaced: contains a phone number")
    assert "VALUES ('mars-sample-return-mission', 'Mars Sample Return'," in sql
    groups = [g for g in re.findall(r"\d+", slug) if len(g) >= 4]
    for out in _outputs(tmp_path, sql, report):
        assert slug not in out and "jane" not in out and not [g for g in groups if g in out]


def test_cli_model_terms_that_may_carry_personal_data_are_withheld(tmp_path, monkeypatch):
    """Before closing round 3 a model term "call jane 5551234567" passed normalize_term (digits and spaces are allowed)
    and went into query_terms, mapping.json and report.txt; the model's clean slug and name are kept."""
    terms = ["Mars sample return", "MSR", "jane doe 5551234567", "call jane 5551234567", "555 123 4567", "Perseverance"]
    _recording_json_task(monkeypatch, {**MARS_REPLY, "terms": terms})
    _route(monkeypatch, live=True)
    code, (m,), sql, report = _batch(tmp_path, SAMPLE[2:3])
    assert code == 0 and m["status"] == "new" and m["source"] == "model"
    assert (m["topic_id"], m["name"]) == ("mars-sample-return", "Mars Sample Return")
    assert m["terms"] == ["mars sample return", "MSR", "perseverance"]
    assert m["reason"].endswith("; 3 proposed terms withheld: may carry personal data") and "replaced" not in m["reason"]
    assert "ARRAY['mars sample return', 'MSR', 'perseverance']" in sql
    for out in _outputs(tmp_path, sql, report):
        assert "jane" not in out and "5551234567" not in out and "555 123 4567" not in out


def test_a_proposed_term_with_personal_data_is_withheld_before_the_term_rules(existing):
    """"jane@x.org" breaks the term rules, whose "too generic, dropped" list echoes the raw term: it is withheld first."""
    (r,) = resolve(["measles cases"], existing, propose=model_row(["measles cases", "jane@x.org", "it"]))
    assert r["status"] == "new" and r["terms"] == ["measles cases"]
    assert r["reason"].endswith("; too generic, dropped: 'it'; 1 proposed term withheld: may carry personal data")
    assert "jane" not in json.dumps(r) and "jane" not in topics.rows_sql([r])


def test_a_derived_slug_that_looks_like_a_phone_number_becomes_a_hashed_id(existing):
    """The typed text passes check_request (its digit groups are words apart), but slug_for drops the stopwords and
    puts 11 digits side by side; with no clean slug to fall back on, the id is `topic-<8 hex>`."""
    text = "2026 and 2027 and 100 plans"
    assert topics.check_request(text) == ("", False) and topics.derive(text)["slug"] == "2026-2027-100-plans"
    (r,) = resolve([text], existing)
    assert r["status"] == "new" and re.fullmatch(r"topic-[0-9a-f]{8}", r["topic_id"])
    assert r["reason"].endswith("; derived slug replaced: contains a phone number")
    (clean,) = resolve(["Mars sample return mission"], existing,
                       propose=lambda t: {**topics.derive(t), "slug": "call-jane-5551234567", "source": "derive"})
    assert clean["topic_id"] == "mars-sample-return-mission"
    assert clean["reason"].endswith("; derived slug replaced: contains a phone number")


@pytest.mark.parametrize(
    "text, slug",
    [
        ("Fortune 500 2026", "fortune-500-2026"), ("Section 230 2026", "section-230-2026"),
        ("Boeing 737 2026", "boeing-737-2026"), ("Top 100 2026", "top-100-2026"),
        ("Section 230 2026 repeal", "section-230-2026-repeal"), ("S&P 500 2026 outlook", "s-p-500-2026"),
        ("MH370 2025 search", "mh370-2025-search"), ("Microsoft 365 2026 outage", "microsoft-365-2026-outage"),
        ("Interstate 405 2026 closure", "interstate-405-2026-closure"), ("Ford F-150 2026 recall", "ford-f-150-2026"),
        ("Route 128 in 2025", "route-128-2025"), ("Airbus A380 2026", "airbus-a380-2026"),
    ],
)
def test_a_derived_slug_reads_its_hyphens_as_the_typed_spaces(existing, text, slug):
    """Closing round 5: derive's slug joins the typed words with "-", and the as-is scan read "500-2026" as a local
    phone number, so these accepted texts got `topic-<8 hex>` and a reason saying the slug held a phone number."""
    assert topics.check_request(text) == ("", False) and topics.derive(text)["slug"] == slug
    (r,) = resolve([text], existing)
    assert r["status"] == "new" and r["topic_id"] == slug
    assert "slug replaced" not in r["reason"] and "phone" not in r["reason"]


def test_cli_a_dry_run_keeps_readable_ids_for_numbered_topics(tmp_path):
    """The rehearsal dry run of closing round 4 wrote INSERT … ('topic-6075d419', 'Fortune 500 2026', …)."""
    code, res, sql, _ = _batch(tmp_path, [{"key": topics.request_key(t), "text": t, "count": 1}
                                          for t in ("Fortune 500 2026", "Section 230 2026")], "--dry-run")
    assert code == 0 and [(r["status"], r["topic_id"]) for r in res] == [("new", "fortune-500-2026"), ("new", "section-230-2026")]
    assert "VALUES ('fortune-500-2026', 'Fortune 500 2026'," in sql and "VALUES ('section-230-2026', 'Section 230 2026'," in sql
    assert "topic-" not in sql


def test_three_and_four_digits_typed_with_a_space_count_alike_in_the_name_and_the_id(existing):
    """The closing-round-5 DECISION at `_slug_personal_data`, (1): "555 1234" typed with a space is not a phone number
    (it cannot be told apart from "Fortune 500 2026"), so the name and the id keep the same digits; before, the name
    kept them and the id was `topic-<8 hex>` with a reason saying the slug held a phone number."""
    for text, slug in (("Jane Doe 555 1234", "jane-doe-555-1234"), ("call jane 555 1234", "call-jane-555-1234")):
        assert topics.check_request(text) == ("", False)
        (r,) = resolve([text], existing)
        assert (r["status"], r["name"], r["topic_id"]) == ("new", topics.derive(text)["name"], slug)
        assert "slug replaced" not in r["reason"]


@pytest.mark.parametrize("model_slug", ["fortune-500-2026-list", "fortune-500-2026s"])
def test_a_flagged_model_slug_falls_back_to_the_derived_slug_read_the_derive_way(existing, model_slug):
    """A model's slug is scanned as it is ("500-2026" counts), and its replacement, derive's slug of the typed text, is
    checked with its hyphens read as spaces, so the id stays readable instead of `topic-<8 hex>`."""
    (r,) = resolve(["Fortune 500 2026"], existing, propose=model_row(["Fortune 500"], slug=model_slug))
    assert r["status"] == "new" and r["topic_id"] == "fortune-500-2026"
    assert r["reason"].endswith("; model slug replaced: contains a phone number")


def test_a_model_slug_equal_to_the_derived_slug_is_read_the_derive_way(existing):
    (r,) = resolve(["Fortune 500 2026"], existing, propose=model_row(["Fortune 500"], slug="fortune-500-2026"))
    assert (r["status"], r["topic_id"], r["source"]) == ("new", "fortune-500-2026", "model") and "replaced" not in r["reason"]
    (jane,) = resolve(["Mars sample return"], existing, propose=model_row(["Mars sample return"], slug="jane-doe-555-1234"))
    assert jane["topic_id"] == "mars-sample-return" and jane["reason"].endswith("; model slug replaced: contains a phone number")


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
