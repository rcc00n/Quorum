"""Acceptance report tests use synthetic data and stub local Git reads, never provider calls."""
import copy
import hashlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase
from .reasoning_preview import SAMPLE

class ReasoningAcceptanceTests(SimpleTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        p=json.loads(SAMPLE.read_bytes())
        p['provenance'].update(fictional=False, corpus='zetaris', model='TEST/model', model_calls=1,
                               model_errors=0, answered_by={'TEST/model':1})
        self.raw=json.dumps(p).encode();(self.root/'snapshot.json').write_bytes(self.raw)
        sidecar=dict(snapshot={k:p[k] for k in ('topic_id','edition_date','version','run_id','status')},
            provisional=True,corpus_as_of_utc=p['window']['start'],edition_window_utc=[p['window'][k] for k in ('start','end')],
            producer=dict(commit='aaaaaaa (TEST producer)',config_sha256=hashlib.sha256(b'TEST config').hexdigest()),
            private_evidence=dict(log='TEST-private-path'))
        sidecar['snapshot']['sha256']=hashlib.sha256(self.raw).hexdigest()
        self.sidecar=json.dumps(sidecar).encode();(self.root/'sidecar.json').write_bytes(self.sidecar)
        self.options=dict(file=str(self.root/'snapshot.json'),sha256=hashlib.sha256(self.raw).hexdigest(),
            sidecar=str(self.root/'sidecar.json'),sidecar_sha256=hashlib.sha256(self.sidecar).hexdigest(),producer_commit='a'*40)

    def run_report(self, config=b'TEST config', blocked=False, **changes):
        out=io.StringIO()
        with patch('portal.management.commands.reasoning_snapshot.subprocess.check_output', return_value=config):
            if blocked:
                with self.assertRaises(CommandError):call_command('reasoning_snapshot', stdout=out, **(self.options|changes))
            else:call_command('reasoning_snapshot',stdout=out,**(self.options|changes))
        report=json.loads(out.getvalue())
        self.assertNotIn('TEST-private-path',out.getvalue())
        self.assertFalse(report['execution_verified']);self.assertFalse(report['source_text_verified']);self.assertFalse(report['published'])
        return report

    def test_matching_metadata_is_not_execution_or_publication_evidence(self):
        report=self.run_report()
        self.assertTrue(report['compatible']);self.assertTrue(report['metadata_valid'])
        self.assertEqual((self.root/'snapshot.json').read_bytes(),self.raw)
        self.assertEqual((self.root/'sidecar.json').read_bytes(),self.sidecar)

    def test_config_discrepancy_remains_blocked_without_disabling_presentation(self):
        report=self.run_report(config=b'TEST different config',blocked=True)
        self.assertTrue(report['compatible']);self.assertFalse(report['metadata_valid'])
        self.assertEqual(report['issues'],['producer_config_mismatch'])

    def test_hash_commit_and_missing_input_fail_without_exporting_values(self):
        for options in (dict(sha256='0'*64),dict(sidecar_sha256='1'*64),dict(sha256='short'),
                        dict(producer_commit='not-a-commit'),dict(producer_commit='b'*40),dict(file='/missing/TEST-private-path')):
            with self.subTest(options=list(options)):self.run_report(blocked=True,**options)

    def test_editorial_hold_blocks_acceptance_even_with_matching_metadata(self):
        with patch('portal.management.commands.reasoning_snapshot.artifact_review_issues',
                   return_value=['impact_score_review_required']):
            report = self.run_report(blocked=True)
        self.assertTrue(report['metadata_valid'])
        self.assertEqual(report['issues'], ['impact_score_review_required'])

    def test_v4_hold_is_exact_hash_only_and_never_changes_parser_rules(self):
        from .reasoning_preview import GENUINE_V4_SHA256, HISTORICAL_V3_SHA256, artifact_review_issues, artifact_review_notices
        self.assertEqual(artifact_review_issues(GENUINE_V4_SHA256), ['impact_score_review_required'])
        for sha in (HISTORICAL_V3_SHA256, '0' * 64, GENUINE_V4_SHA256[:-1] + '0'):
            self.assertEqual(artifact_review_issues(sha), [])
            self.assertEqual(artifact_review_notices(sha), [])
        notices = ' '.join(artifact_review_notices(GENUINE_V4_SHA256))
        self.assertIn('producer score 6 is preserved', notices)
        self.assertIn('has not passed independent impact review', notices)

    def test_known_run_hold_survives_reencoding_without_extending_parser_exceptions(self):
        from .reasoning_preview import artifact_review_issues, artifact_review_notices
        self.assertEqual(artifact_review_issues('0' * 64, '2026-10-24-russia-ukraine-war-5'),
                         ['impact_score_review_required'])
        self.assertTrue(artifact_review_notices('0' * 64, '2026-10-24-russia-ukraine-war-5'))
        self.assertEqual(artifact_review_issues('0' * 64, 'TEST-other-run'), [])
        with patch('portal.management.commands.reasoning_snapshot.artifact_review_issues',
                   return_value=['impact_score_review_required']) as review:
            self.run_report(blocked=True)
        review.assert_called_once_with(self.options['sha256'], json.loads(self.raw)['run_id'])


    def closed_producer(self, config=b'TEST\nconfig\n', **changes):
        sidecar = json.loads(self.sidecar)
        sidecar['producer'] = dict(commit_of_the_publishing_process='aaaaaaa',
            config_sha256_git_blob_lf=hashlib.sha256(config).hexdigest(),
            config_sha256_working_copy_crlf=hashlib.sha256(config.replace(b'\n', b'\r\n')).hexdigest()) | changes
        raw = json.dumps(sidecar).encode()
        (self.root/'sidecar.json').write_bytes(raw)
        self.options['sidecar_sha256'] = hashlib.sha256(raw).hexdigest()
        return config

    def test_complete_closed_config_metadata_never_proves_execution(self):
        config = self.closed_producer()
        report = self.run_report(config=config)
        self.assertTrue(report['metadata_valid'])
        self.assertEqual(report['issues'], [])
        with patch('portal.management.commands.reasoning_snapshot.artifact_review_issues',
                   return_value=['impact_score_review_required']):
            report = self.run_report(config=config, blocked=True)
        self.assertTrue(report['metadata_valid'])
        self.assertEqual(report['issues'], ['impact_score_review_required'])

    def test_closed_config_needs_both_full_matching_hashes(self):
        for field in ('config_sha256_git_blob_lf', 'config_sha256_working_copy_crlf'):
            for bad, issue in [('short', 'producer_config_hash_incomplete'),
                               ('0'*64, 'producer_config_mismatch'),
                               (True, 'producer_config_hash_incomplete')]:
                with self.subTest(field=field, value=type(bad).__name__):
                    config = self.closed_producer(**{field: bad})
                    report = self.run_report(config=config, blocked=True)
                    self.assertFalse(report['metadata_valid'])
                    self.assertEqual(report['issues'], [issue])


    def test_closed_producer_prefix_must_be_a_real_commit_reference(self):
        for value in ('', 'aaaaaa', 'a'*41, True, 123, 'aaaaaaa:private'):
            with self.subTest(value=type(value).__name__):
                config = self.closed_producer(commit_of_the_publishing_process=value)
                report = self.run_report(config=config, blocked=True)
                self.assertFalse(report['metadata_valid'])
                self.assertEqual(report['issues'], ['producer_commit_mismatch'])
