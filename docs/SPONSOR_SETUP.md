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

The subsequent [memory diagnosis](../reports/memory-readiness.md) supersedes the earlier 9 GiB allocation suggestion. Installed RAM is 16 GiB (15.80 GiB usable); no `.wslconfig` exists. The current cap is not the primary blocker: Linux has no current PSI/OOM pressure and the official 6 GiB minimum passes. After explicit approval, a normal Chrome window-close request increased Windows available RAM from 0.910 to 4.592 GiB and reduced commit from 94% to 75%. Guest available RAM was 4.562 GiB, still below the separate 5 GiB local startup gate. Keep approximately the present 8 GiB cap, 8 CPUs and 2 GiB swap; increasing the cap or restarting WSL would not create RAM. A review-only proposed file is documented, not installed. No registry pull was made.

The official `preflight.sh` ran: Docker/Compose/architecture/CPU/disk PASS; memory WARN; Azure registry login FAIL. A bounded noninteractive login attempt confirmed that private interactive credentials are unavailable. No image pull/start was attempted past the failed prerequisite. The supplied `verify.sh` also ran read-only and could not pass because the platform is not deployed. Its credential-bearing raw output was withheld.

## Verification prepared for the actual bundle

The current wrappers validate the official Compose and run the bundled scripts. Diagnostics distinguish long-running services, successful one-shot jobs, `/api/config`, the API's documented healthcheck at HTTP `/`, and actual SQL results.

The authenticated SQL Editor proxy route and payload come from the **bundled verify.sh**: `/api/auth/login`, token plus actual `orgId`, then `/api/proxy/query/sql/start` with `select` and `pageLimit`. The extra smoke requires `SELECT 1 AS one` to return `one=1`. The bundled sample query uses `NY_TAXI.customers`; sample bootstrap registers NY_TAXI and TPCDS_DB from the vendor's public S3 bucket. A query receipt/open port is not a dataset PASS.

The bundle includes the matching official JDBC JAR and driver class, so no driver download or guessed class is needed. The existing Java helper is preserved; current integration diagnostics follow the bundle's UI proxy verification route instead.

## Codex workflow and Meterless → Nemotron

The team uses Codex. Routine checks exclude Cursor installation and Composer/Grok acceptance; optional historical diagnostics preserve existing installations/settings. The claimed organizer change is human-reported, not independently verified; see [current rules evidence](RULES_CHECK.md). Required Zetaris/Meterless integration and the chosen Nemotron route are unchanged.

Hosted inference reads `MODEL_BASE_URL`, `MODEL_API_KEY` and `NEMOTRON_MODEL` from one route: the local Nightshift Console, or a direct NVIDIA route with that route's own three values. `METERLESS_BASE_URL`, `METERLESS_RUNTIME_TOKEN` and `METERLESS_MODEL` are accepted when the `MODEL_*` entries are empty. Keep Meterless keys out of Cursor settings. Routine diagnostics never send inference; `--inference` explicitly allows one capped request after real values are supplied. Existing H-MEM and persistence passes are reference-component results, not inference readiness.
