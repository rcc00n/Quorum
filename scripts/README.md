# Diagnostics and offline evidence audits

Routine environment diagnostics use `doctor.sh` and `verify-all.sh`; configuration,
credit-free defaults and the official bundle checks are documented in
[setup](../docs/SETUP.md). `--offline` checks local tools without reading private
configuration or contacting services. It deliberately reports live evidence blocked.

## Original execution receipts

`audit_execution.py` audits the privately handed-over v4/v6 ledgers, journals for
attempts 3–7 and recorded logs. It uses only Python's standard library and never
imports the reasoning graph, calls a provider or prints prompts, replies, keys or
log text. Originals and reports must remain outside this public checkout.

```bash
python3 scripts/audit_execution.py --inputs <private-download-directory> \
  --manifest <external-owner-receipts.json> --report <new-external-report.json>
```

The manifest is a JSON array of `{path, size_bytes, sha256}` entries. Use the original
owner receipts in [Issue #2 comment 6403229269](https://github.com/rcc00n/Quorum/issues/2#issuecomment-6403229269),
plus the previously announced v4/v6 snapshot hashes. Paths are relative receipt
names, resolved by unique basename inside the private input directory. The bundle
requires all five journals, both ledgers, both snapshots and logs for attempts 5–7;
other manifest inputs are integrity-checked too. Ambiguous names, links, bad hashes,
duplicate/nonfinite JSON, altered replies, reordered ledger occurrences and
inconsistent log boundaries fail closed. Existing report files are never overwritten.

The verifier compares every ledger row, retaining duplicate request-key occurrences;
checks reply SHA-256; verifies the documented removal of old `review_disputed` rows
between attempts 3/4 and exact byte prefixes thereafter; and compares logged live
rows to journal rows, including task/lane/model/duration/usage. Unknown token usage
on failed calls stays null. Replay counts are bounded by the actual queued task
multiset and remain distinct from served/live rows.

A replay log records the task, not the consumed request key or FIFO occurrence.
Therefore per-key consumption, process-start code/config identity, provider-side
execution/source correctness and publication are never marked verified by this tool.
It is a receipt audit, not a complete execution attestation. No existing native
snapshot acceptance or publishing flag is changed by its report.

Synthetic regressions: `python3 -m unittest discover -s scripts -p 'test_*.py'`.
They create only TEST inputs and disposable indexes; they are not live integration.

## Decisions

2026-10-25 · rcc00n / Codex · Keep original receipt auditing independent of reasoning/runtime clients; require external inputs/reports and compare ordered row occurrences with explicit proof limits. Why: offline audit must preserve multiplicity and private material without spending credits or turning partial reconciliation into execution/publication approval. Numeric bounds and historical seed handling are recorded at their implementation sites.
