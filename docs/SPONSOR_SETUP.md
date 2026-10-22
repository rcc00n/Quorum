# Sponsor configuration

## Zetaris

Official sources: [getting-started](https://github.com/zetaris/getting-started), [local installation guide](https://github.com/zetaris/getting-started/blob/main/docs/install/updated_zetaris_installation_guide.md), [connection helpers](https://github.com/zetaris/getting-started/blob/main/scripts/zetaris_api.py).

Prefer an organizer-provided instance and account. Supply its UI origin as `ZETARIS_BASE_URL`, numeric `ZETARIS_ORG_ID`, and either `ZETARIS_API_KEY` or username/password. An engine ID is optional. No credentials or instance were available in this session.

The verifier follows the official UI proxy helper: `/api/auth/login`, authenticated database listing, and `/api/proxy/sql-editor/sqls/run-query` with `SELECT 1 AS one`. It only passes SQL after recognizing an actual row containing 1. Unrecognized or asynchronous result shapes need private inspection in SQL Editor. Data source discovery uses the official `SHOW DATASOURCES` command and requires a structured rows response; database listing alone is insufficient. Set `ZETARIS_HEALTH_URL` only to a supported health endpoint supplied by the operator. HTTPS is required except loopback; redirects are rejected to avoid forwarding credentials.

For local installation, sign in at [Zetaris Cloud](https://cloud.enterprise.zetaris.com/dashboard/download). Obtain `zetaris-platform.zip`, matching private `.env`, registry credentials and evaluation/licence entitlement. Extract outside Quorum. Use current bundle instructions and its preflight/verification scripts. Keep supplied image versions together. No images were pulled and no cloud resources created.

The official guide recommends 8 GiB for Docker and rejects below 6 GiB; allow at least 15 GB disk. Current total Docker memory is approximately 7.7 GiB and other services already run, so check available headroom before starting. Ports such as 5432 are occupied. Review the bundle's mappings without altering existing services.

## Cursor

Official sources: [Windows download](https://cursor.com/downloads), [quickstart](https://cursor.com/docs/get-started/quickstart).

The previously initiated official Windows user installation produced Cursor 3.24.18. No second download or installation is needed. Its CLI is under `%LOCALAPPDATA%\Programs\cursor\resources\app\bin\cursor.cmd`; the executable is `%LOCALAPPDATA%\Programs\cursor\Cursor.exe`.

Cursor CLI version was verified and a Windows process launch succeeded after removing inherited `ELECTRON_RUN_AS_NODE=1` and `VSCODE_IPC_HOOK_CLI` from the child process environment only. These Codex host variables must not be inherited by a GUI launch. A process launch is distinct from a successful WSL connection. Finish first-run/login screens if presented, then open `~/Quorum` through WSL2. See the manual acceptance steps. No subscription was purchased.

## Meterless

Official sources: [reference README](https://github.com/Meterless/Meterless/tree/main/engines/hmem/reference), [World Model reference](https://github.com/Meterless/Meterless/tree/main/engines/world-model/reference), [runtime provider contract](https://github.com/Meterless/Meterless/blob/main/docs/agent-ready/add-meterless-provider.md).

The lightweight references use Node.js and local JSON persistence; they run on the current WSL2 machine without GPU dependencies. They are reference components, not a production SDK or an installed Nightshift inference service.

Optional runtime discovery needs `METERLESS_BASE_URL` ending in `/v1` and the real `METERLESS_RUNTIME_TOKEN` from the authorized runtime's `<stateDir>/proxy-token`. Authenticated `/v1/models` returns `meterless/*` routing modes. `/healthz` alone does not establish authenticated readiness. No paid edition, optional heavy runtime or model weights were installed.

## NVIDIA Nemotron

Official sources: [API endpoint](https://docs.api.nvidia.com/nim/reference/llm-apis), [configured model](https://docs.api.nvidia.com/nim/reference/nvidia-llama-3_3-nemotron-super-49b-v1_5).

Defaults: `https://integrate.api.nvidia.com/v1`, model `nvidia/llama-3.3-nemotron-super-49b-v1.5`. A missing `NVIDIA_API_KEY` blocks inference without sending a request. With a key, the verifier sends one nonstreaming request capped at 32 output tokens and checks actual nonempty response content. It never prints the key or model output.

Create a free/trial key from the model's [NVIDIA build page](https://build.nvidia.com/nvidia/llama-3_3-nemotron-super-49b-v1_5), reviewing current access/terms. Do not enable billing. Store the key only in private configuration.

Meterless's documented inference route exposes `meterless/*` routing modes, not NVIDIA-hosted model IDs. The reviewed provider contract does not establish a hosted Nemotron bridge. Keep the NVIDIA API route separate until Meterless confirms a supported sponsor configuration; no unverified route is claimed operational.
