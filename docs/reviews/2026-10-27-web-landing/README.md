# Landing after the deck, 27 October 2026: review screenshots

Full-page captures at 1440 and 390 px for the PR of `anastasia/web-landing-polish` into `integration`, each page in
two halves so that every file stays under the public repository's 1 MB limit (`scripts/security-check.py`). The
landing renders only committed fixtures (`web/fixtures/landing/`): the real public headlines of the 24 October
window as the evidence file cuts them, the source registry, the loop limits and word lists from `reasoning.toml`,
the run graph, and the FICTIONAL dry-run trace sample, labelled "Dry run · fictional content · real shape" on the
page. No signed-in page, no account, no installed edition appears. Decisions: `web/DESIGN.md` › Landing after the
deck (the evening pass and its Polish sub-section) and the decision-log rows there.

| File | What it shows |
| --- | --- |
| landing-after-1440-0.png, landing-after-1440-1.png | After, 1440 px, the branch head on the production build, top and bottom half: the hero with the typed sentence, the compact evidence card and the three running lines; the sources instrument at the section's width with the reading on a grey tray; the two statement bands with the glow; the anatomy as the cabinet draws it; the run graph with its captions; the trace ledger; sponsors, limits, team; the footer. One type scale, one tray, one rhythm, hairlines only between paper sections. |
| landing-after-390-0.png, landing-after-390-1.png | After, 390 px, top and bottom half: the two buttons at the column's width, the card as an object, the lines, the field at 400 px with the selected mark's label, the captions as a list under the graph, the rows of the ledger stacked. |
| landing-before-1440-0.png, landing-before-1440-1.png, landing-before-390-0.png, landing-before-390-1.png | Before: the landing on `integration` (1159498), the state before the deck pass of the evening and the night's polish, on a production build of that tree. |
| sources-allsides-before-1440.png, sources-allsides-after-1440.png | The sources section in the AllSides mode, where marks sit at −1 and +1. Before is the evening's state (f7521d0, the instrument just added to the landing): the marks poke out of the column and a badge covers an audience tick. After: the field is inset so every mark stays inside; the ticks and the cohort table are left to the signed-in Sources page. |

Captures were taken with Playwright and Chrome on the production bundles, the page scrolled once so the arrival
motion had played, the running lines wherever they stood at that moment.
