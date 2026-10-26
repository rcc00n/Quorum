# Landing page plan (WEB-UX-01) — for approval before building

Anastasia / Claude Code, 2026-10-25. Branch `anastasia/web-ux`, PR into `integration`, Vadim reviews. Scope from Yelysei's proposal (Issue #2 6404484130 item 1), recorded in DECISIONS › User account and interface item 11. Tokens: [web/DESIGN.md](../../web/DESIGN.md). Nothing below is built yet.

## Starting point: Yelysei's prototype

Anastasia sent the Claude Design canvas "Quorum — app screens" (claude.ai/artifact/GxiEuhPNPSzH9SUjKjvYLX) as the stylistic start. Its look is now the token set in `web/DESIGN.md`: white page, rounded display face, crimson date and button, 20 px photo cards with a credit, pill chips and input, grey "Also today" panel, dark sign-up. The landing takes that look. Where the prototype's screen logic is older than the decisions, the decisions win:

| In the prototype | Decided since | Where it shows on the landing |
| --- | --- | --- |
| "up to ten verified stories a day for each" | Up to ten is a cap; no minimum; a quiet day says so | Section 3 and 7 |
| "34 outlets · read three ways across the spectrum" | Four rating modes (AllSides, MBFC, Ad Fontes, averaged); 40 sources | Sections 3 and 6 |
| Topic typed free, no search over existing topics | Search over existing `topics` names before creating a slug | Not on the landing (WEB-UX-02) |
| No waiting state for a new topic | "Collecting since …, N publications so far, edition after the 05:30 New York cut" | Section 7, one line (WEB-UX-03 builds the page) |
| Home card "3 stories today" | Same, plus "No story crossed the bar today" as a real outcome | Section 3 |

## Anastasia's visual brief (2026-10-25, after the first draft)

Seven references (editorial sites and posters: black type on paper, hairlines, columns, typewriter cadence, brackets, puzzle) and notes, taken as inspiration, not as a spec: newspaper aesthetics for the identity; a journalist's words about honest information or democracy on the landing; headlines that rewrite themselves letter by letter; the page as a statement, "What is truth?" answered with what we believe; truth as a puzzle assembled from facts; perhaps the whole site formatted like a printed paper; perhaps a quiet chat field under an article to ask the agent.

What this changes in the plan: the page is laid out as a front page (masthead, date line, hairline rules, narrow columns); the hero gets the typewriter over the three real Reuters titles of one re-edited story from the evidence file (the chain-once rule shown, not told); section 2 becomes "What is truth?" with the project's own definition; a quotation from a journalist in the public domain opens section 7 (C. P. Scott, 1921). Not built: the agent chat (DECISIONS › Daily editions: the web app calls no model; it would be a product decision for Yelysei) and a full newspaper restyle of the app pages (WEB-UX-04). Vadim's approval of the handoff was given in person; the landing is not held for his thread answer (Anastasia, 2026-10-25).

**Review of the first build (Anastasia, 2026-10-26):** the style is approved; the red accent goes (it read as a mobile-carrier line) in favour of a newspaper palette of black, white, warm greys and brown, recorded in DECISIONS item 9 and `web/DESIGN.md`; the hero topic should be a lighter one than the war, climate policy if a real artefact for it exists, otherwise the text change waits for the next PR.

## Who it is for, what it must do

Two readers: a judge who has four minutes and wants to know whether this is an agent system with real verification loops, and a visitor who wants to know what they would get. One page answers both: the product in one sentence, a real artifact up front, the loop structure with its limits, each sponsor named by the job it does, the limits said plainly, the team. Primary action: create an account and choose topics. Secondary: read how one day is checked.

## Facts the copy rests on (with the source of each)

| Fact | Source |
| --- | --- |
| Quorum takes one event, collects publications across the spectrum and official documents, separates facts from claims, verifies, shows framing per cohort; every conclusion links to its sources | DECISIONS › What we are building; README |
| Open Agent Hackathon 2026, Track 03 Reasoning Architecture, 22–27 October 2026 | DECISIONS › What we are building |
| 40 sources in the registry: agencies, left and right outlets in two tiers, WSJ, official bodies (Federal Register, Congress.gov) | `collectors/sources.csv` (40 rows), DECISIONS › Sources |
| Real Zetaris query, 2026-10-24 edition window of `russia-ukraine-war`: 86 publications from 17 sources; 50 left-flank, 19 right-flank, 17 agencies/unrated; 58 with full text, 28 headline and lead; the two SQL statements | `collectors/zetaris/evidence/russia-ukraine-war_2026-10-24.json` (committed, sanitized, run 2026-10-24 14:32Z) |
| The graph: plan → cluster → score → extract claims → research ⇄ verify (≤ 2 rounds) → blind fact-check → adjudicate → third blind review on disagreement → escalate → frame → write ⇄ critique (≤ 3 drafts) → roundup → publish; every node writes a trace row | `docs/ARCHITECTURE.md` § 5 |
| Code decides, models read: confirmation rule, spread vs confirmation, bar score, cap, cohort shares, article order and adjudication are code; stance, claims, framing labels and prose are model calls | ARCHITECTURE § 2 |
| A fact is a signed document or a claim confirmed by two independent groups; ten reprints of a wire story are one piece of evidence; a corrected publication is not evidence | DECISIONS › Principles for handling facts |
| Impact bar: legal force, reach, irreversibility, confirmation; shown at ≥ 6 with confirmation ≥ 1; up to ten a day, no minimum; "No story crossed the bar today" is a real outcome (it was the outcome on 2026-10-24) | DECISIONS › Selecting major news, › Still to clarify |
| Four rating modes: AllSides, MBFC, Ad Fontes, averaged; cohorts by threshold | DECISIONS › Spectrum ratings and cohorts |
| Zetaris is the only read path for agents; Nemotron 3.5 Lightning on the main lane and Nemotron 3 Ultra 550B as the blind fact-checker and reviewer; Meterless Nightshift supported as the primary provider with per-call receipts; canonical runs so far on NVIDIA's direct route; the H-MEM engine work is open (PR #6) | ARCHITECTURE § 7; `reasoning/README.md` › Decisions 2026-10-23/24/25; Yelysei's guard in 6404484130 |
| One edition per topic per day after the 05:30 New York cut, started by the team on the owner's machine; the web app calls no model | DECISIONS › Daily editions for users |
| A new topic's first edition is thin; the site says so | same |
| Paywalled outlets count by headline and lead; robots.txt denials drop to level 2 | DECISIONS › Sources |
| The preview on the site today is a FICTIONAL dry-run sample; real publication is not enabled yet | README; web/README; DECISIONS › Reasoning 1.0 development presentation |
| Team: Yelysei Shkirpan (reasoning), Anastasia Shkirpan (data collection; portal look and UX), Vadim Rudenko (web platform, backend, deployment) | DECISIONS › Stack and work blocks; git log |

Not stated anywhere on the page: testimonials, user counts, prices, "every call runs through Meterless", any number that is not in a committed file.

## Sections and copy

Headline sizes and tokens per `web/DESIGN.md`. Eyebrows are monospace. Copy is final unless marked `[?]`.

### 0. Header
Brand · How it works · Where it loops · Limits · Team · **Sign in** · **Choose your topics** (primary, → `/register`).

### 1. Hero
Eyebrow: `OPEN AGENT HACKATHON 2026 · TRACK 03 · REASONING ARCHITECTURE`
H1: **The news, with its working shown.**
Lead: Quorum takes one event, reads how outlets across the spectrum and official bodies reported it, separates what is known from what is claimed, and shows you the evidence under every line.
Buttons: **Choose your topics** → `/register` · See how one day is checked → `#loop`
Typewriter under the H1: the three Reuters titles of 24 October 2026 09:13 UTC from the evidence sample, rewriting one into the next ("Ukraine says Starlink back to normal after week of throttling" → "Starlink in Ukraine back to normal after week of throttling" → "Ukraine says Starlink and Starshield operating at 400 kph after week of throttli…"), captioned "One story, edited three times in one morning. Quorum counts it once."
Artifact (right): a card titled `russia-ukraine-war · edition 24 Oct 2026 · read through Zetaris`, with four figures: 86 publications · 17 sources · 50 left / 19 right / 17 agencies & unrated · 58 full text / 28 headline and lead, a "Show the SQL" disclosure with the two statements, and the caption "Real query over the collected corpus, 24 October 2026 14:32 UTC, data-collection@4e1be86. No article text is stored or shown."

### 2. What is truth? (two columns)
H2: **What is truth?**
Answer, set large: **We believe a truth is a signed document, or a claim confirmed by sources that do not depend on each other.** Everything else is a statement, and is shown as one.
Then the problem, small: Two readers, two sets of facts.
A Democrat does not see the facts a Republican sees, or does not weigh them. A Republican, the other way round. Each gets one source and its interpretation. Quorum gives the fact first, what happened, and on request how each outlet and each side told it.

### 3. What you get (four items, from the decided UI)
H2: **One card per topic. Then the article, then the appendix.**
1. **Home.** One card per topic you follow: the lead story and how many crossed the bar today, or "No story crossed the bar today".
2. **The story as an article.** Three to four minutes, built only from verified claims: what happened, what the parties say, what is not confirmed. Written by rules, no evaluation added.
3. **Across the spectrum.** What left and right outlets highlighted, left out and how they worded it, by cohort, under the rating mode you pick: AllSides, MBFC, Ad Fontes or the average.
4. **Also today.** One line for every event below the bar, with its source and status: confirmed, disputed, statements only, single source, unverified.

### 4. Where it loops (the judges' section)
Eyebrow: `THE GRAPH · ONE RUN PER TOPIC PER DAY`
H2: **Code decides. Models read. Every step leaves a row.**
Numbered steps, each with "model / code" and the loop it belongs to:
01 **Plan and cluster** — documents of the day grouped into events; the model writes one structured key per document, code buckets them. 
02 **Score the bar** — the model reports the legal status and the state of the act; code maps them to points and sets `above_bar`. Cap of ten by code.
03 **Extract claims** — atomic, checkable, each with the sentence it came from.
04 **Research ⇄ verify** — passages for and against each claim; a contradiction counts only when the model quotes it verbatim and code finds the words in the passage. A thin claim sends the event back for a second round. At most two.
05 **Blind fact-check** — a second agent, different model, same corpus, nothing from the first. Disagreement → a third blind pass chooses between the two evidence chains; code validates its answer. Still unresolved → "disputed".
06 **Write ⇄ critique** — the article draft against the writing rules; rejected drafts go back, at most three; a third rejection is published flagged, never silently dropped or approved.
07 **Roundup and publish** — one immutable snapshot per topic and day, with the trace.
Side note: "An event that crosses the bar on points with no confirmed claim leaves the stories and goes to the roundup as 'reported, not confirmed'."

### 5. A real trace
H2: **Read the trace, not the summary.**
A trace block of rows (node · decision · reason · model · ms). Data source, in order of preference: (a) the latest published snapshot from the portal's own store when one exists; (b) until then, the committed dry-run sample, with a visible label "Dry run · fictional content · real shape" and no story text shown. `[?]` Yelysei: can you give one public-safe trace excerpt (ten rows: node, decision, reason, model, ms, no text) from a canonical run to commit under `docs/examples/`? Then (b) becomes real.

### 6. Each sponsor does one job
H2: **What runs where.**
- **Zetaris** — every read of the corpus is SQL through Zetaris: sources, publications, official documents, previous days. The hero query is one of them.
- **NVIDIA Nemotron** — Nemotron 3.5 Lightning reads, labels and writes; Nemotron 3 Ultra 550B is the blind fact-checker and the third reviewer.
- **Meterless** — Nightshift is supported as the primary provider, with an exact model id per lane and a signed receipt per call. Canonical runs so far used NVIDIA's direct route; the Meterless engine integration is in progress. `[?]` Vadim/Yelysei: wording of the second sentence once PR #6 lands.
- **Development** — Codex and Claude Code, one branch per person, every decision recorded in the repository. `[?]` Team: what we say about Cursor (public rules still name it; `docs/RULES_CHECK.md`).

### 7. Limits, said plainly
Quotation above the heading: “Comment is free, but facts are sacred.” — C. P. Scott, Manchester Guardian, 1921.
H2: **What it does not do.**
- Forty US sources in English; no social networks.
- Paywalled outlets count by headline and lead. A site that forbids our crawler counts the same way.
- One edition per topic per day, prepared after the 05:30 New York cut by the team. A topic you add today has few documents until feeds accumulate; the page says so.
- Positions on the spectrum come from AllSides, MBFC and Ad Fontes, not from us.
- No story on a quiet day. On 24 October 2026, the first real day, no event crossed the bar.
- What you see in the preview today is a labelled fictional sample until the first real edition is published.

### 8. Team
H2: **Three people, one tracker.**
Yelysei Shkirpan — reasoning and the agent graph · Anastasia Shkirpan — data collection, portal look and UX · Vadim Rudenko — web platform, backend, deployment. Built for the Open Agent Hackathon 2026, Track 03. Link: the repository. `[?]` Each person: one line about yourself, or none.

### 9. Final call and footer
H2: **Choose your topics. Read the working.** Button → `/register`. Footer: brand, "Evidence under every line.", Sign in, repository link, hackathon link.

## Implementation notes

- Files: `web/app/page.tsx` (rewritten), `web/components/landing/*.tsx` (hero artifact, loop, trace, sponsors), landing CSS appended to `web/app/globals.css` under a `.landing` scope so other pages do not change in this PR, `web/app/layout.tsx` (+ Nunito import), `web/package.json` and lockfile (+ `@fontsource-variable/nunito`), the evidence JSON imported at build time from `collectors/zetaris/evidence/` (static import, no runtime read of the collection database).
- Not touched: `web/lib/*`, backend, auth, API, other routes. WEB-UX-04 restyles the rest later.
- Tests: `web/tests/browser.cjs` already loads `/` and checks overflow; add `web/tests/landing.cjs` (Node, no browser): the rendered page contains every section anchor, the hero figures equal the evidence file's counts, and the fictional label is present whenever the trace is the dry-run sample. No existing test is changed.
- Checks before the PR: `bash deploy/build-web.sh` (build + typecheck), the new test, phone 390 / tablet 768 / desktop 1440 screenshots outside Git, keyboard-only pass through header, buttons and the SQL disclosure. Light theme only; no dark mode exists on the portal.
- Collision: Vadim has not yet answered which web files he edits; his open PRs touch no `web/` file. Building `page.tsx` before his answer is the one risk.

## Decisions to record with the code

web/README.md › Decisions: landing content comes only from committed files or a published snapshot; the hero artifact is the Zetaris evidence file; fonts from npm; section anchors are the test contract.
