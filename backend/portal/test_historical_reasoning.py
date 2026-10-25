"""Historical acceptance is development-only; private originals are never stored in Git."""
import copy
import hashlib
import json
import os
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch
import tempfile
from django.test import SimpleTestCase
from .reasoning_preview import SAMPLE, envelope, parse_reasoning, present_reasoning, load_preview
from .snapshot_validation import SnapshotError, parse_snapshot

PIN = 'c223bc156b7d80049db24483140f45a1ee065f20106062d69bb249171fa07a30'

class HistoricalReasoningTests(SimpleTestCase):
    def payload(self):
        p = json.loads(SAMPLE.read_bytes())
        p['provenance'].update(model_calls=1249, model_errors=63,
            answered_by={'TEST/fast':879, 'TEST/blind':309, 'error':61})
        return p

    def test_inconsistent_ledgers_never_gain_a_general_bypass(self):
        p = self.payload()
        for raw in (json.dumps(p).encode(), json.dumps(p, indent=2).encode()):
            with self.subTest(format=len(raw)), self.assertRaises(SnapshotError):
                parse_reasoning(raw)
        # The exception covers exactly the historical error relationship, even internally.
        for total, errors in ((1248,63), (1249,62), (1249,64)):
            bad = copy.deepcopy(p)
            bad['provenance'].update(model_calls=total, model_errors=errors)
            with self.subTest(total=total, errors=errors), self.assertRaises(SnapshotError):
                envelope(bad, raw_sha256=PIN)

    def test_production_validator_rejects_reasoning_even_with_valid_ledger(self):
        p = json.loads(SAMPLE.read_bytes())
        with self.assertRaises(SnapshotError):
            parse_snapshot(json.dumps(p).encode())

    @skipUnless(os.getenv('QUORUM_TEST_GENUINE_SNAPSHOT'), 'private original not supplied')
    def test_exact_private_v3_and_negative_derivatives(self):
        raw = Path(os.environ['QUORUM_TEST_GENUINE_SNAPSHOT']).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), PIN)
        p = parse_reasoning(raw)
        self.assertEqual((p['status'], len(p['stories']), p['roundup']['count']), ('partial',0,28))
        with self.assertRaises(SnapshotError):
            parse_snapshot(raw)
        variants = [raw+b'\n', json.dumps(p).encode()]
        for mutate in (
            lambda x:x.update(unknown_field='TEST'),
            lambda x:x['roundup']['groups'][0]['items'][0]['sources'][0].update(url='javascript:alert(1)'),
            lambda x:x['provenance'].update(model_errors=62),
        ):
            bad=copy.deepcopy(p);mutate(bad);variants.append(json.dumps(bad).encode())
        for altered in variants:
            with self.subTest(sha=hashlib.sha256(altered).hexdigest()), self.assertRaises(SnapshotError):
                parse_reasoning(altered)
        self.assertEqual(Path(os.environ['QUORUM_TEST_GENUINE_SNAPSHOT']).read_bytes(),raw)

    @skipUnless(os.getenv('QUORUM_TEST_GENUINE_SNAPSHOT'), 'private original not supplied')
    def test_known_provisional_label_survives_missing_or_contradictory_sidecar(self):
        raw=Path(os.environ['QUORUM_TEST_GENUINE_SNAPSHOT']).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),PIN)
        self.assertTrue(present_reasoning(raw)['preview']['provisional'])
        p=json.loads(raw)
        sidecar=dict(snapshot={key:p[key] for key in ('topic_id','edition_date','version','run_id','status')},
            provisional=False,corpus_as_of_utc='2026-10-24T03:53Z',edition_window_utc=[p['window'][k] for k in ('start','end')])
        sidecar['snapshot']['sha256']=PIN
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'TEST-sidecar.json';path.write_text(json.dumps(sidecar))
            with patch.dict(os.environ,QUORUM_REASONING_PREVIEW_SIDECAR=str(path)), self.assertRaises(SnapshotError):
                load_preview(os.environ['QUORUM_TEST_GENUINE_SNAPSHOT'])
