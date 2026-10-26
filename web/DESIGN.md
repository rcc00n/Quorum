# Quorum portal — design system

Owner: Anastasia (portal look and UX, `anastasia/web-ux`), 2026-10-25. The identity itself is decided in [docs/DECISIONS.md › User account and interface](../docs/DECISIONS.md#user-account-and-interface) item 9; this file turns that decision into named tokens so pages use names, never raw values. Product and wording stay with Yelysei, the web platform with Vadim.

Direction, in one line (Anastasia's brief, 2026-10-25: newspaper aesthetics, a journalist's words about honest information, truth assembled from facts): a newspaper that shows its working. White paper, black ink, one red mark, rounded display type over a system body face. Calm and legible like Apple News; honest and inspectable like a trace.

Starting point (2026-10-25, Anastasia): Yelysei's prototype "Quorum — app screens" (Claude Design canvas, claude.ai/artifact/GxiEuhPNPSzH9SUjKjvYLX; sign-up → home → topic → story, plus "Also today"). Read in the browser, five frames. What it fixes: white page, rounded display face (Nunito-like) at about 56 px for page titles and 40 px on cards, a crimson date line above the title, grey secondary text, full-bleed photo cards with 20 px corners, white type and a small credit over the photo, "3 stories today" style one-liners, pill chips and a pill input, a light-grey rounded panel for "Also today", a dark near-black sign-up screen with a three-circle logo. Its screen logic predates the newest decisions (one edition a day prepared after the cut; topic search over existing names; the waiting state for a new topic; four rating modes), so the look is taken from it and the flows from DECISIONS.

Anastasia's references (2026-10-25, seven images: Peter Jellitsch's site, Les Garçons Sauvages, 5pm.fr, the MOMAT Takashi Homma poster, the Dutch Design Week "(In No Particular Order)" poster, RM's puzzle tracklist): black ink on white or cream paper, type as the picture, hairline rules and narrow columns like a printed page, a typewriter cadence (letters arriving one by one, a line rewriting itself), brackets and puzzle pieces as "truth assembled from facts", photographs small and documentary. Their grotesque typefaces are not adopted: the display face stays rounded per DECISIONS item 9 and the prototype; the newspaper structure, the rules, the columns, the typewriter motion and the bracket motif are.

Two of the reference sites were also opened live (2026-10-25): peterjellitsch.com sets everything in one grotesque at one weight, navigation at 60 px as the page's picture, body 18 px, black on paper; 5pm.fr the same idea in Neue Haas Grotesk at 17 px. The lesson kept: one display face, few sizes, type as the image; the grotesque itself is not adopted (item 9). lesgarconssauvages.com could not be opened.

What was compared besides it (2026-10-25, looked at in the browser, UXKIN not connected): the two sites Yelysei named as the quality bar, GreenTrace (greentrace-eudr.higgsfield.app) and Saphan (saphan.ai). Both are dark, one typeface each (Geist; IBM Plex Sans with Schibsted Grotesk headings), a 64–72 px headline that states the product's question, monospace eyebrows, and a real artifact as the hero visual: a verdict with its data, a trace walked step by step, a "do not trust it, check it" section. We keep the light identity already decided and borrow the structure: the real artifact up front, the loop steps numbered, each sponsor named by the job it does, limits said plainly.

## Color

Light theme only. No dark mode in this phase (the portal has none; add tokens under `prefers-color-scheme: dark` when it does).

| Token | Value | Role |
| --- | --- | --- |
| `--paper` | `#ffffff` | Page background. |
| `--paper-2` | `#f6f5f2` | Quiet panels, alternating sections, code and trace blocks. |
| `--ink` | `#111111` | Headlines and body text. |
| `--ink-2` | `#4a4a4a` | Secondary text, captions, muted labels (6.9:1 on paper). |
| `--rule` | `#e6e3dd` | Hairlines, borders, table rules. |
| `--red` | `#d81e4b` | The one accent, the prototype's crimson (sampled by eye from the canvas; exact value to confirm with Yelysei): the date line, the primary button, the silence line, links on hover. Never for text smaller than 14 px. |
| `--red-ink` | `#b0173c` | Button hover, accent text at small sizes (5.9:1 on paper). |
| `--night` | `#141414` | The dark sign-up and first-setup screens from the prototype (white type, `--red` button, white pill input). Nowhere else. |
| `--cohort-left` | `#1d4ed8` | Left cohort, major outlets. |
| `--cohort-left-minor` | `#93c5fd` | Left cohort, minor outlets. |
| `--cohort-right` | `#c8102e` | Right cohort, major outlets (same red). |
| `--cohort-right-minor` | `#fca5a5` | Right cohort, minor outlets. |
| `--ok` | `#1d6b3a` | Confirmed. |
| `--warn` | `#8a5a00` | Disputed, needs review. |
| `--focus` | `#1d4ed8` | Focus ring, 3 px, offset 3 px. |

Status is said in words ("Confirmed", "Disputed", "Statements only"); colour only underlines, never replaces the word. Cohort colours appear only where cohorts are compared, never as decoration.

## Typography

| Role | Family | Notes |
| --- | --- | --- |
| Display (h1, h2, topic names, numbers) | `ui-rounded, "Nunito Variable", system-ui, sans-serif` | SF Pro Rounded on Apple devices; Nunito packaged from npm (`@fontsource-variable/nunito`) elsewhere. No request to any font host. Weight 700–800, tracking −0.02 em. |
| Body | `-apple-system, system-ui, "Inter Variable", sans-serif` | Inter from npm as the fallback, already packaged. Weight 400, 500 for emphasis. |
| Trace, code, ids | `ui-monospace, "SF Mono", Menlo, monospace` | Eyebrows and trace rows, 12–13 px, tracking 0.04 em, uppercase only for eyebrows. |

Scale (px / line height): 13/1.5 caption · 15/1.6 small · 17/1.65 body · 21/1.45 lead · 28/1.25 h3 · 40/1.15 h2 · 56–80/1.0 h1 (`clamp(44px, 7vw, 80px)`). Body text never below 15 px; measure 60–72 characters (`max-width: 38rem`).

## Spacing and layout

8-point scale: 4, 8, 12, 16, 24, 32, 48, 64, 96, 128. Section padding 96 px desktop, 64 px tablet, 48 px phone. Content width 1120 px; reading column 38 rem. Side gutter 6% desktop, 24 px tablet, 16 px phone. Grid: 12 columns, 24 px gap.

## Shape and depth

Radius: 20 px photo cards and panels (the prototype's), 12 px small cards, 999 px for buttons, chips and the topic input (pills, as in the prototype), 4 px for plain text inputs. No shadows; depth comes from `--paper-2` panels and hairlines. One exception: the sticky header gets a 1 px rule, not a shadow.

## Motion

Transitions 180 ms ease-out on colour and transform only. Entrance animations 500 ms, once, on the hero. One typewriter: a headline that rewrites itself letter by letter (about 40 ms per character, a 1.6 s hold per line) over real titles only, with the finished line always present in the DOM for readers and screen readers. Everything off under `prefers-reduced-motion: reduce`.

## Components

- **Primary button**: `--red` background, white text, pill, 48 px tall, 15 px 600, trailing arrow (prototype's "Continue →"). Hover `--red-ink`; focus ring `--focus`; disabled 50% opacity, cursor default.
- **Secondary button**: `--ink` text, 1 px `--ink` border, transparent background. Hover: `--paper-2` background.
- **Quiet link**: `--ink` text, underline on hover in `--red`.
- **Eyebrow**: monospace 12 px uppercase, `--ink-2`.
- **Trace row**: monospace 13 px, three columns (node · decision · reason), hairline below, `--paper-2` background for the block.
- **Card**: `--paper` on `--paper-2` or hairline border, 10 px radius, 24 px padding, no shadow.
- **Input**: 48 px tall, 1 px `--rule` border, 4 px radius, label above, error in `--red-ink` below.
- **Header**: 72 px, brand left, three links right, primary button last; collapses to brand + button under 700 px.
- **Footer**: hairline, brand, one line, links.

## Icons and imagery

Lucide, 20 px, stroke 1.75, `--ink-2`. Photos only where the product shows them (topic cards, stories) and always with a credit; the landing uses no stock photography and no illustration. Diagrams are the product's own artifacts: trace rows, cohort grids, the graph.

## Decisions

| Date | Who | What | Why |
| --- | --- | --- | --- |
| 2026-10-25 | Anastasia / Claude Code | This file holds the portal's tokens; the identity decision stays in DECISIONS.md item 9. Look taken from Yelysei's prototype canvas (white, rounded display, crimson accent, 20 px photo cards, pills, dark sign-up); flows from DECISIONS where the prototype is older than them. Light theme only for the hackathon. Structure borrowed from GreenTrace and Saphan (real artifact up front, numbered loop, sponsors by job, honest limits); their dark palette and typefaces are not. | One place for the values, so the landing, the forms and the brief pages stop drifting; the prototype is the team's agreed look and matches item 9; changing it would need a new DECISIONS row. |
