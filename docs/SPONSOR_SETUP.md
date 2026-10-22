# Organizer sponsor setup

Authority: GenAI Works Academy, **Start Here: Set Up Your Data, Build and Power Layers**, as corrected by the user. The [public course syllabus](https://academy.genai.works/courses/open-agent-hackathon-2026/details) confirms the Data/Build/Power layers but does not expose the lesson body. The exact sample dataset recipe, Composer/Grok prompt, provider URL and model ID still require the enrolled lesson or organizer. No project/track is selected.

## Zetaris Freemium

Use [zetaris/Freemium](https://github.com/zetaris/Freemium), pinned at `9dd4fe943afebca6b204b6ed5eccdca91b831e6c`, cloned outside Quorum at `~/.local/share/quorum/zetaris-freemium`. The prior Zetaris Cloud bundle instructions and UI-proxy API assumptions have been removed.

The actual upstream Compose contains four core services plus privateai, tools, Ollama, OpenSearch and digiavatar. Preparation selects **only** zetaris-db, zetaris-server, zetaris-api and zetaris-gui. It keeps upstream image tags, dependencies and entrypoints. No local LLM/GPU services are prepared or started.

Run `python3 scripts/services.py prepare`. This creates a mode-700 external runtime at `~/.local/share/quorum/zetaris-runtime`, with mode-600 `compose.json`, random PostgreSQL password, private installation-specific RSA DER keys, and isolated data directories. Existing configuration is preserved. The Compose project is `quorum-zetaris` with its own default network. Its database is reachable only on that network, so occupied host port 5432 needs no remapping or service changes. Host ports are **127.0.0.1:9001 (GUI), :8888 (REST), :10000 (JDBC)**. Debug/internal ports remain unpublished.

Security adaptations: replace the public upstream DB password and test encryption keys; use PostgreSQL's postgres role consistently so the supplied init script's grants are valid; disable statement logging; restrict upstream startup's recursive world-writable chmod to owner access; allow localhost/127.0.0.1 GUI origins. Other vendor initialization/start scripts are mounted read-only. These adaptations pass Compose validation but their image-level compatibility cannot be verified until image access and memory are available. Runtime ownership/key permissions may need image-specific validation at that point; do not weaken them to world-readable/writable.

The organizer requires at least 8 GB available to Docker. This setup uses a conservative **8 GiB allocated and currently available** gate. Current allocation is 7.66 GiB; available WSL RAM is roughly 4.6 GiB. No WSL memory limits were changed.

Docker Hub login was attempted once and required manual authentication. One pull of `zetaris/lightning-server:v2.4.1.0-latest` was denied. Other private images and public PostgreSQL were not downloaded after that denial. Do not repeat pulls until the organizer grants access.

After access is granted, authenticate locally with `docker login` and pull only the four services using the private Compose/project commands in SETUP.md. Start is guarded and never pulls automatically.

**Account initialization:** the actual Freemium README invokes `/home/zetaris/lightning/bin/dev-account.sh` inside zetaris-server. Use the documented helper with your own account/password/organization; do not use the README's public example password. The account helper has not run because containers cannot start. See manual actions for avoiding passwords in shell history.

**Sample data:** register the lesson's sample source in the GUI exactly as taught, then record its real dataset SELECT in private `ZETARIS_DATASET_SQL`. No sample name, external source URL, JDBC driver class or REST SQL route has been invented. Configure the matching official JDBC JAR and credentials. The Java smoke executes the supplied SELECT and requires an actual result row. `SELECT 1` or an open port does not establish dataset readiness.

Set `ZETARIS_REST_CHECK_URL` only to a documented Freemium API JSON endpoint. HTTP availability and authenticated dataset querying have separate statuses.

## Cursor Build layer

Preserve the installed, authenticated Cursor (authentication reported by user). Windows installation now reports 3.26.16 (previous CLI verification was 3.24.18); no update or reinstall was initiated by this work. No reinstall, logout, model-settings changes, extension installation or credit purchase is performed.

Use the lesson's Composer and Grok selections for the manual Agent smoke. A preparatory read-only prompt and external acceptance record are documented in MANUAL_ACTIONS.md. Exact lesson prompt/model availability remains unverified until the lesson is accessible. Do not paste Meterless keys into Cursor model settings or use provider inference credits for coding.

## Meterless → NVIDIA Nemotron Power layer

Required private fields are **METERLESS_BASE_URL**, **METERLESS_API_KEY**, **NEMOTRON_MODEL**, all blank by default. Obtain the exact values and supported OpenAI-compatible chat contract from the organizer. No direct NVIDIA API fallback, guessed URL, version path or model ID is configured.

`./scripts/verify-all.sh` never sends provider inference requests. The explicit one-request smoke is `./scripts/verify-all.sh --inference`; it requires all three real values and sends one nonstreaming `/chat/completions` request with 32 output tokens maximum. It does not retry, print outputs/keys, purchase credits or run development workloads. Confirm the provided route/key is for sponsored smoke testing before invoking it.

The existing H-MEM reference and state-persistence tests remain useful component checks. They do **not** establish hosted Meterless access, Nemotron model identity or inference readiness. Only a real nonempty response from the organizer-configured route passes the inference smoke. A response alone cannot independently prove which backend model the provider executed.
