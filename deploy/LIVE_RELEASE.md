# Live release handoff — 26 October 2026 (client date)

Owner: rcc00n / Codex. Tracking: GitHub Issue #2. This is an execution report,
not a second rulebook. UTC evidence begins 2026-10-27 00:50.

| ID | State | Evidence / next action |
| --- | --- | --- |
| INFRA-SSH-01 | BLOCKED | Existing owner key authenticates as root with strict host-key checking. Teammate full public key missing; fingerprint alone cannot be installed. Expected SHA256:1YQtaPzfPuVR9sbmIjAQzbCxhGk5op14+/mO2eFbLmM. Preserve existing authorized_keys and verify the complete key before adding access. |
| INFRA-HOST-01 | IN_PROGRESS | Existing x86_64 VPS has 3905 MiB RAM, approximately 380 MiB available, 40 GiB disk free. Quorum services active on loopback 3017/8017. Numerous unrelated workloads must remain untouched. No new server purchased. |
| RELEASE-ASSEMBLY-01 | IN_PROGRESS | Recheck #29 at 13834b0, then collection #28, web #23–#27, README #30 and reader #31. Preserve reasoning → collection → web order. Owner reviews and final combined checks required. |
| RELEASE-READER-01 | IN_PROGRESS | #31 d516ff5 adds accepted immutable editions; #27 13a02b0 renders provisional metadata and editorial-review labels. Both have successful PR CI. Actual installed-edition browser verification still required. |
| RELEASE-PROD-01 | NOT_STARTED | Current production remains 09f5325c78fe71677c46a83f952c04b602e6fc7b. Use guarded upgrade, private backups, rollback rehearsal and authenticated browser checks. |
| EDITION-REAL-01 | BLOCKED | Need original accepted 26-Oct immigration snapshot + sidecar matching owner-announced hashes, or accepted 27-Oct handoff. Never publish historical v4 as accepted. |

## Existing execution locations

- VPS: Nginx/TLS, Next.js, Django, private SQLite auth/preferences. No processing.
- Anastasia's machine: PostgreSQL and collection workers, periodic collection and dump export;
  Zetaris registered datasource and genuine query evidence reported by the collection owner.
- Yelysei's Windows machine: restored corpus through the official Zetaris bundle,
  reasoning, local Nightshift runtime, remote NVIDIA inference, external H-MEM store.
  Owner-confirmed 27-Oct runs start at 10:30Z; files to Anastasia by 14:00Z.
- Immutable accepted editions are transferred to the portal; model calls are not
  started by HTTP requests. The public VPS requires no corpus database or model runtime.

## Inputs and ownership

The complete public SSH key is pending. The fingerprint was supplied again and is
insufficient. Never request the private key. Actual teammate authentication requires
a connection from the holder of that private key; local configuration checks alone
cannot prove it.

Deployment and infrastructure execution are explicitly authorized by Vadim in this
session. New paid provisioning is not authorized. Team owner approvals are retained
as their own GitHub reviews, never inferred from this authorization.
