# Quorum portal — design system

Owner: Anastasia (portal look and UX, `anastasia/web-ux`), 2026-10-25. The identity itself is decided in [docs/DECISIONS.md › User account and interface](../docs/DECISIONS.md#user-account-and-interface) item 9; this file turns that decision into named tokens so pages use names, never raw values. Product and wording stay with Yelysei, the web platform with Vadim.

Direction, in one line (Anastasia's brief, 2026-10-25: newspaper aesthetics, a journalist's words about honest information, truth assembled from facts): a newspaper that shows its working. White paper, black ink, warm greys, one umber mark, rounded display type over a system body face. Calm and legible like Apple News; honest and inspectable like a trace.

Starting point (2026-10-25, Anastasia): Yelysei's prototype "Quorum — app screens" (Claude Design canvas, claude.ai/artifact/GxiEuhPNPSzH9SUjKjvYLX; sign-up → home → topic → story, plus "Also today"). Read in the browser, five frames. What it fixes: white page, rounded display face (Nunito-like) at about 56 px for page titles and 40 px on cards, a crimson date line above the title, grey secondary text, full-bleed photo cards with 20 px corners, white type and a small credit over the photo, "3 stories today" style one-liners, pill chips and a pill input, a light-grey rounded panel for "Also today", a dark near-black sign-up screen with a three-circle logo. Its screen logic predates the newest decisions (one edition a day prepared after the cut; topic search over existing names; the waiting state for a new topic; four rating modes), so the look is taken from it and the flows from DECISIONS.

Anastasia's references (2026-10-25, seven images: Peter Jellitsch's site, Les Garçons Sauvages, 5pm.fr, the MOMAT Takashi Homma poster, the Dutch Design Week "(In No Particular Order)" poster, RM's puzzle tracklist): black ink on white or cream paper, type as the picture, hairline rules and narrow columns like a printed page, a typewriter cadence (letters arriving one by one, a line rewriting itself), brackets and puzzle pieces as "truth assembled from facts", photographs small and documentary. Their grotesque typefaces are not adopted: the display face stays rounded per DECISIONS item 9 and the prototype; the newspaper structure, the rules, the columns, the typewriter motion and the bracket motif are.

Two of the reference sites were also opened live (2026-10-25): peterjellitsch.com sets everything in one grotesque at one weight, navigation at 60 px as the page's picture, body 18 px, black on paper; 5pm.fr the same idea in Neue Haas Grotesk at 17 px. The lesson kept: one display face, few sizes, type as the image; the grotesque itself is not adopted (item 9). lesgarconssauvages.com could not be opened.

What was compared besides it (2026-10-25, looked at in the browser, UXKIN not connected): the two sites Yelysei named as the quality bar, GreenTrace (greentrace-eudr.higgsfield.app) and Saphan (saphan.ai). Both are dark, one typeface each (Geist; IBM Plex Sans with Schibsted Grotesk headings), a 64–72 px headline that states the product's question, monospace eyebrows, and a real artifact as the hero visual: a verdict with its data, a trace walked step by step, a "do not trust it, check it" section. We keep the light identity already decided and borrow the structure: the real artifact up front, the loop steps numbered, each sponsor named by the job it does, limits said plainly.

## Color

Light theme only. No dark mode in this phase (the portal has none; add tokens under `prefers-color-scheme: dark` when it does). A newspaper's palette, chosen by Anastasia on 2026-10-26: black ink on white paper, warm greys, one brown accent. No red in the identity (DECISIONS item 9, amended 2026-10-26); the prototype's crimson is superseded here.

| Token | Value | Role |
| --- | --- | --- |
| `--paper` | `#ffffff` | Page background. |
| `--paper-2` | `#f4f1eb` | Warm grey panels, alternating sections, code and trace blocks. |
| `--ink` | `#141414` | Headlines, body text, the primary button, the masthead's double rule. |
| `--ink-2` | `#5f5a53` | Secondary text, captions, muted labels, eyebrows (6.4:1 on paper). |
| `--rule` | `#dcd6cc` | Hairlines, borders, table rules. |
| `--umber` | `#7b5634` | The one accent: the date line, step numbers and markers, the caret, link underlines on hover, the brackets (6.6:1 on paper). Never a fill behind white text smaller than 15 px. |
| `--umber-ink` | `#5a3e25` | Button hover, accent text at small sizes. |
| `--night` | `#141414` | The dark sign-up and first-setup screens from the prototype (white type, ink button inverted to paper, white pill input). Nowhere else. |
| `--cohort-left` | `#1d4ed8` | Left cohort, major outlets. Data colour in cohort views only. |
| `--cohort-left-minor` | `#93c5fd` | Left cohort, minor outlets. |
| `--cohort-right` | `#b91c1c` | Right cohort, major outlets. Data colour in cohort views only. |
| `--cohort-right-minor` | `#fca5a5` | Right cohort, minor outlets. |
| `--ok` | `#1d6b3a` | Confirmed (status word underlined, never a pill). |
| `--warn` | `#8a5a00` | Disputed, needs review. |
| `--focus` | `#141414` | Focus ring, 3 px, offset 3 px (sits on the paper around dark buttons). |

Status is said in words ("Confirmed", "Disputed", "Statements only"); colour only underlines, never replaces the word. Cohort colours appear only where cohorts are compared, never as decoration; the landing shows none.

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

- **Primary button**: `--ink` background, white text, pill, 48 px tall, 15 px 600, trailing arrow (the prototype's "Continue →" shape, in ink instead of crimson). Hover `--umber-ink`; focus ring `--focus`; disabled 50% opacity, cursor default.
- **Secondary button**: `--ink` text, 1 px `--ink` border, transparent background. Hover: `--paper-2` background.
- **Quiet link**: `--ink` text, underline on hover in `--umber`.
- **Eyebrow**: monospace 12 px uppercase, `--ink-2`.
- **Trace row**: monospace 13 px, three columns (node · decision · reason), hairline below, `--paper-2` background for the block.
- **Card**: `--paper` on `--paper-2` or hairline border, 10 px radius, 24 px padding, no shadow.
- **Input**: 48 px tall, 1 px `--rule` border, 4 px radius, label above, error in `--umber-ink` below, said in words.
- **Header**: 72 px, brand left, links centre, primary button last, a 3 px double rule below (the masthead rule of a printed paper); collapses to brand + button under 1000 px.
- **Footer**: hairline, brand, one line, links.

## Icons and imagery

Lucide, 20 px, stroke 1.75, `--ink-2`. Photos only where the product shows them (topic cards, stories) and always with a credit; the landing uses no stock photography and no illustration. Diagrams are the product's own artifacts: trace rows, cohort grids, the graph.

## Decisions

| Date | Who | What | Why |
| --- | --- | --- | --- |
| 2026-10-26 | Anastasia / Claude Code | Palette without red: ink, paper, warm greys, one umber accent; primary button in ink; cohort colours leave the landing. Supersedes the crimson `--red` of the row below. | Anastasia's review of the first landing build: the red read as a mobile-carrier line; a newspaper's palette is strict and matches the direction. |
| 2026-10-25 | Anastasia / Claude Code | This file holds the portal's tokens; the identity decision stays in DECISIONS.md item 9. Look taken from Yelysei's prototype canvas (white, rounded display, crimson accent, 20 px photo cards, pills, dark sign-up); flows from DECISIONS where the prototype is older than them. Light theme only for the hackathon. Structure borrowed from GreenTrace and Saphan (real artifact up front, numbered loop, sponsors by job, honest limits); their dark palette and typefaces are not. | One place for the values, so the landing, the forms and the brief pages stop drifting; the prototype is the team's agreed look and matches item 9; changing it would need a new DECISIONS row. |
