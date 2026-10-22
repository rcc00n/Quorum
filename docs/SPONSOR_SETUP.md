# Sponsor setup: downloaded official Zetaris platform

The **new supported platform bundle** from [Zetaris Cloud Gateway](https://cloud.enterprise.zetaris.com/dashboard/download) supersedes the earlier Freemium preparation. Follow the bundled README/preflight/verify and [official getting-started guide](https://github.com/zetaris/getting-started). The old external Freemium checkout and preparation were preserved but are not started or used by the current scripts.

## Actual installed files and configuration

Archive found read-only at `C:\Users\Vadim\Downloads\zetaris-platform.zip`; size 27,996,894 bytes; SHA256 `14c6a811a140378bec1749ceffd7fa123bafb2f178545b26354e8f9433b413d3`. It was safely extracted outside Git to `~/.local/share/quorum/zetaris-platform-bundle/zetaris-platform`. The archive had 19 entries, approximately 31.2 MB expanded. Archive paths/symlinks were checked before extraction.

The supplied `.env` already contains administrator email/password/organization and all image/database settings. These values were retained, never invented or printed. Configuration is mode 600 and the private installation directory is mode 700. Change the supplied administrator password privately at first successful login. No registry credentials were in the bundle or existing Docker configuration.

Actual default services: `postgres`, `init`, `driver`, `api`, `ui`, `bootstrap`. `init` and `bootstrap` must complete with exit 0; the other four must run with acceptable health. There is no optional GPU, Ollama or local-model service in this selection. No required default service is removed.

Only a private Compose override was added, binding the UI to loopback. Supplied `.env` settings/images are unchanged. Scripts explicitly select the supplied Compose plus this override with project `zetaris`; this also applies when running official scripts through the wrappers.

Configured endpoints (not live until startup): GUI `http://localhost:3000`; REST `http://localhost:8888/api/v1.0`; API internal host port 8889 and JDBC 10000 are loopback-only. Spark UI uses localhost:4040. PostgreSQL and the driver's additional 8080 mapping use auto-assigned loopback host ports (`published: 0`), so occupied host port 5432 is untouched. Static required ports 3000/8888/8889/10000/4040 were free during the audit.

## Resource and authentication results

Existing native Linux Docker 29.0.2 / Compose 2.40.3 works on WSL2. Docker sees 8 CPUs and **7.66 GiB** total RAM, approximately an 8 GiB WSL allocation after overhead. The bundle's actual preflight **requires 6 GiB**, recommends 8 GiB and 4 CPUs, and accepted this allocation with a warning. It found over 850 GiB free disk after cleanup.

Approximately 4.57 GiB was available to WSL before installation, while Windows had only ~567 MiB free physical memory. Default heaps are driver `2g`, API `1g`, Spark `local[2]` with 2 cores; no server-size overrides were used. Local startup safety gates require 5 GiB WSL-available RAM and 4 GiB free Windows physical memory. These are workload-protection gates, not claims about vendor hard requirements. No WSL/Docker memory setting, application or existing container was changed.

No `.wslconfig` resource entries were reported in the read-only check. With approximately 15.8 GiB physical host RAM, raising a configured 8 GiB WSL cap to **9 GiB** would be the smallest whole-GiB change expected to report more than 8 GiB after overhead, leaving roughly 6.8 GiB theoretical host capacity. It is **not safe to apply while the host is this memory-constrained**, and is not required merely to pass the vendor's 6 GiB minimum. Free host headroom manually first; any `.wslconfig` edit or WSL shutdown requires separate authorization. Disk cleanup does not increase RAM.

The official `preflight.sh` ran: Docker/Compose/architecture/CPU/disk PASS; memory WARN; Azure registry login FAIL. A bounded noninteractive login attempt confirmed that private interactive credentials are unavailable. No image pull/start was attempted past the failed prerequisite. The supplied `verify.sh` also ran read-only and could not pass because the platform is not deployed. Its credential-bearing raw output was withheld.

## Verification prepared for the actual bundle

The current wrappers validate the official Compose and run the bundled scripts. Diagnostics distinguish long-running services, successful one-shot jobs, `/api/config`, the API's documented healthcheck at HTTP `/`, and actual SQL results.

The authenticated SQL Editor proxy route and payload come from the **bundled verify.sh**: `/api/auth/login`, token plus actual `orgId`, then `/api/proxy/query/sql/start` with `select` and `pageLimit`. The extra smoke requires `SELECT 1 AS one` to return `one=1`. The bundled sample query uses `NY_TAXI.customers`; sample bootstrap registers NY_TAXI and TPCDS_DB from the vendor's public S3 bucket. A query receipt/open port is not a dataset PASS.

The bundle includes the matching official JDBC JAR and driver class, so no driver download or guessed class is needed. The existing Java helper is preserved; current integration diagnostics follow the bundle's UI proxy verification route instead.

## Cursor and Meterless → Nemotron

Preserve the installed/authenticated Cursor. No reinstall, logout, credits purchase or model-settings changes were made. Composer/Grok Agent acceptance still needs actual user observation; the read-only smoke remains in MANUAL_ACTIONS.md.

Hosted inference still requires the exact organizer-provided `METERLESS_BASE_URL`, `METERLESS_API_KEY`, `NEMOTRON_MODEL`. No defaults or direct NVIDIA fallback are invented. Keep Meterless keys out of Cursor settings. Routine diagnostics never send inference; `--inference` explicitly allows one capped sponsored request after real values are supplied. Existing H-MEM and persistence passes are reference-component results, not inference readiness.
