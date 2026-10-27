# Demo editions of Tuesday 27 October 2026: runbook

Operator: Yelysei. Written 2026-10-26 by Claude Code for Yelysei; nothing here was run yet.
Times are UTC, with the local time (UTC−4, New York daylight time) in brackets.

The rules behind each step are in [docs/DECISIONS.md](../DECISIONS.md) and are not repeated here:
› Demo for the judges (the four demo topics and their order; Canonical editions of 27 October: the Meterless
Nightshift route, the stop rule, NVIDIA direct only as a manual fallback; Public edition samples) and › Daily editions
for users (the edition cut, the status files). Where this page and DECISIONS.md differ, DECISIONS.md wins.
Tool details: [reasoning/README.md](../../reasoning/README.md) › Daily editions (operator) and › Decisions.

Settings for the canonical runs:

- route: `--route meterless` for every topic (no `--keys`).
- hmem: on (set by the follow-up commit after the engine merge)
- topics, in this order: `immigration-southern-border`, `russia-ukraine-war`, `tariffs-trade-war-china`,
  `ai-regulation-export-controls`.

## Times

| What | UTC | Local (UTC−4) |
| --- | --- | --- |
| Edition cut for 2026-10-27 (05:30 New York); `--live` refuses to start before it | 09:30 | 05:30 |
| Post-cut dump restored; the runs start after it | 10:30 | 06:30 |
| Topics registered, corpus checked (plan run, no model call) | 10:45 | 06:45 |
| Four runs on the Meterless route | 10:50–13:00 | 06:50–09:00 |
| Sidecars written, hand-over email to Anastasia | 13:15 | 09:15 |
| Editions installed (Anastasia confirms) | by 15:00 | by 11:00 |
| Public samples exported and committed | 15:30 | 11:30 |
| README samples | 16:30 | 12:30 |
| Submission sent (target, with a buffer) | 21:00 | 17:00 |
| Submissions close | 23:45 | 19:45 |

Run time, for planning only: the two climate-policy runs of 26 October on this route made 188 calls in about
6.5 minutes (about 30 a minute); the 26 October immigration edition made 1 435 calls, about 50 minutes at that rate.

## 0. Before the day

- The checkout that runs the editions is at a pushed commit (the producer commit the portal resolves). Note its full
  40-hex commit (`git rev-parse HEAD`); it goes into every sidecar.
- `.env` holds the Meterless token as `METERLESS_TOKEN`, both Nemotron lanes pinned with exact ids (reasoning/README.md
  › Run it, "Switching to the Meterless route"); the NVIDIA values may stay, since the runner blanks them for every
  Meterless run, and are what the manual fallback uses. Never print any of them.
- The Nightshift runtime is running on this machine (loopback port 8088), started from Windows, not WSL.
- Windows venv in `reasoning/`: `.venv\Scripts\activate`; every command below runs from `reasoning/`.

## 1. Restore the post-cut dump (10:30 UTC, 06:30 local)

Restore Anastasia's post-cut dump of collection (taken after the 09:30 UTC cut) into the local collection Postgres
that Zetaris reads as `QUORUM_COLLECT`, the same way as for the 26 October editions. The dump stays private and
outside the repository. Write down the dump's time as `YYYY-MM-DDTHH:MMZ`: it is `corpus_as_of` in step 5.

## 2. Register the topics table again

Run this one statement through Zetaris (the SQL editor, or `agent/tools_zetaris.run_sql` as
`collectors/zetaris/register.py` does):

```sql
REGISTER DATASOURCE TABLES ('topics') FROM QUORUM_COLLECT
```

Then check that collection's topics table answers through Zetaris and lists the four demo topics:

```bash
python -X utf8 scripts/dry_check.py --list-topics --env-file ../.env
```

(the runner's own topic check, read-only; it prints the topic ids and no credential).

## 3. Check the corpus (plan run: no model call, no status file)

```bash
python -X utf8 scripts/run_editions.py --date 2026-10-27 --topics immigration-southern-border,russia-ukraine-war,tariffs-trade-war-china,ai-regulation-export-controls --route meterless --out snapshots/_private --log-dir snapshots/_runs/logs --status-dir snapshots/_runs/status --dry-check-out snapshots/_runs/dry
```

Go on only when:

- it exits 0 and its first line says `route meterless (the Meterless stop rule on)`;
- no topic says `meterless token missing` or `not a row in collection's topics table`;
- every topic's dry check finished, and the `plan` row in its dry log (`snapshots/_runs/logs/2026-10-27_<topic>_dry.log`)
  counts documents in the window. A topic with no documents: ask Anastasia before step 4.

## 4. The four runs (from about 10:50 UTC, 06:50 local)

The same command with `--live`:

```bash
python -X utf8 scripts/run_editions.py --date 2026-10-27 --topics immigration-southern-border,russia-ukraine-war,tariffs-trade-war-china,ai-regulation-export-controls --route meterless --out snapshots/_private --log-dir snapshots/_runs/logs --status-dir snapshots/_runs/status --dry-check-out snapshots/_runs/dry --live
```

It runs the topics one after the other and exits 0 when all four are published. Per run, the log is
`snapshots/_runs/logs/2026-10-27_<topic>_a1_run<NN>_route.log`; its first line names the route.

The stop rule (DECISIONS.md › Canonical editions of 27 October): at a run's first error the runner kills that run,
marks its topic `failed`, starts none of the later topics (they stay `queued`), prints a `manual fallback for <topic>`
command and a line starting `once the cause is fixed`, and exits 1. Then:

1. Read the end of that run's log (`--- Meterless stop rule: …`) and the runner log
   (`snapshots/_runs/logs/2026-10-27_runner.log`). Report the cause in counts and codes only.
2. If the cause is fixed on the Meterless side (for example, Nightshift restarted), do what the `once the cause is
   fixed` line says for the stopped topic (rules: reasoning/README.md › Decisions, the runner's `--route` row, item 4):
   - `<topic> resumes from its checkpoint`: run the step 4 command again. The published topics are skipped, the
     stopped topic resumes, the queued ones follow.
   - `<topic> stays failed … run it again alone as a fresh --attempt <M>` (`<M>` is 2 after attempt 1): its journal
     keeps a call the rule failed (for example the connection refused while Nightshift was down, or a 401), or its run
     published before it was stopped, or published a partial. A resume would restore that call into the edition, so
     the runner refuses it. Run the step 4 command with `--topics <topic> --attempt <M>`, then the step 4 command again
     with `--topics` listing only the topics still `queued`, in their order.
3. Otherwise only Yelysei decides on the NVIDIA direct fallback for that one topic: the printed command, as printed
   (a fresh `--attempt`, so the edition never mixes routes; it needs `MODEL_BASE_URL` on the NVIDIA endpoint and the
   listed keys in `.env`). The runner never starts it.
4. After a fallback, rerun the Meterless command with `--topics` listing only the topics not yet published, so the
   fallen-back topic is never continued on the other route.

A version the stop rule failed is never handed over. It can still be the store's `latest.json` until a newer version is
published. The status file does not show it as published (the runner log says `which the Meterless stop rule failed`).

Never pass `--allow-before-cut`, and never `--resume` a run by hand on the other route.

## 5. Sidecars

For each published topic, `N` is the version the runner reported for the run that published it: `<topic>: published
version N` in the runner log, `version` in `snapshots/_runs/status/_runner/2026-10-27/_summary.json`. It is normally 1,
and higher when a version the rule failed was published before it. Always name `v<N>.json`, never `latest.json`, because after a stop `latest.json` can be a
version the rule failed.

```bash
python -X utf8 scripts/edition_sidecar.py --snapshot snapshots/_private/<topic>/2026-10-27/v<N>.json --corpus-as-of <dump time from step 1> --producer-commit <full 40-hex commit from step 0>
```

It writes `v<N>.json.sidecar.json`, its `.sha256` and `v<N>.json.sha256` beside the snapshot, and refuses a snapshot or
a corpus time the portal would reject.

## 6. Hand-over to Anastasia, by email

Per topic: `v<N>.json`, `v<N>.json.sha256`, `v<N>.json.sidecar.json`, `v<N>.json.sidecar.json.sha256`, and the producer
commit. Nothing else: never a ledger (`*.ledger.json`), journal, checkpoint, log or `.env`. In Issue #2, only hashes
and counts.

## 7. Public samples, once Anastasia confirms the editions are installed

For each installed topic:

```bash
python -X utf8 scripts/export_public_edition.py snapshots/_private/<topic>/2026-10-27/v<N>.json --sha256 snapshots/_private/<topic>/2026-10-27/v<N>.json.sha256 --ledger snapshots/_private/<topic>/2026-10-27/v<N>.ledger.json --out ../docs/examples/editions
```

It writes `docs/examples/editions/2026-10-27/<topic>.json` (the snapshot, byte for byte) and
`<topic>.run-summary.json` (counts only). Check each summary: `provider_route` `meterless`, `calls.failed` 0,
`route_substituted` 0, `lane_unverified` 0, `hmem_injected` 0. A resumed edition shows the same values: the runner
resumes a stopped topic only when its journal keeps no call the rule fails (step 4.2). A summary that shows anything
else is not an edition the stop rule let through. Do not commit it, and tell Yelysei; he decides what happens to the
installed edition. A refusal names what to fix and writes nothing.
Before committing, `git status` must show only files under `docs/examples/editions/2026-10-27/`.

## 8. README samples, then the submission

- Point the repository README at `docs/examples/editions/2026-10-27/`: the four editions with their run summaries
  (route, call counts, Meterless receipts, H-MEM), next to the fictional samples in `docs/examples/`.
- Submit in HackOS by 21:00 UTC (17:00 local), well before 23:45 UTC (19:45 local): the demo video, the slides, the
  repository with its README, and how the sponsor technologies were used.
