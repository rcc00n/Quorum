# Quorum — project decisions

Updated: 2026-10-22 · First version by Yelysei Shkirpan · Source: team discussion and the agreed project description

This is the single source of truth for product and architecture. Code that contradicts this document is a bug either in the code or in the document; the latter is fixed by editing this file, never silently in code. How decisions are made and recorded is described in [AGENTS.md](../AGENTS.md), section "Decisions". The change log is at the end of this document.

## What we are building

Quorum is a multi-agent system that, for one event, collects publications from different sources, separates facts from interpretations, verifies claims against evidence, and shows how different parts of the political spectrum frame that event.

**Motivation.** Societies are polarized, and everyone lives in their own information bubble. A Democrat does not see the facts a Republican sees, or does not weigh them. A Republican, the other way round. Instead of one source with its interpretation, the user gets the fact: what happened. On request, statistics on how a given party or outlet interpreted that fact.

**Key feature.** Quorum does not retell the news. It investigates what is actually known, which claims contradict each other, what evidence exists, and how different sources interpret the same event. The goal is an AI that does not ask the user to trust its answer, but lets them verify every substantive conclusion.

**Context.** Team Quorum's project for the [Open Agent Hackathon 2026](https://hackathon.genai.works/event/open-agent-hackathon-2026), Track 03 Reasoning Architecture. Build window 22–27 October 2026; submissions close 27 October 23:45 UTC (19:45 New York). The judges expect an agent system with verification loops, not a linear pipeline.

## MVP scope

The MVP consists of the six features from the agreed project description plus five team decisions: topic selection, login, an independent fact-checker, four spectrum-rating modes, and model-based selection of major news.

| Feature | What it includes |
| --- | --- |
| 1. Multi-source intelligence | News from several independent sources: RSS, news APIs, official publications. Federated through Zetaris with SQL queries across sources. Grouping of publications about one event. |
| 2. Autonomous fact verification | The AI extracts checkable claims, looks for supporting and contradicting evidence, and requests additional sources when needed. It distinguishes confirmed facts, disputed claims, and what cannot yet be verified. It accounts for several publications retelling one primary source. |
| 3. Evidence-based reasoning | Every conclusion carries its sources and an explanation of the evidence it rests on. When sources contradict each other, the agent investigates the cause of the discrepancy. When evidence is insufficient, the system says so plainly. The user sees the verification process and can go to the originals. |
| 4. Neutral news brief | A short summary of the event without imposing a political interpretation. Clearly separated: what happened, statements by interested parties, what is still unknown. |
| 5. Narrative & framing comparison | How different sources cover one event: which facts they highlight, which they omit, which wording they use. Comparison of specific outlets and statements by political organizations. Every conclusion comes with examples from the source material. |
| 6. Interactive dashboard | Event feed and topic filter. Event page with facts, sources and disagreements. Comparison of coverage across sources. Drill-down into evidence and reasoning. |

**Added by team decision**

- Topic selection at first setup: the agents collect and analyze only those topics.
- Login and password. No subscription; free at first.
- An independent fact-checker in addition to cross-checking publications (see "Principles for handling facts").
- Four political-spectrum rating modes and a cohort diagram (see "Spectrum ratings and cohorts").
- The model selects the day's major news by impact on people's lives; coverage and silence per cohort are a separate fact (see "Selecting major news").

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

## Selecting major news

The model determines a news item's importance by its impact on people's lives, not by the number of sources that covered it. Silence of sources is itself useful information and is shown separately.

- **Candidates** are all events in the corpus, including official documents. An event nobody published cannot be seen by the system. The realistic case is "covered only by government bodies or by one or two sources".
- **An open importance rubric**, so the score is not merely the model's opinion: who is affected and how many people; scale; irreversibility; legal force (law, decree, court ruling). The score is shown together with the rubric and the reasoning trace.
- **Coverage and silence per cohort** is a separate, visible fact: "covered by N of M sources in the cohort". A whole cohort's silence on a major story is a highlighted line.
- **On the topic page:** the ten major news items of the day by this score.

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

The account is built around the topics the user selects. The interface is visually clear and uncluttered: a few readable metrics beat many unclear ones.

1. **Sign-in.** Login and password. No subscription; free at first.
2. **First setup.** The user picks the topics they care about. The agents collect and analyze only those.
3. **Topic page for today.**
    - The ten major news items of the day by the model's score.
    - A short summary: how the views of different parties are distributed.
    - Which views exist at all — with the spectrum diagram, so it is visible which outlets count as left and right, and the rating-mode switch.
    - Which views are popular: frequency of an interpretation across sources, share of outlets and audience per cohort.
    - Links to the sources the model found weighty enough as evidence.
4. **History** — a separate tab, by day, labeled like "digest for 10/12/2026".
5. **Shift in party positions** — under the topic, outside the days. Implemented after the hackathon; data accumulates from day one.
6. **Event page** — facts, parties' statements, what is unknown, disagreements, coverage comparison, drill-down into evidence and reasoning.

## Stack and work blocks

Data flows through Zetaris, reasoning runs on NVIDIA Nemotron and Meterless, and the interface and backend are Next.js + TypeScript. The architecture is an agent system with verification loops, not a linear pipeline; its detailed design is a separate task on the board.

| Layer | Technology | Role |
| --- | --- | --- |
| Data | Zetaris | Single data layer. SQL queries across different sources as if they were one database. |
| Reasoning | NVIDIA Nemotron, Meterless | Claim verification, agent processes. |
| Independent review | Additional LLMs | Independent review of complex conclusions, if the rules allow. |
| Interface and backend | Next.js + TypeScript | Portal: account, topic and event pages. |
| Development | Cursor / Codex / Claude Code — each team member's own | Rules for all assistants are in [AGENTS.md](../AGENTS.md). Verify the track requirements in HackOS: the event page lists NVIDIA, Zetaris, SpaceX AI and Meterless as sponsors. |

**Three work blocks**

1. Data collection: sources, APIs, databases.
2. Analysis and reasoning.
3. Frontend, interface, UI/UX.

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

Six questions the team has not closed yet.

- [ ] Whether the model's own rating is needed as a fifth mode already in the MVP. Default: no.
- [ ] Priority order of the elements on the topic page: what is visible at once, what opens on click.
- [ ] Which official government bodies are in the hackathon slice, and which event we take for the demo.
- [ ] Language of the interface and the demo: the judges are English-speaking.
- [ ] The track's requirements for sponsor technologies and development tools — verify on the challenge page in HackOS.
- [ ] Where the audience estimates for the Y axis and cohort shares come from.

## Decision log

Every change to this document gets a row here. Newest rows on top. Rules are in [AGENTS.md](../AGENTS.md), section "Decisions".

| Date | Who (human / tool) | What was decided | Why |
| --- | --- | --- | --- |
| 2026-10-22 | Yelysei / Claude | Repository documentation, including this file, is written in English | Readable for the judges and for the whole team |
| 2026-10-22 | Yelysei / team discussion in chat, written up with Claude | First version: MVP scope, principles for handling facts, four rating modes and cohorts, model-based selection of major news, source list, user account, stack, demo, what comes after the hackathon | Fix the team's agreements before the source audit and the architecture design begin |
