"""All inputs are synthetic TEST data; never read original prompts, replies or logs."""
from collections import Counter
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
import audit_execution as audit


def row(reply='TEST reply', key='a', **changes):
    return dict(task='stance', lane='default', route='TEST/model', served='TEST/model',
                ms=1, attempts=1, run_id='2026-10-24-russia-ukraine-war-5', request_key=key*64,
                tokens_in=2, tokens_out=3, payload={'TEST': 'private-passage'}, reply=reply,
                reply_sha256=audit.digest(reply.encode())) | changes


def ledger(rows):
    return dict(topic_id='TEST-topic', edition_date='2026-10-24', version=4,
                run_id=rows[0]['run_id'], calls=[{k:v for k,v in r.items() if k not in ('payload','reply')} for r in rows])


def snapshot(rows):
    value = {k:v for k,v in ledger(rows).items() if k != 'calls'}
    value['provenance'] = dict(model_calls=len(rows), model_errors=sum(r['served']=='error' for r in rows),
                               answered_by=dict(Counter(r['served'] for r in rows)))
    return value


def log(restored=1, replay_count=1, call='stance default TEST/model 1 ms 2>3'):
    return (f'seeding 2026-10-24-russia-ukraine-war-5: {restored} journalled calls restored into the ledger\n'
            + '  · stance replayed from journal\n'*replay_count + '  · '+call+'\n').encode()


class ExecutionAuditTests(unittest.TestCase):
    def test_duplicate_keys_and_nonfinite_are_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(audit.AuditError): audit.strict_json(raw)

    def test_truncated_or_corrupt_journal_cannot_pass(self):
        original=row()
        for raw in (json.dumps(original).encode(), b'not-json\n',
                    (json.dumps(original | {'reply':'TEST changed'})+'\n').encode()):
            with self.subTest(length=len(raw)), self.assertRaises(audit.AuditError): audit.journal_rows(raw)

    def test_usage_null_is_allowed_only_for_failed_calls_and_bool_is_never_an_integer(self):
        failure=row(served='error', error='TEST failure', tokens_in=None, tokens_out=None)
        failure.pop('reply');failure.pop('reply_sha256')
        self.assertEqual(audit.journal_rows((json.dumps(failure)+'\n').encode()), [failure])
        for altered in (row(tokens_in=None), row(ms=True), row(attempts=False)):
            with self.subTest(fields=list(altered)), self.assertRaises(audit.AuditError):
                audit.journal_rows((json.dumps(altered)+'\n').encode())

    def test_ledger_preserves_duplicate_key_order_and_reply_identity(self):
        rows=[row('TEST first'),row('TEST second')]
        report=audit.ledger_matches(ledger(rows),rows,snapshot(rows))
        self.assertEqual(report['rows'],2)
        for bad in (ledger(rows[::-1]), ledger(rows[:1])):
            with self.subTest(length=len(bad['calls'])), self.assertRaises(audit.AuditError):
                audit.ledger_matches(bad,rows,snapshot(rows))

    def test_ledger_rejects_model_counts_and_boolean_identity(self):
        rows=[row()]
        for value in (snapshot(rows) | {'version':True}, snapshot(rows) | {'provenance':dict(model_calls=1,model_errors=False,answered_by={'TEST/model':1})}):
            with self.assertRaises(audit.AuditError): audit.ledger_matches(ledger(rows),rows,value)

    def test_replay_summary_retains_multiplicity_and_never_claims_per_key_proof(self):
        rows=[row('TEST first'),row('TEST second'),row(key='b')]
        result=audit.session_matches(rows,log(restored=2),'2026-10-24-russia-ukraine-war-5')[0]
        self.assertEqual((result['replayed'],result['live'],result['unused_replayable'],result['duplicate_seed_occurrences']), (1,1,1,1))

    def test_replay_over_capacity_or_wrong_live_model_is_rejected(self):
        rows=[row(),row(key='b')]
        for data in (log(replay_count=2),log(call='stance default TEST/wrong 1 ms 2>3'),log(call='stance default TEST/model 1 ms 9>3')):
            with self.subTest(length=len(data)), self.assertRaises(audit.AuditError):
                audit.session_matches(rows,data,'2026-10-24-russia-ukraine-war-5')

    def test_receipts_reject_mutation_symlinks_and_ambiguous_names(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'TEST.json';p.write_bytes(b'{}')
            entry=dict(path=p.name,size_bytes=2,sha256=audit.digest(b'{}'))
            self.assertEqual(audit.checked_inputs(root,[entry]), {'TEST.json':b'{}'})
            with self.assertRaises(audit.AuditError):audit.checked_inputs(root,[entry,entry | {'path':'other/TEST.json'}])
            with self.assertRaises(audit.AuditError):audit.checked_inputs(root,[entry | {'path':'../TEST.json'}])
            p.write_bytes(b'[]')
            with self.assertRaises(audit.AuditError):audit.checked_inputs(root,[entry])
            link=root/'LINK.json';link.symlink_to(p)
            with self.assertRaises(audit.AuditError):audit.checked_inputs(root,[entry | {'path':link.name}])

    def test_cli_refuses_existing_reports_and_never_prints_input_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);inputs=root/'inputs';inputs.mkdir();manifest=root/'manifest.json';manifest.write_text('[]')
            report=root/'report.json';report.write_text('TEST keep this report')
            output=io.StringIO()
            with redirect_stdout(output):status=audit.main(['--inputs',str(inputs),'--manifest',str(manifest),'--report',str(report)])
            self.assertEqual(status,1);self.assertEqual(report.read_text(),'TEST keep this report')
            self.assertNotIn(temp,output.getvalue())


    def test_complete_synthetic_bundle_checks_lineage_and_keeps_proof_limits(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            rows={3:[row(key='a',run_id='2026-10-24-russia-ukraine-war-3'),
                     row(key='f',task='review_disputed',run_id='2026-10-24-russia-ukraine-war-3')]}
            rows[4]=[rows[3][0],row(key='b',task='event_key',run_id='2026-10-24-russia-ukraine-war-4')]
            for n,key in ((5,'c'),(6,'d'),(7,'e')):
                rows[n]=rows[n-1]+[row(key=key,run_id=f'2026-10-24-russia-ukraine-war-{n}')]
            for n,values in rows.items():
                (root/f'2026-10-24-russia-ukraine-war-{n}.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in values))
            for version,attempt in ((4,5),(6,7)):
                data=ledger(rows[attempt]);data.update(version=version,run_id=f'2026-10-24-russia-ukraine-war-{attempt}')
                snap=snapshot(rows[attempt]);snap.update(version=version,run_id=data['run_id'])
                (root/f'v{version}.ledger.json').write_text(json.dumps(data))
                (root/f'2026-10-24-closed-v{version}.snapshot.json').write_text(json.dumps(snap))
            for attempt in (5,6,7):
                data=log(restored=len(rows[attempt])-1).decode().replace('war-5:',f'war-{attempt}:')
                (root/f'live_2026-10-24_attempt{attempt}.log').write_text(data)
            def receipts():
                return [dict(path=p.name,size_bytes=p.stat().st_size,sha256=audit.digest(p.read_bytes())) for p in root.iterdir()]
            report=audit.audit_bundle(root,receipts())
            self.assertTrue(report['seed_lineage_verified'])
            self.assertEqual(report['versions']['4']['rows'],3)
            for flag in ('per_key_replay_consumption_verified','process_config_at_launch_verified',
                         'provider_execution_verified','source_text_verified','published'):
                self.assertFalse(report[flag])
            # Re-hashing a modified artifact cannot make inconsistent seed lineage pass.
            rows[7][0]=row(reply='TEST modified seed',run_id='2026-10-24-russia-ukraine-war-3')
            (root/'2026-10-24-russia-ukraine-war-7.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows[7]))
            with self.assertRaisesRegex(audit.AuditError,'journal_seed_prefix_mismatch'):
                audit.audit_bundle(root,receipts())
