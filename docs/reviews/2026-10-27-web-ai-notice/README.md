# AI headline notice, 27 October 2026: review screenshots

Captures of branch `anastasia/web-ux-ai-notice` for the PR into `integration`. Home (`/dashboard`) and a story page, at
1440 × 900 ("desktop") and 375 × 812 ("phone"), on production builds: "before" is integration 1a1e141, "after" the
branch head (closable notices, 2026-10-27). The pages show the FICTIONAL 22 October preview sample (russia-ukraine-war, the DEMO label on the page),
served to the browser through Playwright routes with a DEMO reader: no account, no real edition, no credential.
Decision: `docs/DECISIONS.md` › User account and interface, item 12; `web/DESIGN.md` › Components and › Color.

| File | What it shows |
| --- | --- |
| home-before-desktop.png, home-before-phone.png | Home before: the DEMO label first, then the edition head. |
| home-after-desktop.png, home-after-phone.png | Home after: the yellow AI headline notice first in the main column, under the site header, then the DEMO label; both with rounded corners, no left edge and a white × on an ink circle to close them for the visit. |
| story-before-desktop.png, story-before-phone.png | A story page before: the crumb, the DEMO label, the story's head. |
| story-after-desktop.png, story-after-phone.png | The same story page after: the notice above the crumb, the DEMO label under it, both closable. |
| home-closed-desktop.png | Home with both notices closed: the edition head moves up; a new visit shows both again. |
