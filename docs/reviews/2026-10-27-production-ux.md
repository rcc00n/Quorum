# Production UI/UX audit — 27 October 2026

Owner: Vadim / rcc00n / Codex. Scope: WEB-EDITION-NAV-01 and WEB-AUTH-RETURN-01 on `feature/web-edition-navigation`. Canonical release tracker: [Issue #2](https://github.com/rcc00n/Quorum/issues/2). This is an audit and implementation record, not a competing feature tracker or production release claim.

## Context and method

Read fetched master AGENTS.md, DECISIONS.md, the web README/design system, release checklist, portal verification and reasoning §8 contract; inspected owner branch history and Issue #2 discussions, including the #47/#48 review and #52/#53 boundaries. The accepted direction is a newspaper that shows its working: Schibsted Grotesk, paper/ink/umber, restrained composition and progressive evidence disclosure. Preserve that direction and the existing article/source wording.

Actual production Chromium used the existing ordinary judge account at https://quorum.raccncode.com. Inspected public landing/login/register at 390 px and authenticated Today, dated Today, History, My topics, Sources and the installed story at 1440/768/390 px. No preferences, profile, passwords, content, provider configuration or services were changed; only normal login/logout metadata. Private screenshots and observations remain outside Git. No horizontal page overflow or JavaScript page errors were observed. This does not establish full accessibility, performance or processing integration certification.

Visual thesis: keep the paper-and-ink reading surface and make the selected edition a reliable place to return to. Content plan: retain existing page headers and reading hierarchy; improve only date controls and entry/return paths. Interaction thesis: one-tap calendar-day steps, browser-native history, exact shared-story continuation after sign-in. Reuse current motion and reduced-motion behavior; no extra decoration or dependency.

## Findings and disposition

| Priority | Finding and evidence | Action / ownership |
| --- | --- | --- |
| P1 | `/history?date=2026-10-26` shows 27-Oct, so the installed edition is missed. Changing the dashboard calendar to 25-Oct leaves `?date=2026-10-26`; reload restores 26-Oct. Topic selection also exists only in local state. | WEB-EDITION-NAV-01: explicit date/topic URL state, contextual History and shared calendar controls. Browser Back/Forward must restore the same filters. |
| P1 | Portal authentication discards the requested route; Auth always returns to `/dashboard`. A shared historical story therefore loses its date/revision/pane. | WEB-AUTH-RETURN-01: validated local return route with exact query/hash; ordinary sign-in and first setup remain unchanged. |
| P1 | The partial/stale/error dashboard branches remove the board, including its date selector. The real local partial fixture reproduced this while testing navigation with no followed story. | WEB-EDITION-NAV-01: retain calendar controls beside those unchanged honest states so another date remains reachable. This finding is from the local real-HTTP boundary, not a claimed production failure. |
| P1 | Today's real pending screen has four large waiting cards and no way to discover which historical dates contain installed editions. A working 26-Oct story exists on its dated route. | Calendar steps reduce friction now. A true installed-edition index needs a web API/owner contract; never guess a latest date or relabel old news as today. Deferred from this narrow fix. |
| P1 | The installed story retains an evaluative/predictive producer headline, and its article composition fails the established article guard. The portal correctly shows Requires editorial review and the fallback presentation. | Reasoning/editorial owner: fix future producer output. Preserve this immutable original, review label and evidence; do not cosmetically rewrite its words in the frontend. |
| P2 | Settings says “Live analysis is pending” in the catalog note although an installed historical analysis is available. It mixes registry freshness with edition availability. | Proposed wording correction needs the product wording owner's review; leave source/availability semantics explicit. |
| P2 | “My topics” opens with profile fields before topic selection; the archive/topic toolbar also draws “Evidence first” like a tab although it is inert. | Follow-up for the UX owner: prioritize topic selection and remove false interaction cues; retain account fields and evidence access. |
| P2 | First setup supports existing catalog topics; the agreed typed-request/status and delivery-time flows remain incomplete. Topic names include mechanical capitalization, e.g. “Ai regulation export controls”. | Existing platform/data handoff gap, not a styling problem. Use reviewed catalog labels and genuine statuses; do not simulate creation or progress. |
| P2 | The source chart needs stronger mark identity, a grouped closed ledger and clearer audience denominators. | Already implemented in Anastasia's #52; do not duplicate it. Its missing-audience correction/review remains separate. |
| P2 | Landing execution metadata and raw Impact details compete with the main values. | Already covered by #53; pending explicit look approval. Do not silently include or deploy it here. |

## Preserve

The landing's evidence-led hero, type/grid/wireline, real counts/date/context; the coherent paper identity across gates and workspace; the Read/Evidence/Coverage/Map/Trace workspace and local search; explicit pending/provisional/review/DEMO labels; native source/provenance disclosures; reduced motion. These work and do not need another visual redesign. Missing-photo treatment is already an explicit owner decision, not a reason to invent a news image.

## Validation and release boundary

Production build/typecheck, pure calendar/redirect guards, current/public-fixture TypeScript contract and existing rating/editorial/search/cut/topic/spectrum geometry checks passed. The focused real Django/Next/Chromium navigation suite passed: exact sign-in return including date/revision/pane, History context, date/topic refresh and Back/Forward, missing-topic preservation, recovery controls, local today, 44 px targets and no page overflow/errors at 1440/768/390/320. [Local review captures](2026-10-27-edition-navigation/README.md) contain no production account or real news.

The complete `boundary.cjs` regression also passed: existing auth/registration/onboarding/preferences/profile/logout/admin boundaries, reader/search/source/keyboard/reduced-motion checks, corrections/rollback/revisions, rich DEMO analysis, retry and layout checks. The new checks supplement the existing assertions.

`boundary.cjs --reasoning` passed the exact main/empty/partial canonical envelopes, articles/evidence, all 45 main trace steps, four rating modes and context/XSS/retry/responsive checks. `--reasoning --roundup-checks` passed producer-attributed skipped-check behavior. These are explicitly fictional local fixtures, not processing or sponsor evidence. Build receipt v2 matches current web source and standalone/static bytes. The staged public-index scanner and its three secret/asset regressions passed; only the three visually inspected, hash-pinned local review PNGs are newly permitted.

`scripts/doctor.sh --offline` and `scripts/verify-all.sh --offline`: each 5 PASS / 0 FAIL / 1 BLOCKED (live integration intentionally untested in offline mode). No provider call was made. Neither this audit nor a local fixture pass changes production. Merge/release retain the existing owner review, exact-head CI and guarded deployment gates.
