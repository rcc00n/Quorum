"""The official-document seed rule (2026-10-26, Yelysei): an official document seeds an event only when a term of the
run's topic matches its title or abstract, with collection's whole-word, case-insensitive matcher; otherwise it is
evidence only. Decision: docs/DECISIONS.md › Sources; code: quorum_reasoning/topic_match.py, nodes/plan.py
(apply_seed_rule), nodes/cluster.py, tools/corpus.py (load_topic_terms)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from quorum_reasoning import topic_match
from quorum_reasoning.nodes import cluster, plan, research
from quorum_reasoning.state import DocRef, initial_state
from quorum_reasoning.tools import corpus

TOPIC, DAY = "ai-regulation-export-controls", "2026-10-26"

# (text, terms, matches_topic) — pinned on collection's semantics (collectors/common.py, data-collection 2026-10-25)
MATCH_VECTORS = [
    ("Ukraine war update", ["Ukraine"], True),
    ("UKRAINE talks", ["ukraine"], True),
    ("Ukrainian forces advance", ["Ukraine"], False),  # whole word: no stemming, no prefix match
    ("New export controls on chips", ["export controls"], True),
    ("export-controls regime", ["export controls"], False),
    ("export\ncontrols", ["export controls"], False),  # a phrase needs its literal space (the abstract collapses whitespace first)
    ("The AI act passed", ["AI act"], True),
    ("The AI will act on it", ["AI act"], False),  # a phrase, not the implicit AND of the Federal Register search
    ("the price raids", ["ICE raids"], False),
    ("ICE raids in Chicago", ["ICE raids"], True),
    ("Section 301 action", ["section 301"], True),
    ("C++ rules", ["C++"], False),  # \b after a non-word character needs a word character next: collection's quirk, kept
    ("Zürich climate strike", ["zürich"], True),
    ("Zürichsee shore", ["Zürich"], False),
    ("Выборы в Молдове прошли", ["Молдове"], True),  # Unicode word characters count for \b
    ("молдовеские новости", ["Молдове"], False),
    ("", ["Ukraine"], False),
    (None, ["Ukraine"], False),
    ("Ukraine", [], False),
]

# (title, lead, terms, topic_match_of)
WHERE_VECTORS = [
    ("Ukraine aid bill", "Senate votes", ["Ukraine"], "title"),
    ("Senate votes", "on Ukraine aid", ["Ukraine"], "lead"),
    ("Senate votes", "on farm aid", ["Ukraine"], None),
    ("Senate votes", None, ["Ukraine"], None),
    ("Senate votes", "", ["Ukraine"], None),
    ("Kyiv strike", "Ukraine says", ["Kyiv", "Ukraine"], "title"),
]


def test_matcher_vectors_pin_collections_semantics():
    for text, terms, expected in MATCH_VECTORS:
        assert topic_match.matches_topic(text, terms) is expected, (text, terms)
    for title, lead, terms, expected in WHERE_VECTORS:
        assert topic_match.topic_match_of(title, lead, terms) == expected, (title, lead, terms)


def test_first_topic_match_keeps_collection_order():
    topics = [{"id": "a", "query_terms": ["tariffs"]}, {"id": "b", "query_terms": ["Ukraine", "tariffs"]}]
    assert topic_match.first_topic_match("Tariffs on Ukraine steel", None, topics) == (topics[0], "title")
    assert topic_match.first_topic_match("Steel", "Ukraine steel", topics) == (topics[1], "lead")
    assert topic_match.first_topic_match("Steel", "Steel", topics) == (None, None)


def _collectors_common():
    repo = Path(__file__).resolve().parents[2]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    return pytest.importorskip("collectors.common")


def test_copy_agrees_with_collectors_common_when_it_can_be_imported():
    common = _collectors_common()
    for text, terms, _ in MATCH_VECTORS:
        assert topic_match.matches_topic(text, terms) is common.matches_topic(text, terms), (text, terms)
    for title, lead, terms, _ in WHERE_VECTORS:
        assert topic_match.topic_match_of(title, lead, terms) == common.topic_match_of(title, lead, terms)
    if hasattr(common, "first_topic_match"):  # data-collection has it; an older collectors/ copy may not
        topics = [{"id": "a", "query_terms": ["tariffs"]}, {"id": "b", "query_terms": ["Ukraine"]}]
        for title, lead in (("Tariffs", None), ("x", "Ukraine"), ("x", "y")):
            assert topic_match.first_topic_match(title, lead, topics) == common.first_topic_match(title, lead, topics)


# --- query_terms as Zetaris delivers it ----------------------------------------------------------------------

# the exact strings Zetaris returned for the rehearsal dump of 2026-10-26 (QUORUM_COLLECT.topics)
ZETARIS_TERMS = {
    "russia-ukraine-war": ("{Ukraine,Zelensky,Zelenskyy,Kyiv,Ukrainian}", ["Ukraine", "Zelensky", "Zelenskyy", "Kyiv", "Ukrainian"]),
    "ai-regulation-export-controls": (
        '{"artificial intelligence","AI regulation","AI act","AI safety","chip export controls","export controls","AI chips",'
        '"nvidia chips","AI executive order","AI legislation","frontier models","data centers",semiconductors}',
        ["artificial intelligence", "AI regulation", "AI act", "AI safety", "chip export controls", "export controls", "AI chips",
         "nvidia chips", "AI executive order", "AI legislation", "frontier models", "data centers", "semiconductors"],
    ),
    "climate-policy": (
        '{climate,emissions,carbon,"clean energy",renewable,renewables,"Paris Agreement","net zero",greenhouse,decarbonization}',
        ["climate", "emissions", "carbon", "clean energy", "renewable", "renewables", "Paris Agreement", "net zero", "greenhouse", "decarbonization"],
    ),
}


def test_query_terms_parse_the_shapes_zetaris_returns():
    for raw, expected in ZETARIS_TERMS.values():
        assert topic_match.parse_query_terms(raw) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("{}", []),
        ("{ }", []),
        ('{ " a b " , c }', ["a b", "c"]),
        ("{NULL,x}", ["x"]),
        ('{"say \\"hi\\"",x}', ['say "hi"', "x"]),
        ('{"Côte d\'Ivoire",Zürich,"Выборы в Молдове"}', ["Côte d'Ivoire", "Zürich", "Выборы в Молдове"]),
        ('["a", "b c"]', ["a", "b c"]),
        ("['a', 'b c']", ["a", "b c"]),
        (["a", " ", "b "], ["a", "b"]),
        (("a",), ["a"]),
        (None, None),
        ("", None),
        ("None", None),
        ("a,b", None),  # not an array literal: unreadable, not guessed
        ("{a,}", None),
        ('{"a}', None),
        ("{{a,b}}", None),
        ('{"a"b}', None),
        ("[1, 2]", None),
        ("[oops", None),
        (42, None),
        (["a", 3], None),
    ],
)
def test_query_terms_parser_edge_cases(value, expected):
    assert topic_match.parse_query_terms(value) == expected


# --- the abstract of an official document -----------------------------------------------------------------

FR_RULE = """<html>
<head>
<title>Federal Register, Volume 91 Issue 205 (Monday, October 26, 2026)</title>
</head>
<body><pre>
[Federal Register Volume 91, Number 205 (Monday, October 26, 2026)]
[Rules and Regulations]
[Pages 1-2]
From the Federal Register Online via the Government Publishing Office [<a href="http://www.gpo.gov">www.gpo.gov</a>]
[FR Doc No: 2026-00001]


-----------------------------------------------------------------------

DEPARTMENT OF EXAMPLES

Example Regulatory Program

AGENCY: Office of Examples.

ACTION: Final rule.

-----------------------------------------------------------------------

SUMMARY: The Office approves rules on chip export
controls &amp; reporting for <b>data centers</b>.

DATES: The effective date is November 25, 2026.

SUPPLEMENTARY INFORMATION: artificial intelligence is mentioned only down here.
</pre></body></html>"""

FR_NO_SUMMARY = """<html><body><pre>
[Federal Register Volume 91, Number 205 (Monday, October 26, 2026)]
[Notices]
[Pages 3-4]
From the Federal Register Online via the Government Publishing Office [<a href="http://www.gpo.gov">www.gpo.gov</a>]
[FR Doc No: 2026-00002]


=======================================================================
-----------------------------------------------------------------------

LEGAL SERVICES EXAMPLE

Sunshine Act Meetings

TIME AND DATE: The Board meets on Friday.
</pre></body></html>"""


def test_abstract_is_the_federal_register_summary_paragraph():
    a = topic_match.official_abstract(FR_RULE)
    assert a == "The Office approves rules on chip export controls & reporting for data centers ."
    assert topic_match.matches_topic(a, ["chip export controls"]) and topic_match.matches_topic(a, ["data centers"])
    assert not topic_match.matches_topic(a, ["artificial intelligence"])  # a body-only term is not in the abstract


def test_a_federal_register_document_without_a_summary_has_no_abstract():
    # the Federal Register API's abstract is null for these documents: they are matched on their title alone
    assert topic_match.official_abstract(FR_NO_SUMMARY) == ""  # recognised by its page header
    assert topic_match.official_abstract("TIME AND DATE: Friday.", "federal-register") == ""  # or by its source
    assert topic_match.official_abstract(FR_NO_SUMMARY, "whitehouse") == ""  # the header wins over a mislabelled source
    assert topic_match.official_abstract(FR_RULE, "federal-register").startswith("The Office approves rules")


def test_other_sources_fall_back_to_the_first_600_characters():
    long = "First Lady secures ceasefire in Oleshky. " + "More words follow here. " * 60
    b = topic_match.official_abstract(long, "whitehouse")
    assert len(b) == topic_match.LEAD_MAX and b.startswith("First Lady secures ceasefire")
    bill = "Expressing support for the withdrawal of the United States from the Paris Agreement.\n\nLatest action (2025-04-21): Referred to the House Committee on Foreign Affairs.\n\n"
    assert topic_match.official_abstract(bill, "congress-gov") == " ".join(bill.split())
    assert topic_match.official_abstract(None) == "" and topic_match.official_abstract("") == ""


def test_a_summary_word_inside_a_sentence_is_not_a_heading():
    text = "The report says SUMMARY: nothing here. Ukraine is mentioned in passing."
    assert topic_match.official_abstract(text) == text  # no SUMMARY heading at a line start: the first 600 characters


# An executive order as the Federal Register prints it (official_docs 5934, tariffs-trade-war-china): no SUMMARY, and
# its opening is the enacting clause, which cites "section 301 of title 3" (the President's delegation statute).
FR_ORDER = """<html><body><pre>
[Federal Register Volume 91, Number 167 (Monday, August 31, 2026)]
[Presidential Documents]
[Pages 55995-55999]
From the Federal Register Online via the Government Publishing Office [<a href="http://www.gpo.gov">www.gpo.gov</a>]
[FR Doc No: 2026-17843]




                        Presidential Documents



Federal Register / Vol. 91 , No. 167 / Monday, August 31, 2026 /
Presidential Documents

[[Page 55995]]


                Executive Order 14421 of August 26, 2026


Declaring a National Emergency To Secure the
                United States Bulk-Power System

                By the authority vested in me as President by the
                Constitution and the laws of the United States of
                America, including the International Emergency Economic
                Powers Act (50 U.S.C. 1701 et seq.) (IEEPA), the
                National Emergencies Act (50 U.S.C. 1601 et seq.)
                (NEA), and section 301 of title 3, United States Code,
                I hereby determine and order:

                Section 1. National Emergency. As President of the
                United States, my highest duty is protecting the
                national security of this country.
</pre></body></html>"""

# The issue's cover page opens a presidential document (official_docs 5942): the titles of the other documents of the
# same Part, one of them naming a term another topic could carry.
FR_COVER = """<html><body><pre>
[Federal Register Volume 91, Number 153 (Tuesday, August 11, 2026)]
[Presidential Documents]
[Pages 51975-51987]
From the Federal Register Online via the Government Publishing Office [<a href="http://www.gpo.gov">www.gpo.gov</a>]
[FR Doc No: 2026-16400]



[[Page 51973]]

Vol. 91

Tuesday,

No. 153

August 11, 2026

Part V





The President





-----------------------------------------------------------------------



Proclamation 11052--Adjusting Imports of Polysilicon and Its
Derivatives Into the United States



Executive Order 14419--Ending Birth Tourism


___________________________________________________________________

Title 3--
The President

[[Page 51975]]

                Proclamation 11052 of August 6, 2026

Adjusting Imports of Polysilicon and Its
                Derivatives Into the United States
</pre></body></html>"""

# A Sunshine Act notice (official_docs 6215, federal-budget-shutdown): no SUMMARY, an agenda with meeting dates
FR_SUNSHINE = FR_NO_SUMMARY.replace("TIME AND DATE: The Board meets on Friday.", "DATES AND TIME: Every second Wednesday through Fiscal \nYear 2027.")

# The same kind of order as a White House release (official_docs 5898): no page header, the enacting clause first
WH_ORDER = (
    "Executive Order 14436\n\nBy the authority vested in me as President by the Constitution and the laws of the United States of America, "
    "including the Lindsey O. Graham Sanctioning Russia and Iran Act of 2026 (22 U.S.C. 10802 et seq . ) (Graham Act), and section 301 "
    "of title 3, United States Code, I hereby determine and order:\n\nSection 1 . Background . On September 18, 2026, I signed the Graham "
    "Act into law. The Graham Act provides for duties on goods imported from the Russian Federation.\n"
)


def _doc(title: str, text: str, source: str = "federal-register") -> dict:
    return {"title": title, "lead": "", "text": text, "source_id": source}


@pytest.mark.parametrize("source", ["federal-register", None])
def test_an_order_printed_in_the_federal_register_is_matched_on_its_title_only(source):
    title = "Declaring a National Emergency To Secure the United States Bulk-Power System"
    assert topic_match.official_abstract(FR_ORDER, source) == ""
    assert topic_match.official_seed_match(_doc(title, FR_ORDER, source), ["section 301"]) is None  # the enacting clause seeds nothing
    assert topic_match.official_seed_match(_doc(title, FR_ORDER, source), ["bulk-power system"]) == "title"


def test_the_cover_page_list_of_other_documents_seeds_nothing():
    title = "Adjusting Imports of Polysilicon and Its Derivatives Into the United States"
    assert topic_match.official_seed_match(_doc(title, FR_COVER), ["birth tourism"]) is None  # another document's title
    assert topic_match.official_seed_match(_doc(title, FR_COVER), ["polysilicon"]) == "title"


def test_a_meeting_agenda_without_a_summary_seeds_nothing():
    assert topic_match.official_seed_match(_doc("Sunshine Act Meetings Notice", FR_SUNSHINE), ["fiscal year"]) is None
    headerless = "DATES AND TIME: Every second Wednesday through Fiscal Year 2027."  # the row's source alone says Federal Register
    assert topic_match.official_seed_match(_doc("Sunshine Act Meetings Notice", headerless), ["fiscal year"]) is None
    assert topic_match.official_seed_match(_doc("Board notice", headerless, "congress-gov"), ["fiscal year"]) == "lead"


def test_a_white_house_order_loses_its_enacting_clause_but_keeps_its_text():
    a = topic_match.official_abstract(WH_ORDER, "whitehouse")
    assert a.startswith("Executive Order 14436 Section 1 . Background . On September 18, 2026")
    assert "authority vested" not in a and "title 3" not in a
    title = "Implementing the Lindsey O. Graham Sanctioning Russia and Iran Act of 2026"
    assert topic_match.official_seed_match(_doc(title, WH_ORDER, "whitehouse"), ["section 301"]) is None
    assert topic_match.official_seed_match(_doc(title, WH_ORDER, "whitehouse"), ["Russian Federation"]) == "lead"


def test_only_the_enacting_clause_up_to_its_colon_is_dropped():
    proclaim = ("NOW, THEREFORE, I, the President, by virtue of the authority vested in me by the Constitution and the laws of the "
                "United States, do hereby proclaim November 2026 as National Ukraine Remembrance Month.")
    assert topic_match.official_abstract(proclaim, "whitehouse") == proclaim  # a proclamation's operative sentence stays
    no_colon = "By the authority vested in me as President, I order a review of Ukraine aid.\n\nSection 2. More."
    assert topic_match.official_abstract(no_colon, "whitehouse") == "By the authority vested in me as President, I order a review of Ukraine aid. Section 2. More."


FR_SUMMARY_ACROSS_A_PAGE = """[FR Doc No: 2026-15000]

SUMMARY: FRA proposes that each railroad carrier conducting a
triennial examination of skill performance, and an annual

[[Page 48346]]

operational monitoring observation, conduct those examinations. FRA
proposes to codify limitations on operations at the southern border.

DATES: Written comments must be received on or before September 29,
2026.
"""


def test_a_summary_crossing_a_page_break_is_read_whole():
    a = topic_match.official_abstract(FR_SUMMARY_ACROSS_A_PAGE, "federal-register")
    assert "and an annual operational monitoring observation" in a and "[[Page" not in a
    assert a.endswith("limitations on operations at the southern border.") and "Written comments" not in a
    title = "Qualification and Certification of Locomotive Engineers and Conductors"
    assert topic_match.official_seed_match(_doc(title, FR_SUMMARY_ACROSS_A_PAGE), ["southern border"]) == "lead"


def test_a_page_break_just_before_the_dates_heading_keeps_dates_out_of_the_abstract():
    text = "SUMMARY: The rule is short.\n\n[[Page 2]]\n\nDATES: Comments on Ukraine are due in November.\n"
    assert topic_match.official_abstract(text, "federal-register") == "The rule is short."
    assert topic_match.official_seed_match(_doc("Example rule", text), ["Ukraine"]) is None


# --- the seed flags -----------------------------------------------------------------------------------------


def _official(doc_id: int, title: str, text: str, *, previous: bool = False, doc_type: str = "release") -> DocRef:
    d = DocRef(id=corpus.OFFICIAL_ID_OFFSET + doc_id, source_id="federal-register", source_name="Federal Register", independence_group="federal-register",
               kind="official", flank=None, tier=None, url=f"https://www.federalregister.gov/d/{doc_id}", title=title, lead="",
               published_at="2026-10-26T00:00:00Z", access_level=1, wire_origin=None, official=True, doc_type=doc_type, text=text)
    if previous:
        d["from_previous_day"] = True
    return d


def _outlet(doc_id: int, title: str, lead: str = "", source: str = "cnn") -> DocRef:
    return DocRef(id=doc_id, source_id=source, source_name=source.upper(), independence_group=source, kind="outlet", flank="left", tier="major",
                  url=f"https://example.org/{source}/{doc_id}", title=title, lead=lead, published_at="2026-10-25T20:00:00Z", access_level=2, wire_origin=None)


TERMS = ZETARIS_TERMS[TOPIC][1]


def _day() -> list[DocRef]:
    return [
        _outlet(1, "Commerce tightens AI chips rules", "New export controls target advanced semiconductors."),
        _outlet(2, "Lawmakers debate AI chips export limits", "Senators weigh new export controls.", source="foxnews"),
        _official(10, "Export Controls on Advanced Computing Items", "SUMMARY: BIS revises rules.\n"),  # title: "export controls"
        _official(11, "Example Regulatory Program", FR_RULE, doc_type="law"),  # abstract: "chip export controls", "data centers"
        _official(12, "Ohio Regulatory Program", "SUMMARY: OSM approves an amendment to the Ohio program.\n\nSUPPLEMENTARY: artificial intelligence.", doc_type="law"),
        _official(13, "Privacy Act of 1974; System of Records", "SUMMARY: A new system of records.\n", previous=True),
    ]


def test_seed_flags_mark_title_abstract_and_evidence_only_official_documents():
    docs = _day()
    before = [dict(d) for d in docs]
    out, counts = topic_match.official_seed_flags(docs, TERMS)
    assert docs == before, "the caller's dicts are never mutated"
    by_id = {d["id"]: d for d in out}
    off = corpus.OFFICIAL_ID_OFFSET
    assert by_id[off + 10]["seed_match"] == "title" and by_id[off + 10]["evidence_only"] is False
    assert by_id[off + 11]["seed_match"] == "lead" and by_id[off + 11]["evidence_only"] is False
    assert by_id[off + 12]["seed_match"] is None and by_id[off + 12]["evidence_only"] is True  # body-only term
    assert "evidence_only" not in by_id[off + 13] and "seed_match" not in by_id[off + 13]  # an earlier day is never an event anyway
    assert "evidence_only" not in by_id[1] and "seed_match" not in by_id[1]  # outlet documents are never filtered
    assert counts == {"official": 3, "title": 1, "lead": 1, "evidence_only": 1}


@pytest.mark.parametrize("terms", [None, []])
def test_unknown_terms_make_every_official_document_evidence_only(terms):
    out, counts = topic_match.official_seed_flags(_day(), terms)
    assert counts == {"official": 3, "title": 0, "lead": 0, "evidence_only": 3}
    assert all(d["evidence_only"] for d in out if d.get("official") and not d.get("from_previous_day"))


def test_a_lead_carried_by_an_official_row_is_used_as_its_abstract():
    d = _official(20, "Notice", "SUMMARY: nothing on topic.\n")
    d["lead"] = "Rules for AI chips."
    assert topic_match.official_seed_match(d, TERMS) == "lead"


# --- loading the topic's terms through Zetaris ---------------------------------------------------------------


def _topics_sql(rows=None, exc=None):
    seen: list[str] = []

    def fake(sql, limit):
        seen.append(sql)
        if exc:
            raise exc
        return list(rows or [])

    return fake, seen


def test_load_topic_terms_reads_and_parses_the_row(monkeypatch):
    fake, seen = _topics_sql([{"id": TOPIC, "name": "AI Regulation and Chip Export Controls", "query_terms": ZETARIS_TERMS[TOPIC][0]}])
    monkeypatch.setattr(corpus, "_run_sql", fake)
    terms, why, failed = corpus.load_topic_terms(TOPIC)
    assert terms == TERMS and not failed and why == "13 query terms from QUORUM_COLLECT.topics"
    assert seen == [f"SELECT id, name, query_terms FROM QUORUM_COLLECT.topics WHERE id = '{TOPIC}'"]


@pytest.mark.parametrize(
    "rows, why",
    [
        ([], f"no topics row for {TOPIC}"),
        ([{"id": "other-topic", "query_terms": "{x}"}], f"no topics row for {TOPIC}"),  # a row for another slug is not ours
        ([{"id": TOPIC, "query_terms": "a,b"}], "query_terms unreadable"),
        ([{"id": TOPIC, "query_terms": None}], "query_terms unreadable"),
        ([{"id": TOPIC, "query_terms": "{}"}], "query_terms empty"),
    ],
)
def test_load_topic_terms_says_why_terms_are_unusable(monkeypatch, rows, why):
    fake, _ = _topics_sql(rows)
    monkeypatch.setattr(corpus, "_run_sql", fake)
    assert corpus.load_topic_terms(TOPIC) == (None, why, False)


def test_a_failed_lookup_is_reported_by_type_only(monkeypatch):
    fake, _ = _topics_sql(exc=RuntimeError("upstream detail internal-4242"))
    monkeypatch.setattr(corpus, "_run_sql", fake)
    terms, why, failed = corpus.load_topic_terms(TOPIC)
    assert terms is None and failed and why == "topics lookup failed (RuntimeError)"
    assert "4242" not in why


@pytest.mark.parametrize("bad", ["Ukraine War", "x'; DROP TABLE topics; --", "", "-lead", "a" * 65, "zürich"])
def test_a_bad_slug_never_reaches_sql(monkeypatch, bad):
    fake, seen = _topics_sql([])
    monkeypatch.setattr(corpus, "_run_sql", fake)
    with pytest.raises(ValueError):
        corpus.load_topic_terms(bad)
    assert seen == []


# --- plan: the trace row and the flags -------------------------------------------------------------------------


def _zetaris_state(docs: list[DocRef]):
    st = initial_state("t", TOPIC, DAY, dry_run=True)
    st["corpus"] = "zetaris"
    st["documents"] = docs
    return st


def test_plan_reports_total_seed_eligible_and_evidence_only(monkeypatch):
    monkeypatch.setattr(corpus, "load_topic_terms", lambda topic_id: (TERMS, "13 query terms from QUORUM_COLLECT.topics", False))
    out = plan.run(_zetaris_state(_day()))
    row = out["steps"][0]
    assert "official documents: 3 total, 2 seed-eligible (title 1 / abstract 1), 1 evidence only (no topic term in title or abstract)" in row["decision"]
    assert "official seed rule: a term of the topic in the title or abstract, whole word, any case (13 query terms" in row["reason"]
    assert out["errors"] == []
    flagged = [d for d in out["documents"] if d.get("evidence_only")]
    assert [d["title"] for d in flagged] == ["Ohio Regulatory Program"]


def test_plan_with_no_topics_row_seeds_no_official_document_and_says_so(monkeypatch):
    monkeypatch.setattr(corpus, "load_topic_terms", lambda topic_id: (None, f"no topics row for {topic_id}", False))
    out = plan.run(_zetaris_state(_day()))
    row = out["steps"][0]
    assert f"official documents: 3 total, 0 seed-eligible (title 0 / abstract 0), 3 evidence only (topic terms unavailable: no topics row for {TOPIC}; no official document seeds an event)" in row["decision"]
    assert out["errors"] == []  # a missing row is a state of the data, not a failure


def test_plan_with_a_failed_lookup_records_an_error(monkeypatch):
    monkeypatch.setattr(corpus, "load_topic_terms", lambda topic_id: (None, "topics lookup failed (RuntimeError)", True))
    out = plan.run(_zetaris_state(_day()))
    assert "3 evidence only (topic terms unavailable: topics lookup failed (RuntimeError)" in out["steps"][0]["decision"]
    assert [e["node"] for e in out["errors"]] == ["plan"] and "no official document seeds an event today" in out["errors"][0]["message"]


def test_plan_reads_no_terms_when_the_window_has_no_official_document(monkeypatch):
    def boom(topic_id):
        raise AssertionError("no lookup without an official document")

    monkeypatch.setattr(corpus, "load_topic_terms", boom)
    docs = [d for d in _day() if not d.get("official") or d.get("from_previous_day")]
    out = plan.run(_zetaris_state(docs))
    assert "official documents:" not in out["steps"][0]["decision"] and out["errors"] == []


def test_fixture_corpus_keeps_every_official_document_as_a_seed(monkeypatch):
    def boom(topic_id):
        raise AssertionError("the fixture corpus reads no topics row")

    monkeypatch.setattr(corpus, "load_topic_terms", boom)
    st = initial_state("t", TOPIC, DAY, dry_run=True)  # corpus fixture
    st["documents"] = _day()
    out = plan.run(st)
    assert "official documents: 3 total, all seed-eligible (fixture corpus: seed rule not applied)" in out["steps"][0]["decision"]
    assert not any("evidence_only" in d for d in out["documents"])


# --- cluster and research: an evidence-only document may join an event, never start one ------------------------


def test_an_evidence_only_document_in_no_event_stays_a_round_2_candidate():
    docs, _ = topic_match.official_seed_flags(_day(), TERMS)
    st = _zetaris_state(docs)
    out = cluster.run(st)
    off = corpus.OFFICIAL_ID_OFFSET
    members = {i for e in out["events"] for i in e["document_ids"]}
    assert off + 12 not in members  # the Ohio notice shares nothing with the day's chip stories: alone, so dropped
    assert off + 13 not in members  # earlier day, as before
    assert {off + 10, off + 11} <= members  # seed-eligible official documents still seed
    decision = out["steps"][0]["decision"]
    assert "(1 official documents evidence only by the seed rule, see plan: 0 joined an event, 1 in no event, 1 group(s) with no seed member dropped)" in decision
    assert decision.startswith("4 events from 4 documents (1 earlier-day documents held for evidence only)")
    st["events"] = out["events"]
    for e in out["events"]:
        pool = {d["id"] for d in research._candidates(st, e["document_ids"], 2)}
        assert off + 12 in pool, "research round 2 may still quote it"


def _key(title: str, *objects: str, action: str = "") -> dict:
    return {"canonical": title, "actors": [], "action": action, "object": list(objects), "place": [], "date": None, "numbers": []}


def _held(doc_id: int, title: str) -> DocRef:
    d = _official(doc_id, title, "")
    d["seed_match"], d["evidence_only"] = None, True
    return d


def _fake_model(monkeypatch, keys: dict[int, dict], same: set[frozenset]) -> list[tuple[str, list[str], list[str]]]:
    """Event keys by document id; a merge question answers yes when a title on one side and one on the other are a
    pair in `same`. Returns the questions asked as (mode, titles of side a, titles of side b)."""
    asked: list[tuple[str, list[str], list[str]]] = []

    def fake(task, payload, *, dry_run, which="default"):
        if task == "event_key":
            return keys[payload["id"]]
        assert task == "merge_confirm", task
        a, b = payload["a"], payload["b"]
        ta, tb = a.get("member_titles") or [a["title"]], b.get("member_titles") or [b["title"]]
        asked.append((payload["mode"], ta, tb))
        return {"same_event": any(frozenset((x, y)) in same for x in ta for y in tb)}

    monkeypatch.setattr(cluster.llm, "json_task", fake)
    return asked


OFF = corpus.OFFICIAL_ID_OFFSET


def test_an_evidence_only_document_joins_an_outlet_event_and_a_group_without_a_seed_is_dropped(monkeypatch):
    rule, ohio, sunshine, nasdaq, nyse, panel = (
        "Revisions to the Export Administration Regulations", "Ohio Regulatory Program", "Sunshine Act Meetings",
        "Nasdaq Texas filing", "NYSE Arca notice", "Closed meeting of the review panel",
    )
    docs = [
        _outlet(1, "Commerce adopts chip export rule"),
        _outlet(2, "Lawmakers question chip rule", source="foxnews"),
        _held(21, rule), _held(22, ohio), _held(23, sunshine), _held(24, sunshine), _held(25, sunshine),
        _held(26, nasdaq), _held(27, nyse), _held(28, panel),
    ]
    keys = {
        1: _key("Commerce adopts chip export rule", "commerce", "chip", "export", "rule", action="adopt"),
        2: _key("Lawmakers question chip rule", "lawmakers", "chip"),
        OFF + 21: _key(rule, "commerce", "export", "administration", "regulations", "entity", action="adopt"),
        OFF + 22: _key(ohio, "ohio", "program"),
        OFF + 23: _key(sunshine, "board", "meeting", "agenda"),
        OFF + 24: _key(sunshine, "board", "meeting", "agenda"),
        OFF + 25: _key(sunshine, "board", "meeting", "agenda"),
        OFF + 26: _key(nasdaq, "nasdaq", "filing", "exchange", "texas"),
        OFF + 27: _key(nyse, "nyse", "filing", "exchange", "arca", "listing"),
        OFF + 28: _key(panel, "meeting", "panel", "review", "grant"),
    }
    asked = _fake_model(monkeypatch, keys, {frozenset(("Commerce adopts chip export rule", rule))})
    out = cluster.run(_zetaris_state(docs))
    groups = sorted(sorted(e["document_ids"]) for e in out["events"])
    assert groups == [[1, OFF + 21], [2]], "the rule joins the outlet event that reports it; nothing else becomes an event"
    held_titles = {rule, ohio, sunshine, nasdaq, nyse, panel}
    assert asked and all(not (set(a) <= held_titles and set(b) <= held_titles) for _, a, b in asked), "no question without a seed side"
    assert ("pair", ["Commerce adopts chip export rule"], [rule]) in asked
    decision = out["steps"][0]["decision"]
    assert decision.startswith("2 events from 3 documents (8 official documents evidence only by the seed rule, see plan: 1 joined an event, "
                               "7 in no event, 5 group(s) with no seed member dropped)")
    assert "no seed member on either side (pair 4 / singleton 1 / chain 1)" in decision


def test_an_outlet_document_may_join_a_group_of_evidence_only_documents(monkeypatch):
    sunshine = "Sunshine Act Meetings"
    docs = [_outlet(3, "Board meeting leak worries staff"), _held(23, sunshine), _held(24, sunshine), _held(25, sunshine)]
    keys = {3: _key("Board meeting leak worries staff", "board", "meeting", "leak", "staff")}
    keys.update({OFF + i: _key(sunshine, "board", "meeting", "agenda") for i in (23, 24, 25)})
    asked = _fake_model(monkeypatch, keys, {frozenset(("Board meeting leak worries staff", sunshine)), frozenset((sunshine, sunshine))})
    out = cluster.run(_zetaris_state(docs))
    assert [sorted(e["document_ids"]) for e in out["events"]] == [[3, OFF + 23, OFF + 24, OFF + 25]]
    assert [m for m, _, _ in asked].count("chain") == 1, "a group with a seed member is still chain-checked"
    assert "(3 official documents evidence only by the seed rule, see plan: 3 joined an event, 0 in no event)" in out["steps"][0]["decision"]


def test_a_window_of_evidence_only_documents_clusters_nothing(monkeypatch):
    asked = _fake_model(monkeypatch, {}, set())  # any event-key call would raise KeyError
    out = cluster.run(_zetaris_state([_held(22, "Ohio Regulatory Program"), _held(23, "Sunshine Act Meetings")]))
    assert out["events"] == [] and asked == [] and out["errors"] == []
    assert out["steps"][0]["decision"].startswith(
        "0 events from 0 documents (2 official documents evidence only by the seed rule, see plan: 0 joined an event, 2 in no event; "
        "no seed document in the window, nothing clustered)"
    )
