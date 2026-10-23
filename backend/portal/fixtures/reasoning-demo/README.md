# FICTIONAL reasoning 1.0 fixture

Development and tests only. No real news, model execution, collected quotes or verified provenance is established by this file.

`snapshot.sample.json` is a byte-for-byte copy of `docs/examples/snapshot.sample.json` on `origin/yelysei/agents@8a4d453e0ab1f1338abcf77c5eac62d18d9ec2d6` (sample introduced in `b4a6674`). SHA-256: `4662e8aa1616f39cad3663ce2963aaf9eec0eac82929b1637d6419168a7287d1`. Schema/version: reasoning `1.0`, edition `2026-10-22`, run `2026-10-22-russia-ukraine-war-1`, version `1`.

Two featured stories, two roundup events and 45 recorded steps. The exact sample has **no context block or photo**; context rendering is tested in an explicitly TEST-labelled derivative. `duration_ms: 0` is retained; no times or model calls are synthesized. Sample topic `russia-ukraine-war` is not silently mapped to collector `ukraine-aid`.

`portal.reasoning_preview` consumes it only through the gated local preview; production feed/publisher never load it. The strict production validator deliberately rejects it. The file hash identifies these fixture bytes, not source document content. See [canonical integration handoff](../../../../docs/PORTAL_INTEGRATION.md#reasoning-10-fictional-development-preview) for gates, missing metadata and local commands.
