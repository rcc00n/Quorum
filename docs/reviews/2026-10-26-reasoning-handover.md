# Reasoning hand-over, night of 26 → 27 October 2026

Owner: Yelysei (reasoning). Written by Yelysei / Claude Code at about 22:45Z on 26 Oct, because the session's tokens were running low.

Whoever picks this up, human or assistant: read this file, then `AGENTS.md`, [Issue #2](https://github.com/rcc00n/Quorum/issues/2) from comment 6425000264 on, and `docs/DECISIONS.md`. Every branch below is pushed. Check its current head with `git fetch origin` before you act, because work may have landed after this note.

Deadline: **27 Oct 23:45 UTC, which is 19:45 New York** (the team's local time, UTC−4).

## 1. Decisions Yelysei made on 26 Oct that are not all recorded yet

Record each one per `AGENTS.md` § 2 in the same commit as its code, with the author "Yelysei / Claude Code (decided by Yelysei 2026-10-26)".

| # | Decision | Where it is implemented | State at 22:45Z |
| --- | --- | --- | --- |
| D1 | The 27-Oct canonical editions run on the **Meterless Nightshift** route with the H-MEM guard, not on NVIDIA direct. NVIDIA direct is only a manual per-topic fallback, by Yelysei's word, and one edition never mixes routes. | `yelysei/tuesday-runs`: `run_editions.py --route meterless`; DECISIONS D1 | IN_PROGRESS (implementer done, review pending) |
| D2 | Published editions go public **after** they are installed on the site: the snapshot with its public trace goes to `docs/examples/editions/<date>/<topic>.json`, plus `<topic>.run-summary.json` with counts only. Ledgers, journals and logs stay private. | `yelysei/tuesday-runs`: `scripts/export_public_edition.py`; DECISIONS D2 | IN_PROGRESS |
| D3 | **H-MEM source memory is on** for the 27-Oct runs. | Not written yet. It needs: a way for the runner to turn hmem on (the committed config stays `off`); the canonical store directory created **before** the first run (outside the repo), so that every round-2 recall reaches the engine (when the directory is missing, the sidecar answers recalls without opening the engine, `reasoning/memory/sidecar.mjs`); and topics run one after another, because they share one store lock. | NOT_STARTED |
| D4 | **Impact bar 6 → 4 of 9.** `confirmation_min` stays 1, the cap stays 10. It applies to all editions and closes "calibrate on the first real days" in › Still to clarify. Why: on 26 Oct, 1 of 50 events crossed 6, and war events with 5 confirmed claims scored 3–4. | Workflow, on `yelysei/demo-ready` after the engine merge: `reasoning/config/reasoning.toml` threshold, the `rules/impact_bar.py` default, DECISIONS › Selecting major news, tests | NOT_STARTED (queued behind the engine merge) |
| D5 | "Across the spectrum" is **one quote-backed paragraph per side** (flanks, and outlets where they differ). The direction comes first and is neutral, then good or bad, cause, why, what next. Every sentence has a code-verified verbatim quote, otherwise it is dropped. This supersedes the five-item list in Issue #2 6425000264. | `yelysei/spectrum-readings`: new optional key `spectrum.readings`, behind `[frame] readings`, committed **off** until the portal accepts the key | review round 3 |
| D6 | **Anastasia takes Vadim's items this week**: integration merges, the portal parser, the reasoning reader and install, deploy. Vadim's recorded decisions stay valid. | Issue #2 6426106426 | posted |

## 2. Branches

| Branch | Head at 22:45Z | What it is | Next step |
| --- | --- | --- | --- |
| `yelysei/agents` (= PR #29 → `integration`) | d57bd6f | H-MEM guard, seed filter, intake, sidecar, runner | CI is red at d57bd6f; see `yelysei/ci-proc-cmdline`. The `portal` job was cancelled at the 12-minute timeout while apt fetched Playwright fonts, which is infrastructure; a re-run should pass. |
| `yelysei/demo-ready` (local only; equals `yelysei/agents`) | d57bd6f | Where everything is merged before it is pushed to `yelysei/agents` | Merge the branches below, run the full suite, then `git push origin yelysei/demo-ready:yelysei/agents` (fast-forward only, never force). |
| `yelysei/ci-proc-cmdline` | 4d92ed5 | One-line test fix: on Linux, `/proc/<pid>/cmdline` uses NUL separators | Ready. Merge into demo-ready. Proved under WSL: the old scan finds nothing, the new one finds the process. |
| `yelysei/meterless-engine` | 593036a or later | H-MEM source memory (Vadim's patches 0002/0004/0012, adopted). Conformance 13/13 against the sidecar; engine-backed tests green; one live write-path check. Hand-over log: `docs/reviews/2026-10-26-meterless-engine-build.md` | Review loop in progress: an env allowlist for the sidecar (no secrets passed to Node), consistent Build-rule wording, EXIT= captured in the scorecards. When clean, merge into demo-ready, keeping every row of both sides in `docs/DECISIONS.md` and `reasoning/README.md`. |
| `yelysei/tuesday-runs` | a7690bd or later | D1, D2 and the runbook `docs/reviews/2026-10-27-demo-runbook.md` | Review it, then merge into demo-ready. Add D3 on top. |
| `yelysei/spectrum-readings` | dbd4d5e or later | D5 | When review is clean, merge into demo-ready. The field names and the exact portal parser change go into ARCHITECTURE § 8; post them to Anastasia. The flag stays off unless her reader (PR #31) accepts the key. |

**Build-rule wording.** Keep it until Yelysei says otherwise:
- **TESTED**: conformance 13/13 against the sidecar; engine-backed tests with the real reference engine;
- **INTEGRATED** live on the write path only;
- the first live recall through the engine is expected from the 27-Oct runs with H-MEM on;
- still open: Anastasia's DocRef review (`RELEASE_CHECKLIST` › H-MEM) and the challenge-page check.

Do not write "Build rule met" before those.

## 3. Still to do tonight (UTC)

1. **Merge into `yelysei/demo-ready`, in this order:**
   1. the engine;
   2. D4 (the bar);
   3. `ci-proc-cmdline`;
   4. `tuesday-runs`;
   5. D3 (H-MEM on);
   6. `spectrum-readings` if it is clean.

   Then run the full suite twice: once with `METERLESS_HOME` unset, once with it set. Run `scripts/security-check.py`. Push to `yelysei/agents` and watch PR #29 CI.
2. **Issue #2:**
   - REASON-ENGINE-01 status, using the wording above;
   - the `spectrum.readings` fields and the parser change for Anastasia;
   - "PR #29 ready to merge" for Anastasia, who merges into `integration`.
3. **Reviews of Anastasia's PR #30** (README submission) and **PR #31** (login-only reader, `manage.py reasoning_snapshot … --install`). Scope: the reasoning facts and the contract. A review was started and its results may already sit in the session; otherwise redo it.

## 4. Tuesday 27 Oct (UTC / New York)

- **10:30Z / 06:30.** Anastasia's post-cut dump lands in her private dump repository.
- **Restore and register.** Restore the dump into the collection database. Then, in Zetaris, run `REGISTER DATASOURCE TABLES ('topics') FROM QUORUM_COLLECT`.
- **About 10:45–13:30Z.** Run the four topics one after another with `--route meterless`, with H-MEM on and the bar at 4, in this order:
  1. `immigration-southern-border`;
  2. `russia-ukraine-war`;
  3. `tariffs-trade-war-china`;
  4. `ai-regulation-export-controls`.

  **Stop rule (Yelysei's):** stop at the first error. That means 403 or any 4xx/5xx, `route_substituted`, `lane_unverified`, injected H-MEM memories, a Traceback, or a non-zero exit. Find the cause before you go on.
- **After each topic.** Write the sidecar with `corpus_as_of`. Hand the files to Yelysei to **email to Anastasia**: snapshot, sidecar, both `.sha256` files, and the producer commit.
- **Deadline for the files.** All files reach her **by 14:00Z, and by 14:30Z at the latest**. She installs them with `manage.py reasoning_snapshot --file … --sha256 … --sidecar … --sidecar-sha256 … --producer-commit … --install` (PR #31).
- **After she confirms an install.** Export with `export_public_edition.py` into `docs/examples/editions/2026-10-27/`. Then fill the README samples (PR #30).
- **About 16:00–22:00Z.** Video with audio, showing Meterless working; slides; the HackOS form. Submit with margin before 23:45Z.

## 5. Open asks for Yelysei

- Email Anastasia the 26-Oct immigration edition for her rehearsal: hashes and producer commit are in Issue #2 6428555157.
- Ask Vadim to add Anastasia's public key on the portal VPS. Without it there is no deploy, and only the fallback video remains.
- Open the HackOS submission form and post its exact fields: video, slides format, sponsor text.
- Check on the challenge page that the H-MEM scope counts for the Build rule.

## 6. Rules that still apply

- Everything in `AGENTS.md`.
- No secrets in output.
- Private files never go into the repository or Issue #2; post only hashes and counts. The one exception is D2, and only after an edition is installed.
- Live paid runs only with Yelysei's word. The 27-Oct runs above are agreed.
- Never force-push.
- Reasoning never merges into `integration` or `master`; Anastasia does.
- Vendor checkouts and the H-MEM store stay outside the repository.
