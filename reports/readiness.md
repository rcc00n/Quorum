# Environment readiness — 2026-10-21, organizer correction

Repository: https://github.com/rcc00n/Quorum, branch `master`.
Authority: user-provided corrections from Academy's “Start Here: Set Up Your Data, Build and Power Layers”; [public syllabus](https://academy.genai.works/courses/open-agent-hackathon-2026/details). The full enrolled lesson text is not publicly accessible here. No project or track selected; no application/agent created.

| Component | Status | Actual evidence / remaining boundary |
|---|---|---|
| WSL2 / native Docker | PASS — VERIFIED | Ubuntu-20.04 WSL2, working existing Linux Docker 29.0.2 Unix socket and Compose 2.40.3. No backend/WSL changes. |
| Docker Desktop integration | NOT_TESTED | Existing working Linux Engine is used; Desktop integration is not inferred. |
| Zetaris Freemium source | PASS — PREPARED | Official checkout outside Quorum, revision `9dd4fe943afebca6b204b6ed5eccdca91b831e6c`. Actual README/Compose inspected. |
| Freemium isolated configuration | PASS — CONFIGURED / syntax VERIFIED | External private Compose validates. Exactly zetaris-db/server/api/gui, isolated project/network/data, DB unpublished, localhost 9001/8888/10000 only. No optional model/GPU services. |
| Docker memory prerequisite | BLOCKED | 7.66 GiB allocation, roughly 4.61 GiB currently available. Start requires 8 GiB allocated AND available, a conservative interpretation of organizer's 8 GB. No limits silently changed. |
| Docker Hub authentication | BLOCKED | One noninteractive `docker login` attempt required manual authentication. No credentials supplied or printed. |
| Freemium image access | BLOCKED | One pull of `zetaris/lightning-server:v2.4.1.0-latest` denied. No repeated pull, alternate obsolete tag, optional image pull or Cloud-bundle substitution. |
| Four core containers | BLOCKED | None started; memory and image-access prerequisites unmet. Existing unrelated containers untouched. |
| GUI / REST availability | BLOCKED | No running deployment. Script checks HTTP HTML/JSON application responses separately from SQL. Exact REST probe endpoint still needs lesson/operator confirmation. |
| Registered dataset query | BLOCKED | Need lesson's actual source registration recipe/sample SELECT, matching external JDBC JAR, initialized account and running engine. Java smoke compiled successfully but no real SQL request was possible. |
| Cursor installation | PASS — INSTALLED | Current Windows executable 3.26.16; installation/login preserved. No reinstall, model-settings change or credit purchase. Authentication is user-reported. |
| Cursor Composer/Grok Agent acceptance | NOT_TESTED | Preparatory read-only smoke and external user-evidence format documented. Exact lesson prompt/model selections and interactive success not observed. |
| Meterless H-MEM/state references | PASS — VERIFIED components | Existing pinned external installation preserved; 10 official smoke tests and real JSON memory/ledger/World Model persistence checks pass. These do not prove inference readiness. |
| Nemotron through Meterless | BLOCKED | Organizer-issued METERLESS_BASE_URL, METERLESS_API_KEY, NEMOTRON_MODEL absent. No endpoint/model invented; previous direct NVIDIA route removed. No provider credits spent. |
| GitHub / public-file safety | PASS — VERIFIED before publication | Correct origin/master and authentication. Staged paths, content, sizes and heuristic secret scan reviewed before commit/push. Remote SHA checked after successful push. |

Final `verify-all.sh`: **19 PASS, 0 FAIL, 10 BLOCKED, 2 NOT_TESTED**, exit **2**. Reference tests are actual official/local persistence checks. No mock inference, open-port success or SELECT 1 is counted as dataset/inference integration.

Additional validation: Python compilation, shell syntax, Java smoke compilation, private Compose validation, idempotent preparation, and memory-blocked startup path. Image-level startup, runtime ownership/private-key compatibility, account helper, HTTP probes, registered-data SQL and configured provider inference remain untested because prerequisites are missing.

Security: generated DB password, RSA DER private keys, vendor repository, private deployment, datasets and runtime files stay outside Quorum. Private files/directories use restricted permissions; DB statement logging and upstream world-writable data chmod are removed in the isolated preparation. Public example credentials/test encryption keys are not used for this deployment. No secrets or binaries are staged.

Workspace has approximately 846 GiB free. Existing host port 5432 remains untouched; Freemium PostgreSQL is internal-only. No containers or WSL memory settings were changed.

Manual actions: [MANUAL_ACTIONS.md](../docs/MANUAL_ACTIONS.md). Normal diagnostics: `cd ~/Quorum && ./scripts/verify-all.sh` (no inference credits). Explicit sponsored inference only after real access is supplied: `./scripts/verify-all.sh --inference`.

Environment preparation does not establish hackathon submission compliance.
