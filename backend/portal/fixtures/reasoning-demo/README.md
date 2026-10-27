# FICTIONAL reasoning 1.0 fixtures

Development/tests only; not real news, verified collection provenance, publication-grade validation or proof of model execution.

Exact byte copies of `docs/examples/` on `origin/yelysei/agents@6ea82434d0f06cefb51f5536732ceac68e9780ef`, canonical `docs/ARCHITECTURE.md` §8. All schema1.0, edition2026-10-22, topic `russia-ukraine-war`, run `2026-10-22-russia-ukraine-war-1`, version1, published_at null, fictional true, stand-ins model.

| File | Stories / trace / roundup | SHA-256 |
| --- | --- | --- |
| [snapshot.sample.json](snapshot.sample.json) | 2 / 45 / 2 | `2dd7510a618c584ee3925efb9de3c745417a6abe549a10f3042271ce22ab0366` |
| [snapshot.empty-day.sample.json](snapshot.empty-day.sample.json) | 0 / 29 / 3 | `014cc695491181a61012559aeb97ddd878938571b21bb749597bc55190ea97e7` |
| [snapshot.partial.sample.json](snapshot.partial.sample.json) | 2 / 45 / 2 | `df0c03e5903b5dd2238eb03233a10f25ac0515e6a3ed65ea4d059b1de1769495` |
| [snapshot.sample.sidecar.json](snapshot.sample.sidecar.json) | the provisional sidecar for `snapshot.sample.json`, in the producer's exact shape (`reasoning/scripts/edition_sidecar.py` `build_sidecar` + `serialize`: five keys in order, `bytes`, a 40-hex commit, `corpus_as_of_utc` = the window's start) | `8a7d6dcee9609fc3399ecf95d585c1268a1f484b1289ad6f4f8eb3636dcdf4a6` |
| [producer-config.sample.toml](producer-config.sample.toml) | TEST bytes standing in for the producer's `reasoning/config/reasoning.toml`; the sidecar's `producer.config_sha256` is their sha256, so the acceptance passes them as `--producer-config` | `fc3a3e4f199b5d7b3d33b84bb8ff4647f3c6e2be5c1cf186f819efa191242bfe` |

The sidecar pair (2026-10-27, Anastasia / Claude Code) exists so a portal test accepts the producer's shape itself, not a hand-built sidecar; `reasoning/tests/test_portal_sidecar_fixture.py` checks that the producer's builder still writes these bytes. Regenerate both when `snapshot.sample.json` or the builder changes (`build_sidecar(raw, p, window.start, '6ea82434d0f06cefb51f5536732ceac68e9780ef', sha256(config))`). Main/partial roundup each has one group. Partial has structured frame errors and omits framing prose while preserving coverage pairs. Samples include generated/expiry/window/timezone/corpus/model declarations; these do not establish real publication. No native context block/photo; explicitly TEST-labelled derivatives exercise context/XSS/missing trace. Zero durations/null models remain unchanged.

The gated local `portal.reasoning_preview` alone consumes these files; ordinary feed/store/publisher never load them. Strict production validation deliberately rejects all three. Hashes identify fixture bytes, not source-content hashes. Topic ID is not silently aliased to collector `ukraine-aid`.

[Current adapter/missing provenance](../../../../docs/PORTAL_INTEGRATION.md#reasoning-10-fictional-development-preview) · [preview and tests](../../../../docs/PORTAL_VERIFICATION.md#current-reproducible-checks) · [notify interface changes](../../../../docs/TEAM_HANDOFF.md#interface-change-notification-protocol).
