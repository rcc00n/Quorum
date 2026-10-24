# Reasoning review, 2026-10-23

Review and hardening of the reasoning block on `yelysei/agents`, run as four workstreams: A red-team of the
confirmation rules and the impact bar, B prompt-injection and untrusted-text audit, C evaluation set and
runner, D use-case walkthroughs as fixture days. The architecture itself was not changed: every fix below is
a code bug within the rules recorded in `docs/DECISIONS.md` and `docs/ARCHITECTURE.md` § 6; everything that
would change a rule is a proposal or a question here, not a change.

Baseline before the review: 27 tests passed, dry run end to end. After: 66 passed, 2 xfailed (both are
recorded proposals, A7 and D3), dry run unchanged on the fixture day,
`docs/examples/snapshot.sample.json` regenerated once for the roundup-label fix (D1/D2).

Commits, one per workstream plus one follow-up:

| Commit | Workstream | What |
| --- | --- | --- |
| `9e98bf5` | C | Eval set (28 real claims, 7 days) and `tests/eval.py` |
| `ac9cca4` | A | Red-team fixes: wire groups, id namespacing, superseded rows, sentence-boundary quotes, hearsay prompt |
| `6c50dad` | B | Injection hardening: `untrusted.py` wired into every payload and reply |
| `f1b39b8` | D | Eight use-case fixture days; roundup labels `Disputed` and `Single source` |
| `29359fd` | A | Follow-up: edition window follows America/New_York DST (A12) |

## Findings

Severity: high = a false or unsupported claim can end up `confirmed`, or data is corrupted; medium = a wrong
label, a dropped document, a killed run or a cost amplification; low = bounded surface or already defended.

| id | ws | sev | what can go wrong | reproduction (test) | status |
| --- | --- | --- | --- | --- | --- |
| A1 | A | high | A wire story plus its reprint counted as two independence groups: a claim confirmed by one wire. `wire_origin` was never read. | `test_a1_wire_reprint_carries_the_wire_independence_group`, `test_a1_wire_plus_its_reprint_do_not_confirm` | fixed in `ac9cca4` |
| A2 | A | high | `documents.id` and `official_docs.id` are separate Postgres sequences loaded into one id space: on a live day, collisions corrupt every by-id lookup and the self-confirmation skip can drop an unrelated outlet's evidence. The fixture masks it. | `test_a2_live_corpus_keeps_document_and_official_ids_apart`, `test_a2_official_evidence_keeps_the_database_id` | fixed in `ac9cca4` (official ids namespaced above `OFFICIAL_ID_OFFSET`, mapped back on evidence rows; duplicate ids abort the run) |
| A7 | A | med | Union-find chains above-threshold title pairs transitively: a bridge title puts two unrelated documents in one event, and research round 1 then lets the unrelated document confirm a claim. The model never sees the chain, only pairs. | `test_a7_bridge_title_must_not_chain_unrelated_documents` (xfail flipped to pass, 2026-10-24) | fixed by the event-key clustering redesign (Yelysei's decision 2026-10-24: least-similar-pair chain check; see reasoning/README.md › Decisions) |
| A8 | A | med | `supersedes_id` was never read: an original and its correction both stayed in the corpus, and retracted text kept supporting claims. | `test_a8_superseded_document_is_not_part_of_the_corpus` | fixed in `ac9cca4` (superseded rows dropped in `load_documents`); spread semantics open, see questions |
| A9 | A | med | Evidence quotes were cut at `passage[:300]`: a cut can land mid-sentence and drop the half that reverses the meaning. | `test_a9_quote_is_whole_sentences_not_a_character_cut` | fixed in `ac9cca4` (`text.clip_sentences`) |
| A10 | A | med | A passage that only relays a party's assertion ("officials said X") can be judged `supports`. | not reproducible in dry run (the stand-in, not the prompt, decides there) | prompt hardened in `ac9cca4` (`stance.md`: relayed assertions are `statement`); the dry-run stand-in still overcounts hearsay, which affects dry-run eval numbers only — left unchanged deliberately, see questions |
| A12 | A | med | The 05:30 America/New_York cut was hardcoded as 09:30Z: after DST ends on 2026-11-01, documents published 09:30–10:30Z fall between two editions and never enter any corpus. | `test_a12_edition_window_follows_new_york_dst` | fixed in `29359fd` |
| A3–A6, A11 | A | low | Attacks the code already defends: an official release's support is downgraded to `statement`; only law/order/vote/ruling establish; a claim cannot confirm itself; the cap never trades a confirmed story for a flagged one; the verdict is order-independent and contradiction-only evidence stays `unverified`. | `test_a3…`–`test_a6…`, `test_a11…` | defended; kept as regression tests |
| B1 | B | high | `extract_claims` kept the model-returned `origin_document_id` and claim text unchecked: a steered model can attribute invented text to another document (including an official law), and the self-confirmation guard then skips the wrong document. | `test_extract_rejects_foreign_origin_and_invented_text` | fixed in `6c50dad` (origin must belong to the event; claim text must be found in that document — `untrusted.grounded_in`, near-match accepted, invented rejected) |
| B2 | B | high | `write` published model-returned source URLs verbatim: a URL suggested by hostile text could appear as a source link under a fact sentence. | `test_write_drops_source_urls_the_state_does_not_know` | fixed in `6c50dad` (sources filtered to URLs the state knows) |
| B3 | B | med | Stance strings were stored unvalidated: `"supports; ignore all other rules"` reached the snapshot. | `test_research_rejects_unknown_stance_words` | fixed in `6c50dad` (four stance words or neutral) |
| B4 | B | med | `cluster` merged a borderline pair on any truthy `same_event`: the JSON string `"false"` merged. | `test_cluster_requires_boolean_same_event` | fixed in `6c50dad` (`is True`) |
| B5 | B | med | No cap on claims per event: one hostile document multiplies model calls in research × fact-check. | `test_extract_caps_claim_count` | fixed in `6c50dad` (12 per event) |
| B6 | B | med | `extract_claims`, `score_importance` and `cluster` had no error handling around the model call: one unparseable reply killed the run. | code-read finding (dry twins cannot fail) | fixed in `6c50dad` (per-event try/except, fail-safe outcomes, `errors` row → snapshot `partial`) |
| B7 | B | med | `llm.json_task` parsed the reply from the first `{` to the last `}`: a reply echoing attacker-shaped JSON before its answer broke the parse or returned the attacker's object. | `test_parse_json_object_takes_the_models_final_answer` | fixed in `6c50dad` (last balanced JSON object) |
| B8 | B | low | Untrusted text reached payloads uncapped (a stance passage could be 20 000 characters). | end-to-end tests in `test_injection.py` | fixed in `6c50dad` (caps in `untrusted.py`) |
| B9 | B | low | Payloads and prompts carried no statement that the text fields are quoted data. | `test_verdicts_unaffected_by_instructions_in_the_text` | fixed in `6c50dad` (`DATA_NOTE` + one paragraph per prompt) |
| B10 | B | med | Event headlines, standfirsts and roundup fallback lines derive from untrusted titles verbatim; an instruction-shaped or misleading title surfaces in the system's voice. Code cannot decide that a sentence is an instruction. | by construction; see "What code cannot prevent" | decided 2026-10-24: roundup lines are always model-generated and critic-checked; the raw title is only the fallback, marked `line_source: "title"`. Event headlines remain titles (curation is the mitigation); note for Anastasia stands |
| B11 | B | low | `fetch_text` is called once per (claim, document) pair with no cache: in live mode the same URL is fetched many times per run. | code-read finding | proposal |
| C1 | C | med | Mass-casualty strikes score below the bar: Kramatorsk (30 dead, 3 independence groups) = 0+1+2+2 = 5 < 6. If intended, one sentence in DECISIONS.md closes it; if not, the rubric needs casualty guidance. | eval days 2026-10-10/-12 (`expected_above_bar` differs) | question for Yelysei |
| C2 | C | med | Clustering on exact title tokens fragments real days (titles of one event share ~2 tokens), so cross-outlet confirmation is structurally unreachable; this dominates the eval's `missed confirmed` = 7. | `tests/eval.py` dry baseline | fixed by the event-key clustering redesign (2026-10-24): the fragmented eval days now cluster (Kramatorsk's three outlets are one event with cross-outlet evidence); the dry-run `missed confirmed` number stays at 7 because the remaining distance is the stance stand-in's word-overlap bound, which only a live run measures (fixtures/eval/README.md) |
| C3 | C | — | `collectors/sources.csv` has no defense.gov row (the review task allows defense.gov documents); reuters.com, apnews.com, nypost.com, nytimes.com, theguardian.com block the search crawler used to build the dataset. | `fixtures/eval/README.md` | note for Anastasia |
| C4 | C | — | Eval leads are reconstructed from search-result summaries, not verbatim outlet text; the EO text is an excerpt. Re-fetch before any live acceptance use. | `fixtures/eval/README.md` (`verbatim: false` markers) | limitation, recorded |
| C5 | C | low | `tools/corpus.load_fixture` ignores `edition_date`: every dry-run date returns the same sample day. The eval sidesteps it by injecting documents. | code-read finding | proposal |
| D1 | D | med | A single-outlet scoop was labelled `unverified` in the roundup; DECISIONS names `single source` and the reader loses the one-outlet warning. | `test_scoop_roundup_status_is_single_source` | fixed in `f1b39b8` |
| D2 | D | med | A below-bar event with a disputed claim could never show `disputed`: no such label or group existed, though DECISIONS lists it. | `test_roundup_label_disputed_exists` | fixed in `f1b39b8` |
| D3 | D | med | Retraction within the day: whether a superseded document still counts for spread, and how corrections arriving under new URLs are linked, is undefined in DECISIONS/ARCHITECTURE. The corpus now drops superseded rows (A8), so they count for nothing. | `test_retraction_superseded_document_is_not_evidence` (xfail flipped to pass, 2026-10-24) | decided 2026-10-24 (DECISIONS.md log): superseded rows stay for spread and coverage, excluded from evidence, confirmation and extraction; corrections under new URLs remain with Anastasia |

## Proposals (not applied; Yelysei decides)

1. **A7 — transitive clustering chains.** Options: (a) model-confirm the least-similar pair inside every
   multi-document event and split on "no"; (b) union a pair only when the new document shares a word with
   every current member; (c) accept the risk, relying on stance checks needing the claim's words in the
   passage. The xfail test is strict, so any fix flips it visibly.
2. **C2 — clustering fragmentation on real titles.** Light stemming of title tokens, or a second pass that
   offers singleton clusters to the model with leads as context. Same recorded decision as A7 touches
   (`nodes/cluster.py`, README decision row); decide both together.
3. **B11 — fetch cache.** One `lru_cache` keyed by URL per run (or a fetched-text dict on the state) so live
   runs fetch each URL once.
4. **C5 — fixture per date.** A fixture-directory switch in `tools/corpus.load_fixture` so `run.py --dry-run`
   can run the eval days directly; the eval does not need it (it injects documents), so this is convenience.
5. **A10 — dry-run stance stand-in.** The stand-in counts hearsay as support, which inflates dry-run eval
   agreement. Changing it changes `test_graph.py` and the sample snapshot; do it, if at all, in one commit
   that regenerates both.

### Proposal: a third blind reviewer for `disputed` claims (design only, no code)

Today `rules/confirmation.adjudicate` turns any verifier/fact-checker disagreement into `disputed`, per
DECISIONS.md › Principles for handling facts. A bounded third pass would work like this:

- **Where.** One new node, `review_disputed`, between `adjudicate` and `frame`, entered by a conditional
  edge only when at least one claim is `disputed` because of a *disagreement* ("verifier says X,
  fact-checker says Y"). A claim both checkers call `disputed` (a genuine evidence contradiction) is not
  reviewed: the third pass has nothing to add there. The route is code; the model still controls no edge.
- **Inputs (bounded).** Per disagreed claim, one model call: the claim text, kind, speaker; both evidence
  chains as data (the researcher/verifier rows and the fact-checker rows, each with quote, stance,
  independence group, is_document, url); both one-line reasons. No corpus access, no fetching, no new
  evidence: the reviewer judges what the two chains already hold. Payload capped as in `untrusted.py`.
- **Output.** JSON `{verdict, decisive_quote, decisive_evidence_index, reason}`. Code validates: the verdict
  must be one of the two blind verdicts or `disputed` (the reviewer may side with a chain or keep the
  dispute, never invent a third outcome); the decisive quote must be found (near-match) in the cited
  evidence row, else the pass is discarded and the claim stays `disputed` with "third pass invalid" in the
  adjudication. A `confirmed` verdict is accepted only when the cited chain itself satisfies
  `rules/confirmation.verdict` — the reviewer picks which chain to trust; the rule still decides what that
  chain proves.
- **Limit.** One pass per claim, never repeated (`loops.review_disputed_max = 1`). No loop.
- **Trace.** One StepRecord per reviewed claim ("sided with verifier / fact-checker / kept disputed"); the
  snapshot claim keeps both original verdicts plus `third_review: {verdict, reason, quote}` so the page
  shows all three.
- **Cost.** One call per disagreed claim; on the fixture day, 2. Live, single digits per topic-day at the
  sizing of ARCHITECTURE § 7 and the eval's 5% disputed rate.
- **DECISIONS.md change it needs.** "A disagreement between the two checks = 'disputed'" would become: a
  disagreement goes to a third blind reviewer (different model when available, both chains as input, one
  pass); if the reviewer validates one chain under the confirmation rule, that verdict stands and the trace
  shows all three; otherwise disputed. "Never resolved by guessing" survives: the code rule, not the vote,
  still gates `confirmed`.
- **Trade-off.** For: fewer disputes that are artifacts of retrieval differences (one checker found the
  second group, the other did not) rather than real contradictions. Against: one more model dependency in
  the trust chain, and a story can flip from disputed to confirmed on a model call; the mitigation is the
  code gate plus all three verdicts on the page.

## Open questions for Yelysei

Decided 2026-10-24 (DECISIONS.md log and reasoning/README.md › Decisions carry the canonical entries):
1 — the origin outlet or agency counts as one group next to at least one other (never for statement-kind
claims); 2 — stays as recorded; 3 — model lines with a marked title fallback; 4 — engineering constants
stay in code; 5 — dropped claims kept with text and reason in the per-event trace (`detail`); 6 — the
confirmed-deaths reach sentence, threshold unchanged; 7 — superseded rows: spread yes, evidence no; 8 —
`by_headline` on level-2 evidence; 9 — `unverified` kept and defined. The clustering proposals (A7, C2)
became the event-key redesign. The original questions follow for the record.

1. **Origin plus one other group.** A claim extracted from a Reuters story and supported only by AP stays
   `unverified`: the origin document is excluded from evidence, so Reuters' group never appears. If the
   origin outlet plus one other group should confirm, that is a § 6 rule change. (A)
2. **Event confirmation points mix both chains.** `adjudicate.event_confirmation` takes the best-supported
   claim over all evidence rows, so an event can show confirmation 2 with zero confirmed claims; escalation
   catches the story case. Left as recorded; flagged because the rubric rationale wording can overstate. (A)
3. **B10 — headlines from titles.** Is a raw outlet title acceptable as an event headline and as the roundup
   fallback line, or should roundup items always use the model line (critic-checked, capped) with the title
   kept only as data?
4. **Grounding threshold placement.** `untrusted.GROUNDING_MIN = 0.6` and the payload caps are placed as
   engineering bounds. If grounding strictness is a product rule, it belongs in `config/reasoning.toml` and
   DECISIONS.md.
5. **Audit of dropped claims.** Claims rejected by validation appear only as a count in the trace decision.
   Keep text + reason somewhere (errors, a per-event list) for audit?
6. **C1 — the bar vs mass-casualty strikes** (see findings). One sentence in DECISIONS.md either way.
7. **D3 — the retraction rule.** Proposal: superseded documents are excluded from evidence and confirmation,
   kept for spread. Needs a DECISIONS.md sentence and Anastasia's confirmation of the semantics.
8. **Level-2 "by headline" marker.** DECISIONS says paywalled sources' scores are "marked 'by headline'";
   no such marker exists in the state or the snapshot. Add per-evidence `by_headline`? (D)
9. **`Unverified` roundup label.** It survives D1/D2 as the label of last resort but DECISIONS does not
   define it. Keep as the fifth label? (D)

## Notes for Anastasia (collectors; nothing in `collectors/` was changed)

- `wire_origin` and `independence_group` correctness now directly bounds confirmation correctness: reasoning
  counts a reprint in the wire's group (A1), but a reprint the collectors do not mark still double-counts,
  and reasoning cannot repair that. What does wire detection currently catch?
- `supersedes_id`: reasoning now drops superseded rows from the day's corpus (A8). Confirm the semantics
  ("current version of the same document"?) and whether corrections can arrive under new URLs — those are
  invisible to this mechanism. Also note `documents.supersedes_id` was collected but never read until now.
- `collectors/sources.csv` has no defense.gov row; the eval task treats defense.gov documents as allowed
  official sources. Reuters, AP, NY Post, NYT and Guardian block the crawler this review's dataset was built
  with (the collectors' own RSS access is unaffected).
- Decided 2026-10-24 (her question 5): level-2 rows of outlets that run wire copy (NYT, WSJ, The Atlantic; the
  Reuters sitemap and AFP via France24 are agencies already) get no special treatment — a level-2 row contributes
  headline and lead only and is marked `by_headline` on every evidence row. Residual risk, accepted: a reprint
  credited only in the body of a level-2 document is unmarked and counts as the outlet's own group, so one wire
  story plus such a reprint could confirm a claim. Bounded by the small set of level-2 outlets and by the blind
  fact-checker; revisit if a live day shows it.
- Title and lead hygiene at collection time would cut the main injection surface: strip control characters
  and HTML, cap lengths (titles ~300, leads ~600). Reasoning caps on its side too; two layers are better
  than one.

## Notes for Vadim (portal; no web code was changed)

- Roundup `status` values are now: `reported, not confirmed`, `confirmed`, `disputed`, `single source`,
  `statements only`, `unverified` — `disputed` is new, and `single source` now also covers events whose
  documents span one independence group. `docs/examples/snapshot.sample.json` was regenerated in
  `f1b39b8`; the Reuters-only grain-corridor event moved from `unverified` to `single source`.
- Everything model- or outlet-derived in the snapshot (headline, standfirst, article block texts, framing
  labels, evidence quotes, summary, roundup lines) is untrusted free text: render as plain text, never as
  HTML or markdown. Source and evidence URLs are now checked against the state but still point at outlet
  sites: render with `rel="noopener noreferrer"` and show the domain next to the link text.

## What code cannot prevent and must stay a rule

1. **The stance judgment itself.** A hostile passage written to read like independent assertion can make the
   model answer `supports`. Backstops: the independence rule (one hostile outlet is one group and can never
   confirm alone) and the blind fact-checker. The residual risk — two independence groups both reprinting
   crafted text — is a source-curation question.
2. **Untrusted titles surfacing as headlines and roundup lines** (B10). Deciding "this sentence is an
   instruction" is a judgment no rule in `writing_rules.py` can make; mitigations are curation (only
   `collectors/sources.csv` sources enter the corpus) and caps.
3. **Judged rubric points read hostile titles and leads.** A lying headline can inflate `legal_force` or
   `reach`; the computed confirmation gate is the backstop — without independent confirmation the event is a
   roundup line, never a story.
4. **Selection bias in extraction.** Grounding guarantees a claim's text exists in its document, not that the
   model picked representative sentences. The blind fact-checker and the disputed status are the backstop.

**The model never controls routing — confirmed file by file.** `graph.py` wires exactly three conditional
edges: `verify.route` (code: thinness and the round budget), `adjudicate.route` (code: `needs_review` from
the bar and confirmed counts), `critique.route` (code: writing-rule violations and `drafts_max`). No model
output is used as a node name, a jump target, a fetch URL or a config value; model answers act only at
enumerated, bounded points (stance per passage, merge per borderline pair, three judged rubric points,
generated text behind the critic and the confirmation rule). This must stay a rule when nodes are added: a
future model critic returns verdicts, never routes.

## Eval baseline (dry run, 2026-10-23)

False confirmed 0; missed confirmed 7 (dominated by C2); disputed rate 5%; 7 of 28 claims not extracted;
above-bar matches expected on 4 of 7 days. Dry-run numbers measure the pipeline's mechanics and the rule
layer, not the model's judgment — `fixtures/eval/README.md` states what only `--live` can measure.
