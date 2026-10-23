# Nemotron routing diagnosis, 2026-10-23

Model access through Meterless Nightshift v1.2.2 and directly against `integrate.api.nvidia.com`: thinking
mode, lane pinning, model availability, 500s. Evidence: this session's own probe chronology (recorded in
the diagnostic brief), the public Meterless repository and site, NVIDIA's own repositories and docs, and
third-party captures from the same hackathon week. Claims from search-extracted pages (this build
environment cannot fetch build.nvidia.com or meterless.ai directly) are marked; everything else was read
verbatim at the cited URL. No model calls were made from this session; the probes marked "local" are for
Yelysei to run, one call each.

## Q1 — Thinking off on the direct NVIDIA route

**The control our client sends is the documented one, and the mechanics are right.** NVIDIA's Nemotron 3.5
Lightning usage cookbook: "The model supports two modes: Reasoning ON (default) and Reasoning OFF. Toggle by
setting `enable_thinking` to `False` in `chat_template_kwargs`"
(github.com/NVIDIA-NeMo/Nemotron, usage-cookbook/Nemotron-3.5-Lightning/vllm_cookbook.ipynb). NVIDIA's
skills reference confirms the SDK mechanics we use: "With an OpenAI-compatible SDK these provider fields
travel in `extra_body`, which merges them into the top level of the request body"
(github.com/NVIDIA/skills, nemotron-voice-agent-builder/references/models/llm.md) — and that the default is
ON when the field is omitted, hosted endpoints included.

Facts that explain the first live run's behaviour:

- On the hosted endpoint the trace is returned in a separate `reasoning_content` field (the parser is
  enabled server-side; self-hosted NIM/vLLM are not — github.com/NVIDIA-AI-Blueprints/nemotron-voice-agent,
  docs/how-to/configure-llm.md). The "thinking prose in content" we saw came through Nightshift, which may
  not run the parser.
- The trace counts against `max_tokens`; when the trace fills the ceiling the reply is
  `finish_reason: length` with no answer (NIM docs for Lightning, search-extracted). The trace is forcibly
  cut only at `reasoning_budget + 500` (cookbook). Consequence in code: with thinking on, `max_tokens` is
  now lifted to `reasoning_budget + 1000` when lower; with thinking off, `force_nonempty_content: true`
  rides along (both in `llm._request_extras`, decision in reasoning/README.md).
- `reasoning_budget` applies only when thinking is on: "Setting `LLM_REASONING_BUDGET=0` alone does not
  disable reasoning" (github.com/NVIDIA-AI-Blueprints/rag, docs/enable-nemotron-thinking.md). Our config
  already sends it only with `reasoning = "on"`.
- The cookbook recommends `temperature=1.0, top_p=0.95` for Lightning in both modes. We run 0.1 for
  near-deterministic judgments; if live JSON quality degrades (truncation, repetition), this is the first
  knob to revisit — a product decision, not made here.

**Local verification (one call):** on the direct route, `python -m quorum_reasoning.run --probe`. Expected
with thinking off: completion tokens in the low tens, 1–3 s, `parsed` showing clean stance JSON. If
completion tokens stay near 1000 with a clean short reply, the usage number is counting a reasoning trace
the endpoint still generated — then paste the probe output and the next candidate is the NIM-era name
`chat_template_kwargs.thinking_token_budget` (NVIDIA uses three names across stacks; the hosted samples use
top-level `reasoning_budget`).

## Q2 — 404 "Function not found for account" for every Nemotron except Lightning

Each hosted model is an NVCF "function"; the 404 means that function is not enabled for the account.
**There is no official documentation of this mechanism, no per-model enable step, and no documented
trial-tier model list.** Three findings bound the problem:

- `GET /v1/models` listing a model does not mean it is callable; this mismatch is widely observed and
  nowhere documented as intended (e.g. github.com/tashfeenahmed/freellmapi/issues/1489; an NVIDIA forum
  thread asking for an authoritative list has no official answer).
- **`nvidia/nemotron-3-super-120b-a12b` has been returning exactly this 404 for everyone since about
  2026-10-20** (github.com/NVIDIA/NemoClaw/issues/13536, which reports Ultra-550B and Super-VL-120B serving
  normally from the same account). So the 404 on Super-120B is NVIDIA-side, not a key or account mistake.
- Keys from build.nvidia.com are account-wide, not per model (created at build.nvidia.com/settings/api-keys);
  forum reports name a "Public API Endpoints" permission that can be missing from an account — not our case,
  since Lightning serves.

**Steps for a second Nemotron on the fact-checker lane (one request per model, in this order):**

1. Set `NEMOTRON_MODEL_FACT_CHECKER=nvidia/nemotron-3-ultra-550b-a55b` and run
   `python -m quorum_reasoning.run --test-connection`. Ultra was serving while Super-120B 404ed, and we have
   already seen it answer through Nightshift. Alternative: `nvidia/nemotron-3.5-super-vl-120b-a12b`.
2. If 404: generate a fresh key at build.nvidia.com/settings/api-keys, enabling every scope offered
   ("Catalog", "Public API Endpoints"), and repeat once.
3. If still 404, the only channel is the NVIDIA developer forum's accounts category; there is no documented
   self-service fix. Run the demo with Lightning on both lanes (the recorded fallback decision) until then.

Avoid `nvidia/llama-3.3-nemotron-super-49b-v1.5` for the fact-checker: its thinking switch is a
system-prompt `/no_think` (NGC model card), not `chat_template_kwargs`, so our single reasoning control
would not reach it and every call would pay a thinking trace.

## Q3 — Does Nightshift forward `chat_template_kwargs` and `max_tokens`?

**Not documented, and the published contract does not cover it.** The only public Meterless provider
contract is Runtime **0.90.0** (github.com/Meterless/Meterless,
docs/agent-ready/add-meterless-provider.md); the repository's ROADMAP lists the runtime spec as "drop
pending". "Runtime 1.4" exists only in the gated organizer Setup Guide. The published body contract is one
sentence (plain-text requests stay OpenAI-shaped); nothing specifies which fields are forwarded or
stripped.

Evidence available anyway:

- `max_tokens` **is** forwarded: a third-party capture in the same week saw Nightshift return a 502
  `_empty_response` when `max_tokens` was 64 "because reasoning tokens used the budget"
  (github.com/awkwardapples/Arbiter, pull 6) — which also shows thinking stayed ON through Nightshift.
- Our own comparison says `chat_template_kwargs` does **not** take effect through Nightshift: the identical
  request with `enable_thinking: false` produced ~975 completion tokens through Nightshift and (expected,
  Q1 probe to confirm) tens of tokens on the direct route. Whether Nightshift strips the field or its lane
  settings override it cannot be told from outside.
- Nightshift's chat response carries a `meterless` object (`requested_model`, `provider_model`,
  `routed_model`, `receipt_id`, signed receipt envelope — same capture). The ledger and `--probe` now record
  `routed_model` and `receipt_id` when present, so each demo request can be matched to Console › Proof.
- No debug flag, log path or Console body view is documented. The discriminating experiment that needs no
  Meterless internals: run the same `--probe` through Nightshift and directly, compare completion tokens.
  To confirm what our SDK sends (it is correct per NVIDIA's skills doc, but to close the question): run the
  loopback logging proxy I prepared (see "Local verification steps") — it prints our request's top-level
  body keys, keys redacted, forwards to 127.0.0.1:8088, writes nothing to disk.

**For Meterless (report as questions/limitations):** body-field passthrough rules; a client-facing
reasoning control; the Runtime 1.4 contract text; per-request body in receipts; debug logging.

## Q4 — Pinning a model through Nightshift

The documented route vocabulary is `meterless/<disposition>` with dispositions **auto, fast, deep, cheap,
local, fusion**, plus `meterless/<class>` and `meterless/<class>.<disposition>` with classes **vision,
text, image, video** (docs/products/nightshift/hotspot.md and the provider contract). The docs state
plainly: "Your app does not pick a model file. It picks a disposition, and the runtime routes to the fleet
you have" and "Routing modes, not model names".

Consequences:

- **`meterless/judge` and `meterless/verify` are not in the published vocabulary.** Lane duties
  (Race/Judge/Verify/…) exist in the product, but no documented mapping from route ids to duties, no way to
  name a lane, and no way to force an exact model. Our attempts to pin via `deep`/`judge` routes or explicit
  `nvidia/...` ids were attempts at undocumented behaviour.
- **Explicit `nvidia/...` ids in the model field have no documented semantics at all** — the observed
  silent, non-deterministic substitution is therefore a limitation to report, not a bug we can cite against
  a contract.
- The same-week third-party capture matches ours exactly: `meterless/fast` and `meterless/deep` both landed
  on the Lightning lane; "deep currently lands on the same Lightning 30B lane as fast" and fixing it is "a
  Nightshift lane setting", i.e. server-side.

**Proposed Nightshift setup to try (local, two `--test-connection` calls, no graph run):** keep the
Lightning lane as is; on the second lane set the model to `nvidia/nemotron-3-ultra-550b-a55b` and its duty
to **Judge** (re-create the lane choosing a judge-type job if the wizard has no duty switch); then set
`NEMOTRON_MODEL=meterless/fast` and `NEMOTRON_MODEL_FACT_CHECKER=meterless/text.deep` and run
`--test-connection`. If `answered_by`/`routed_model` still shows Lightning on both, stop: two models through
Nightshift v1.2.2 is not achievable from the client today — keep the recorded fallback (both lanes
Lightning, fact-checker independence = blind context + own prompt role) for the demo, and the second model
runs on the direct route in development. Report the pinning question to Meterless either way.

## Q5 — The 500s through Nightshift (44–137 s)

No public Meterless doc describes an upstream timeout, 429 pass-through or per-minute throttling, so the
receipts in Console › Activity for those exact requests remain the only direct evidence (local step below).
What the public record supports:

- NVIDIA's hosted gateway has a reverse-engineered **~120 s ceiling** and is known to drop sockets after a
  5xx (github.com/diegosouzapw/OmniRoute/issues/3884); NVIDIA's own integration raises client timeouts to
  300 s because first bytes can take over 120 s. Our failures at 137 s (big `extract_claims` payload) and
  44 s fit generation inflated by a thinking trace crossing that ceiling, surfaced by Nightshift as a bare
  500.
- Rate-limit violations surface as **429**, not 500 (NVIDIA's own troubleshooting docs), so the per-minute
  cap is the less likely cause — but through Nightshift we cannot see the upstream status without receipts.

**Values:** with thinking off the calls drop to seconds and the ceiling stops mattering; keep `TIMEOUT_S`
at the contract-documented 180 s. For direct-route live runs, set `[models] min_interval_ms = 1600` in
`config/reasoning.toml` (37 req/min, under the 40-rpm trial cap). If a Nightshift receipt shows an upstream
429, the same 1600 ms applies there; if it shows an upstream timeout, nothing client-side fixes it — split
the `extract_claims` payload (fewer documents per call) instead, and that becomes a code change to propose.

## What is a Nightshift limitation vs our mistake

Ours (all corrected in code or recorded as superseded): expecting explicit `nvidia/...` ids to pin a lane
(undocumented); expecting `deep`/`judge` to select the second lane (`judge`/`verify` are not routes; `deep`
ranks, it does not pin); `/no_think` in the system prompt (Qwen3's switch, not Nemotron's — superseded the
same day); `max_tokens` low enough that a thinking trace could consume the whole reply (guard added).

Nightshift v1.2.2 limitations, to report to Meterless: no client-side model pinning and silent
non-deterministic substitution of explicit model ids; `chat_template_kwargs` apparently not applied
upstream (`max_tokens` is); the Runtime 1.4 contract unpublished (public contract stops at 0.90.0, spec
"drop pending"); upstream errors flattened to bare 500s; the "Runtime endpoint is offline" banner stuck in
LOCAL ONLY mode with loopback working (no public mention of this issue anywhere); no documented debug
logging or request-body view in receipts.

NVIDIA-side, not ours: Super-120B's global 404 since ~Oct 20; `/v1/models` listing uncallable functions;
undocumented trial limits and timeouts.

## Recommended configuration

**(a) Development runs (now):** direct route, `.env` per `.env.example`'s direct-route block —
`NEMOTRON_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b`,
`NEMOTRON_MODEL_FACT_CHECKER=nvidia/nemotron-3-ultra-550b-a55b` once Q2 step 1 passes (Lightning on both
until then); `[models] reasoning = "off"`, `max_tokens = 1500`, `min_interval_ms = 1600`.

**(b) Demo run (must go through Nightshift, Power rule):** `MODEL_BASE_URL=http://127.0.0.1:8088/v1`, both
routes `meterless/fast` (or the Q4 split if the duty experiment works), `reasoning = "off"` kept — harmless
if Nightshift drops it, correct if it forwards; per-minute throttle off unless receipts show upstream 429s.
Evidence for the award write-up comes from `provenance.answered_by` plus the per-call `receipt_id` now in
the ledger, matched to Console › Proof.

## Local verification steps (nothing here can run from the cloud container)

1. Direct route, thinking: `python -m quorum_reasoning.run --probe` → expect tens of completion tokens,
   1–3 s (Q1).
2. Fact-checker model: set Ultra-550B, `python -m quorum_reasoning.run --test-connection` → expect
   `answered_by nvidia/nemotron-3-ultra-550b-a55b`, reply "ready" (Q2).
3. Nightshift passthrough: same `--probe` with `.env` pointed back at Nightshift; compare completion tokens
   with step 1 (Q3). Optionally run the logging proxy first to print our exact body keys.
4. The two-lane experiment of Q4 (`--test-connection`, two calls).
5. Console › Activity receipts for the failed requests of the first live run (Q5): note the upstream status
   per receipt.
