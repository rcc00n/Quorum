# Web Integration: Start Here

Owner: Vadim (@rcc00n), `feature/web-portals`; [draft PR #1](https://github.com/rcc00n/Quorum/pull/1). [Issue #2](https://github.com/rcc00n/Quorum/issues/2) is the canonical shared tracker. This handoff supplements **AGENTS.md → Shared Project Tracking and Cross-Agent Handoff**; it is not a replacement rulebook or a change to master.

1. **Already implemented:** Django sessions, permissions, preferences, Control, Next.js portal; strict internal snapshot validation/projection/store/revisions/rollback; articles, Evidence Explorer, paired reviews, Perspective Comparison, cohorts, roundup and recorded Investigation Timeline. [Inventory](IMPLEMENTATION_STATUS.md) distinguishes shipped code from fictional-only tests.
2. **Provide reasoning output:** Yelysei owns reasoning 1.0 in his latest `docs/ARCHITECTURE.md` §8. [Integration guide](PORTAL_INTEGRATION.md) pins inspected revisions, mappings and exact outstanding provenance. Do not generate the portal's internal proposal instead of reasoning's own contract.
3. **Test locally:** follow [reproducible checks](PORTAL_VERIFICATION.md#current-reproducible-checks), including the three canonical FICTIONAL samples through real Django/Next HTTP. No model calls or production credentials are needed.
4. **Production versus demo:** existing website/auth/catalog are deployed; reasoning 1.0 preview is localhost-only and fictional. Production publication and transport remain disabled/unapproved. [Release checklist](RELEASE_CHECKLIST.md) and [deployment procedure](../deploy/README.md) belong to Vadim.
5. **Blocked:** a genuine full-provenance result, production bridge and transport approval. Envelope dates/model/corpus declarations now exist; those declarations alone do not establish an actual sponsor run. See the [field-level handoff](PORTAL_INTEGRATION.md#remaining-production-handoff).
6. **Notify Vadim:** use the interface-change procedure below, before integration/merge when practical. Other branches do not automatically read these files: explicitly tell your active assistant to read this handoff and Issue #2.
7. **First real result:** post its branch/SHA, safe sample path/hash and actual corpus/model evidence in Issue #2. Vadim validates and renders it locally; all three owners resolve provenance/identity/transport decisions before any production activation.

## Interface-change notification protocol

This operational format implements AGENTS.md's existing requirement to report interface changes. It is requested on the web branch and announced in Issue #2; adoption by other active assistants requires acknowledgement. No other branch's AGENTS.md is edited.

Notify when a change touches the web boundary:

- Reasoning schema/version; JSON additions/removals/renames, meanings or nullability.
- Status, errors, versions, correction/supersession, source/event/claim identities.
- Quote hashes, text versions, Unicode offsets, access levels, independence or wire rules.
- Trace/review records; topic/date/edition/freshness semantics.
- Transport endpoints or authentication; breaking collector/reasoning behavior.
- Website presentation dependencies or any new genuine end-to-end sample.

The responsible human/assistant posts **one concise actionable update in Issue #2**, preferably before integration or merging, and tags @rcc00n. Reasoning changes also tag @Sor1na; collector/provenance changes also tag @AnastasiaShkirpan; changes across all blocks tag all three. Never silently break another consumer. Do not attach secrets, raw private logs, credentials or private reasoning.

```text
WEB INTEGRATION CHANGE — ACTION REQUIRED
Owner:
Branch / commit:
Changed files / contract:
Previous behavior:
New behavior:
Breaking change: YES / NO
Example / evidence: (public-safe JSON/sample path, hash, test result)
Required from @rcc00n: (concrete action, or no action)
Integration impact: (blocks next milestone YES / NO; dependency)
```

The same duty applies to **Vadim's agent**: document changed portal acceptance, supported reasoning fields, API/authentication/transport requirements or frontend dependencies; give the commit, update Issue #2 and tag affected owners with required action. Internal CSS/refactoring needs no upstream action request. Interface proposals must say **PROPOSED**, never imply team approval. Use existing AGENTS.md statuses; notification is not evidence of integration.

## Notification and acknowledgement record

Latest explicit-acknowledgement audit (2026-10-23): the fetched 16-comment Issue #2 history contains no adoption acknowledgement from either teammate. Anastasia's earlier collection report is not an acknowledgement of the notification protocol or later model findings. [One ACTION REQUIRED follow-up](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6377086206) requests instruction/adoption by their **currently active agents**, review of both experiments, an actual Zetaris sample/topic/date/provenance handoff, and a named Meterless Engine feature owner. Both acknowledgements remain pending; mentions and delivery are not confirmation.

| Owner | Notification | Explicit acknowledgement |
| --- | --- | --- |
| Yelysei @Sor1na | [Team-wide Issue #2 announcement](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6357796090) | Pending; no adoption claimed |
| Anastasia @AnastasiaShkirpan | Same announcement | Pending; no adoption claimed |
| Vadim @rcc00n | Own web agent follows this procedure in this milestone | User requested; implementation/evidence in Issue #2 |

Each teammate is asked to instruct their **currently active coding agent** to follow this procedure and explicitly acknowledge in Issue #2. A mention or successful comment does not establish acknowledgement. Existing master AGENTS.md already requires interface-change reporting; any future stronger master rule must be proposed as a reviewed documentation diff/PR for human approval, not silently installed here.
