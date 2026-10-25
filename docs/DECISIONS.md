# Quorum — project decisions

Updated: 2026-10-22 · First version by Yelysei Shkirpan · Source: team discussion and the agreed project description

This is the single source of truth for product and architecture. Code that contradicts this document is a bug either in the code or in the document; the latter is fixed by editing this file, never silently in code. How decisions are made and recorded is described in [AGENTS.md](../AGENTS.md), section "Decisions". The change log is at the end of this document.

## What we are building

Quorum is a multi-agent system that, for one event, collects publications from different sources, separates facts from interpretations, verifies claims against evidence, and shows how different parts of the political spectrum frame that event.

**Motivation.** Societies are polarized, and everyone lives in their own information bubble. A Democrat does not see the facts a Republican sees, or does not weigh them. A Republican, the other way round. Instead of one source with its interpretation, the user gets the fact: what happened. On request, statistics on how a given party or outlet interpreted that fact.

**Key feature.** Quorum does not retell the news. It investigates what is actually known, which claims contradict each other, what evidence exists, and how different sources interpret the same event. The goal is an AI that does not ask the user to trust its answer, but lets them verify every substantive conclusion.

**Context.** Team Quorum's project for the [Open Agent Hackathon 2026](https://hackathon.genai.works/event/open-agent-hackathon-2026), Track 03 Reasoning Architecture. Build window 22–27 October 2026; submissions close 27 October 23:45 UTC (19:45 New York). The judges expect an agent system with verification loops, not a linear pipeline.

## MVP scope

The MVP consists of the six features from the agreed project description plus seven team decisions: topic selection, login, an independent fact-checker, four spectrum-rating modes, selection of stories by an absolute impact bar, stories written as articles, and the "Also today" roundup.

| Feature | What it includes |
| --- | --- |
| 1. Multi-source intelligence | News from several independent sources: RSS, news APIs, official publications. Federated through Zetaris with SQL queries across sources. Grouping of publications about one event. |
| 2. Autonomous fact verification | The AI extracts checkable claims, looks for supporting and contradicting evidence, and requests additional sources when needed. It distinguishes confirmed facts, disputed claims, and what cannot yet be verified. It accounts for several publications retelling one primary source. |
| 3. Evidence-based reasoning | Every conclusion carries its sources and an explanation of the evidence it rests on. When sources contradict each other, the agent investigates the cause of the discrepancy. When evidence is insufficient, the system says so plainly. The user sees the verification process and can go to the originals. |
| 4. Neutral news brief | A short article (3–4 minutes) built only from verified claims, without political interpretation or evaluation. What happened, what the parties say and what is not confirmed are kept apart by writing rules, not by headings (see "Stories as articles"). |
| 5. Narrative & framing comparison | How different sources cover one event: which facts they highlight, which they omit, which wording they use. Comparison of specific outlets and statements by political organizations. Every conclusion comes with examples from the source material. |
| 6. Interactive dashboard | Event feed and topic filter. Event page with facts, sources and disagreements. Comparison of coverage across sources. Drill-down into evidence and reasoning. |

**Added by team decision**

- Topic selection at first setup: the agents collect and analyze only those topics.
- Login and password. No subscription; free at first.
- An independent fact-checker in addition to cross-checking publications (see "Principles for handling facts").
- Four political-spectrum rating modes and a cohort diagram (see "Spectrum ratings and cohorts").
- Stories are selected by an absolute impact bar, up to ten a day per topic and with no minimum; coverage and silence per cohort are a separate fact (see "Selecting major news").
- Stories are written as short articles with photos, not as briefs with headings; facts only, no evaluation (see "Stories as articles").
- An "Also today" roundup per topic and day: one line for every event below the bar, with its source and status (see "Selecting major news").

**Out of scope:** social networks (Facebook and others) — many bots, an unrealistic picture, and questionable legality of collection. Sources are news outlets and official government bodies.

## Principles for handling facts

A fact is either a signed document or a claim confirmed by independent sources. Everything else is a statement and is presented as a statement.

- **Statement = a party's words. Signed document = fact.** A decree, law, order, court ruling or signed agreement is a fact. Operationally: the fact is that the document was adopted and what it says. Assessments and figures inside the document about the outside world remain the signer's claims. Otherwise any defense ministry's report would automatically become a fact.
- **Official government documents are the top-priority source.** Media news is not. The model does not guess: a claim without a source is not accepted.
- **Two metrics that are never mixed.** "Confirmation" counts only independent sources: ten reprints of one wire story are one piece of evidence, not ten. "Spread" counts without deduplication: every publication is separate, because people read it.
- **Independent fact-checker.** A separate agent re-verifies the extracted claims without seeing the primary verifier's conclusions. A different model, if the hackathon rules allow, and its own toolset: search over primary sources and official documents. A disagreement between the two checks = "disputed".
- **Sources under every conclusion.** The agent explains why a claim was accepted as real rather than fake, and provides links. If evidence is thin, the system says so plainly instead of inventing an answer.

## Spectrum ratings and cohorts

A source's position on the spectrum comes from external ratings in one of four modes. Switching the mode recomputes the center and the cohorts.

- Modes: [AllSides](https://www.allsides.com/media-bias/ratings), [MBFC](https://mediabiasfactcheck.com/), [Ad Fontes](https://adfontesmedia.com/) and averaged.
- The averaged mode uses an open formula. Each rating is mapped to a −1…+1 scale: AllSides (5 steps) → −1, −0.5, 0, +0.5, +1; MBFC (7 steps) → −1, −0.67, −0.33, 0, +0.33, +0.67, +1; Ad Fontes → bias ÷ 42. The result is the mean of the available ratings.
- Cohorts by threshold: ≤ −0.25 left; between −0.25 and +0.25 center; ≥ +0.25 right. The formula is shown in the tooltip of the mode switch.
- Ratings for ~40 sources are entered by hand into a CSV, not scraped.
- The model's own spectrum rating is not used in the MVP (see "After the hackathon").

$$
s = \frac{1}{n}\sum_{i=1}^{n} s_i,\qquad s_i \in [-1,\,1],\qquad n = \text{number of available ratings}
$$

**Diagram and cohorts.** X axis: position under the selected rating mode. Y axis: audience, log scale. Four cohorts: major left, major right, minor left, minor right. Per-cohort statistics: share of outlets and share of audience. This makes visible the concentration of the right around a few major outlets and the spread of the left.

| Audience ↓ / Position → | Left | Right |
| --- | --- | --- |
| **Major** | CNN, NYT, Washington Post, Guardian, NPR, MSNBC, HuffPost | Fox News, NY Post |
| **Minor** | Vox, Mother Jones, The Intercept, Salon, The Atlantic, The Daily Beast, Slate, The New Republic, The Nation, Common Dreams | Washington Examiner, Washington Times, Daily Caller, Daily Wire, Newsmax, Washington Free Beacon, The Federalist, Breitbart, The Blaze, Townhall, National Review, The Daily Signal, RedState |

Outlets are placed in cohorts according to the agreed tier assignment; exact positions on both axes will appear once the CSV with ratings and audience is filled in. The center (WSJ) sits outside the cohorts.

## Stories as articles

A story is a short article the reader can form their own view from: facts with sources, the parties' statements with their authors, and what is not confirmed. No evaluation is added. The three parts of the brief stay as data and as rules for the critic; on the page they are prose, not headings.

- **Built only from verified claims.** Every sentence maps to a claim with a status. The writer cannot add a sentence that has no claim behind it, and the critic rejects any that does.
- **Status is shown by typography, not by sections.** A confirmed fact is plain text with its sources in small gray links right after the sentence. A statement is attributed in the sentence itself ("the White House says"). What is not confirmed is a short paragraph at the end, "Not confirmed". One gray line under the headline explains this key.
- **No evaluation.** Forbidden in the writer's voice: evaluative adjectives and adverbs, predictions, causal links without a source, and any "why it matters". What an event may change is for the reader to decide or for the parties to claim, with attribution.
- **Context only as facts.** Prior comparable events, the document's own provisions, numbers from official data — each with a source. "The previous package took eleven weeks to ship" is context; "this one matters because it is a law" is not.
- **Fixed order:** facts in chronological order, then statements, then what is not confirmed. A fixed order removes framing by sequence.
- **Headline and standfirst.** Headline: subject, verb, object, no adjectives. Standfirst: three facts.
- **Length:** 2–4 minutes of reading. The writer picks one of a few shapes by event type (event report, document explainer, dispute explainer); the shapes are few so the critic can check them.
- **Photos.** One lead photo and at most one inline photo, only when the agent finds a suitable image under an allowed license: US federal government sites (public domain) and Wikimedia Commons with an open license. Always with a credit and a caption that says what is shown, without adjectives. No photo is fine. AP, Reuters and AFP photos are not used. A photo is also framing: documentary and official images, not emotional ones.
- **At the end, as an appendix:** "Across the spectrum" — how left and right outlets told the story, one line on where big and small outlets differ, and links to all claims with evidence and to the reasoning trace. A reader who wants only the facts never reaches it.

## Selecting major news

Importance is measured by impact on people's lives, not by how many outlets covered an event. Ten stories a day per topic is a cap, not a target: a day with three stories shows three, a day with none says so.

- **Candidates** are all events in the corpus, including official documents. An event nobody published cannot be seen by the system. The realistic case is "covered only by government bodies or by one or two sources".
- **An absolute bar, not a ranking.** A top-N always produces N. Instead each event is scored on an open rubric and shown only if it crosses a fixed threshold: legal force (0 none, 1 official statement, 2 adopted document); reach (0 local or unknown, 1 a region or one sector, 2 national or several sectors, 3 several countries); irreversibility (0 reversible, 1 hard to reverse, 2 irreversible); confirmation (0 unverified, 1 one independent source, 2 two independent sources or a document). A story is shown when the total is at least 6 and confirmation is at least 1. The threshold is a configuration parameter and is calibrated on the first real days.
- **Confirmation is a gate.** An unconfirmed event never becomes a story, however large its potential impact; it goes to the roundup marked "reported, not confirmed".
- **"Interesting" is not a criterion.** Only the rubric decides; liveliness follows from impact.
- **No minimum.** A day with no story above the bar is stated plainly on the topic page and on the home card: "No story crossed the bar today". The roundup then carries every event of the day.
- **"Also today" roundup** — one article per topic and day for everything below the bar: one line per event with its source and status (confirmed, disputed, statements only, single source), grouped by sub-topic, ordered by rubric score. It includes events covered only by official sources. No framing analysis for roundup items.
- **Coverage and silence per cohort** is a separate, visible fact: "covered by N of M sources in the cohort". A whole cohort's silence on a story is a highlighted line.
- **The rule is visible.** The topic page carries a short "What crosses the bar" note; the full rubric score for each story is in its trace.

## Sources

The set is text-based news outlets split by flank and tier, plus news agencies as the fact anchor and official government bodies. For the hackathon the list is cut to 10–15 sources; that is the source-audit task on the board.

| Group | Sources | Access |
| --- | --- | --- |
| Agencies, fact anchor | AP, Reuters, AFP | AP — RSS with full text. Reuters — public RSS closed; headlines via Google News RSS by domain. AFP — check whether a usable feed exists. |
| Left, major | CNN, NYT, Washington Post, Guardian, NPR, MSNBC, HuffPost | NYT and Washington Post — paywall, headline and lead only. Guardian — free API with full text. Others — full text. |
| Left, minor | Vox, Mother Jones, The Intercept, Salon, The Atlantic, The Daily Beast, Slate, The New Republic, The Nation, Common Dreams | The Atlantic — paywall. Others — full text. |
| Right, major | Fox News, NY Post | Full text. |
| Right, minor | Washington Examiner, Washington Times, Daily Caller, Daily Wire, Newsmax, Washington Free Beacon, The Federalist, Breitbart, The Blaze, Townhall, National Review, The Daily Signal, RedState | Full text. |
| Center, outside cohorts | WSJ | Paywall, headline and lead. Counts for coverage, not for cohorts. |
| Military specialists, attributed only | ISW, DeepState, Oryx | Their own lens; presented as statements with the author named. |
| Official government bodies (candidates) | US: whitehouse.gov, federalregister.gov, congress.gov, defense.gov, state.gov, supremecourt.gov. Ukraine: president.gov.ua, mod.gov.ua, mfa.gov.ua. Russia: kremlin.ru, mid.ru, mil.ru | Federal Register and Congress.gov have APIs. Documents are facts, statements are words (see "Principles for handling facts"). |

- Access levels: 1 — full text; 2 — headline and lead from RSS; 3 — only the fact of coverage. Paywalled sources participate at level 2 and their scores are marked "by headline".
- An outlet's flank comes from the external ratings in the selected mode, not from the team's taste. Tier comes from audience; for the MVP the majors are a fixed list.
- Audience figures for the Y axis and cohort shares are public estimates, entered by hand into the CSV.
- Social networks are out of scope.

## User account and interface

The account is built around the topics the user selects. The interface is simple in the manner of Apple News: a few readable elements beat many metrics. Numbers and analysis live behind links, never on the first screen. A design mock of all screens exists as a Claude Design canvas, "Quorum — app screens" (Yelysei's account; ask for a share link).

1. **Sign-in.** Login and password. No subscription; free at first.
2. **First setup.** The user picks the topics they care about. The agents collect and analyze only those.
3. **Home.** One card per topic, like Apple News: a photo of the day as background, the topic name in a large rounded display font over it, one line with the lead story and the number of stories today (or "No story crossed the bar today"), a small photo credit. The first topic is a full-width card, the rest a two-column grid.
4. **Topic page for today.**
    - One paragraph: how many events crossed the bar and how the views of different parties are distributed.
    - The stories that crossed the bar (up to ten): number, headline, a one-line factual standfirst with reading time, a thumbnail. A whole cohort's silence is one red line under the story.
    - A card to the "Also today" roundup, naming what is in it.
    - Aside: the lead story's interpretations in words ("19 outlets, mostly left"); who counts as left and right, with the rating-mode switch as a text link; a three-sentence "What crosses the bar" note.
5. **Story page** — the article (see "Stories as articles"), then "Across the spectrum" as an appendix.
6. **Roundup page** — "Also today": one line per event below the bar, grouped, with source and status.
7. **History** — a tab on the topic page, by day, labeled like "digest for 10/12/2026".
8. **Shift in party positions** — under the topic, outside the days. Implemented after the hackathon; data accumulates from day one.
9. **Type and color.** Display: SF Pro Rounded via the CSS generic `ui-rounded` (Safari, iOS), with Nunito from Google Fonts as the fallback elsewhere. Body: the system font, with Inter as the fallback. White background, one red accent for the date, cohort colors blue (left) and red (right), darker for big outlets and lighter for small ones. Status words, not colored pills.

## Stack and work blocks

Data flows through Zetaris and reasoning runs on NVIDIA Nemotron and Meterless. The user-facing frontend is Next.js + TypeScript; Django owns authentication, user management, administration and web-facing API endpoints.

Previous stack decision (superseded 2026-10-22 by explicit human team-approved clarification): interface and backend both used Next.js + TypeScript. Collectors and reasoning ownership and architecture are unchanged. The architecture is an agent system with verification loops, not a linear pipeline; its detailed design is a separate task on the board.

| Layer | Technology | Role |
| --- | --- | --- |
| Data | Zetaris | Single data layer. SQL queries across different sources as if they were one database. |
| Reasoning | NVIDIA Nemotron, Meterless | Claim verification, agent processes. |
| Independent review | Additional LLMs | Independent review of complex conclusions, if the rules allow. |
| Reasoning orchestration | Python, LangGraph; LangGraph Studio for development and the demo | The reasoning block is one LangGraph graph with verification loops; agents read only through Zetaris and write their results to Postgres directly; one run per topic per day plus on-demand runs. Design: [ARCHITECTURE.md](ARCHITECTURE.md). |
| Interface | Next.js + TypeScript | User portal: account, topic, story and roundup pages. |
| Web backend and administration | Django | Session authentication, preferences, web API, Quorum Control. Dedicated portal database, separate from collector tables. A typed read-only adapter reads published reasoning snapshots; the contract is being agreed (see "Still to clarify"). |
| Deployment | quorum.raccncode.com | Isolated lightweight VPS for the portal, set up by Vadim. No inference, collectors or Zetaris run there. |
| Development | Each member's own assistant: Codex (Vadim), Claude Code (Yelysei), Nastya's choice | Rules for all assistants are in [AGENTS.md](../AGENTS.md); the shared tracker is [Issue #2](https://github.com/rcc00n/Quorum/issues/2). Routine checks do not require Cursor; its interactive acceptance is historical opt-in diagnostics. Organizer rule 5.1 was independently checked on 2026-10-25 UTC: Cursor development is optional; Zetaris and Meterless remain required. See [rules evidence](RULES_CHECK.md). Verify the track requirements in HackOS: the event page lists NVIDIA, Zetaris, SpaceX AI and Meterless as sponsors. |

Historical evidence state (superseded 2026-10-25 UTC by the direct rule 5.1 check): the team reported Cursor was optional, but this had not yet been independently verified. The sponsor and final compliance gates remain separate.

Previous development-tool listing (superseded 2026-10-22 by explicit human workflow clarification): Cursor / Codex / Claude Code, each team member’s own. Cursor installation/interactive acceptance is now historical opt-in diagnostics, excluded from routine readiness. This does not waive Zetaris/Meterless integration or certify submission compliance. A later wording of the row, "Codex — current team workflow", was superseded the same day: the team does not share one assistant.

**Three work blocks and who owns them** (agreed in the team chat on 2026-10-22; not a strict split, everything is discussed together)

1. Data collection: sources, APIs, databases — Nastya.
2. Analysis and reasoning, the agent architecture — Yelysei.
3. Frontend, interface, UI/UX — Vadim.

**Git.** Nobody works on `master`. Each member works on their own branch — `data-collection` (Nastya), `yelysei/agents` (Yelysei), `feature/web-portals` (Vadim), as listed in [AGENTS.md](../AGENTS.md#shared-project-tracking-and-cross-agent-handoff) — and merges to `master` through a pull request.

**What the judges consider a strong submission:** agents that delegate tasks dynamically, critique and validate outputs, work in planner — executor — evaluator loops, share memory, can branch, retry, escalate and recover, and leave reasoning traces. A chain "agent A → agent B → agent C" with no feedback is rated as weak.

## Demo for the judges

The demo is one real political event that different sources cover differently. Quorum collects the publications, extracts the contradicting claims, consults additional evidence, and delivers four things:

1. What is reliably known.
2. Which claims remain disputed and why.
3. How the interpretations of different sources differ.
4. What each of the agent's conclusions rests on — with the reasoning trace and links.

Submission per the hackathon guide (verify in HackOS): a 1–4 minute demo video, slides, the repository with a README, and an explanation of how the sponsor technologies were used. Deadline: 27 October, 23:45 UTC.

## After the hackathon

Four things are deferred. For the first of them, data accumulates from day one.

- **Shift in party positions by topic over time** — the core of the product; implemented after the hackathon. From day one, for every topic, each source's and cohort's interpretations are stored by day. Otherwise there will be nothing to compute the shift from.
- **The model's own spectrum rating** — as an "observed position" from the accumulated tone scores, shown next to the external ratings.
- **Comparison of US and Chinese news.**
- **Subscription** — everything is free at first.

## Still to clarify

Seven questions the team has not closed yet.

- [ ] Whether the model's own rating is needed as a fifth mode already in the MVP. Default: no.
- [ ] The reasoning output contract and its transport to the portal. Reasoning's proposal is [ARCHITECTURE.md § 8](ARCHITECTURE.md); the portal's validated proposal is [SNAPSHOT_PROPOSAL.md](SNAPSHOT_PROPOSAL.md). One schema must come out of the two, owned by reasoning, before either side codes the live bridge.
- [ ] The impact-bar threshold: start at 6 of 9 with confirmation ≥ 1, then calibrate on the first real days.
- [ ] Which official government bodies are in the hackathon slice, and which event we take for the demo.
- [ ] Language of the interface and the demo: the judges are English-speaking.
- [ ] The track's requirements for sponsor technologies and development tools — verify on the challenge page in HackOS.
- [ ] Where the audience estimates for the Y axis and cohort shares come from.

## Portal integration proposal

Explicit human authorization permits a portal-owned versioned snapshot **proposal**, strict local validation/publication scaffolding and optional rich evidence presentation, without making it the reasoning API. See [proposal and approval dependencies](SNAPSHOT_PROPOSAL.md). Reasoning retains schema ownership; transport credentials and production publication remain disabled until cross-team agreement. No collector/reasoning architecture is changed.

## Shared development coordination

[GitHub Issue #2](https://github.com/rcc00n/Quorum/issues/2) is the canonical cross-team feature/release tracker. Every assistant follows the tracking/handoff protocol in [AGENTS.md](../AGENTS.md#shared-project-tracking-and-cross-agent-handoff), with evidence-backed states and read-only inspection of other owners' branches. Module inventories and release checklists supplement this tracker; product and architecture decisions remain here. This coordination amendment does not approve unfinished application code or change data/reasoning architecture.

## Decision log

Every change to this document gets a row here. Newest rows on top. Rules are in [AGENTS.md](../AGENTS.md), section "Decisions".

| Date | Who (human / tool) | What was decided | Why |
| --- | --- | --- | --- |
| 2026-10-25 UTC | rcc00n / Codex | Verify organizer rule 5.1 directly: Cursor optional, Zetaris and Meterless still required; preserve earlier unverified evidence state below. | Resolve the tool-policy evidence blocker without waiving actual sponsor integration or submission requirements. |
| 2026-10-22 | Yelysei / Claude | Reasoning block: Python and LangGraph, LangGraph Studio for development and the demo; agents read only through Zetaris and write results to Postgres directly; one run per topic per day plus on-demand runs; design in ARCHITECTURE.md | Loops, checkpoints and a visible trace come with the library; the data block is Python already |
| 2026-10-22 | Yelysei / Claude | Merged this file across branches: kept the coordination and portal rows (master, PR #1), the stack rows and superseded notes from PR #1, and restated the Development row as each member's own assistant | Three branches edited this file on the same day; "Codex — current team workflow" implied one tool for the team, but Vadim uses Codex and Yelysei uses Claude Code |
| 2026-10-22 | rcc00n / Codex, explicit human portal-foundation authorization | Implement the portal-owned snapshot proposal and optional evidence/trace views; upstream schema and production transport remain unapproved. | Prepare a tested integration target without dictating reasoning output or enabling production ingestion. |
| 2026-10-22 | rcc00n / Codex, explicit human coordination authorization | Issue #2 is the canonical shared tracker; every assistant follows the AGENTS.md tracking/handoff protocol across branches. | Preserve feature ownership, completion evidence and regression checks across independent sessions without merging application work. |
| 2026-10-22 | rcc00n / Codex, explicit human workflow update | Use Codex; exclude Cursor gates from routine readiness and retain optional historical checks. Treat the reported organizer change as unverified; preserve sponsor requirements. | Match actual development workflow without claiming that conflicting public rules or submission compliance have been resolved. |
| 2026-10-22 | rcc00n / Codex, explicit human team-approved amendment | Next.js frontend; Django auth, administration and web API; dedicated persistent SQLite portal database. Typed read-only integration adapter pending reasoning contract. | Clarify team ownership without changing data or reasoning architecture; isolated lightweight VPS deployment. |
| 2026-10-22 | Yelysei / Claude | Ten stories a day is a cap, not a target: an absolute impact bar scored on an open rubric, confirmation as a gate, no minimum, quiet days stated plainly; an "Also today" roundup carries everything below the bar | Padding to ten dilutes the product; saying "nothing important today" builds trust |
| 2026-10-22 | Yelysei / Claude | Stories are short articles built only from verified claims: facts with sources, attributed statements, "not confirmed" at the end, fixed order, no evaluation and no "why it matters"; photos only from public-domain or openly licensed sources, with credits; the spectrum analysis is an appendix | Readers form their own view from facts; section headings read like a dashboard, and evaluation hides in "why it matters" |
| 2026-10-22 | Yelysei / Claude | Interface in the manner of Apple News: topic cards with a photo and a rounded display font, text instead of metrics, analysis behind links; type and colors as in "User account and interface" | A few readable elements beat many metrics (agreed with Vadim); a first draft felt like an analytics console |
| 2026-10-22 | Yelysei, Vadim, Nastya / team chat | Work split: Nastya — data collection, Yelysei — analysis and reasoning, Vadim — interface; one branch per member, `master` only through pull requests; portal temporarily at quorum.raccncode.com; user accounts via Django | Start building in parallel without stepping on each other |
| 2026-10-22 | Yelysei / Claude | Repository documentation, including this file, is written in English | Readable for the judges and for the whole team |
| 2026-10-22 | Yelysei / team discussion in chat, written up with Claude | First version: MVP scope, principles for handling facts, four rating modes and cohorts, model-based selection of major news, source list, user account, stack, demo, what comes after the hackathon | Fix the team's agreements before the source audit and the architecture design begin |
