"""Private historical originals are opt-in; never substitute a synthetic v4 artifact."""
import copy
import hashlib
import json
import os
from pathlib import Path
from unittest import skipUnless
from django.test import SimpleTestCase
from .reasoning_preview import (SAMPLE, GENUINE_V4_SHA256, GENUINE_V4_SIDECAR_SHA256,
    bind_preview_sidecar, parse_reasoning, present_reasoning)
from .snapshot_validation import SnapshotError, parse_snapshot

class ClosedV4Tests(SimpleTestCase):
    def test_unpinned_closed_format_cannot_bind_arbitrary_snapshot(self):
        raw = SAMPLE.read_bytes()
        for binding in ({'sha256_file_bytes': hashlib.sha256(raw).hexdigest()}, {}, None):
            sidecar = json.dumps({'snapshot': binding, 'provisional': False}).encode()
            with self.subTest(binding=binding), self.assertRaises(SnapshotError):
                bind_preview_sidecar(sidecar, raw, present_reasoning(raw))

    @skipUnless(os.getenv('QUORUM_TEST_GENUINE_V4_SNAPSHOT') and os.getenv('QUORUM_TEST_GENUINE_V4_SIDECAR'),
                'original private v4 pair not supplied')
    def test_original_v4_binding_counts_claims_and_editorial_hold(self):
        raw = Path(os.environ['QUORUM_TEST_GENUINE_V4_SNAPSHOT']).read_bytes()
        sidecar = Path(os.environ['QUORUM_TEST_GENUINE_V4_SIDECAR']).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), GENUINE_V4_SHA256)
        self.assertEqual(hashlib.sha256(sidecar).hexdigest(), GENUINE_V4_SIDECAR_SHA256)
        result = bind_preview_sidecar(sidecar, raw, present_reasoning(raw))
        p = result['reasoning']
        self.assertEqual((len(p['stories']), p['roundup']['count'], len(p['trace']), len(p['errors'])), (1,26,235,0))
        claims = p['stories'][0]['claims']
        self.assertEqual(len(claims), 12)
        for status in ('confirmed', 'disputed', 'unverified'):
            self.assertEqual(sum(c['status'] == status for c in claims), 4)
        self.assertEqual(p['stories'][0]['rubric']['total'], 6)
        self.assertIn('has not passed independent impact review', ' '.join(result['preview']['warnings']))
        self.assertNotIn('corpus_as_of_utc', result['preview']['corpus_binding'])
        self.assertTrue(result['preview']['corpus_binding']['closed_edition'])
        self.assertFalse(result['preview']['published'])
        self.assertNotIn('api_keys', json.dumps(result['preview']))
        for altered in (sidecar+b'\n', sidecar.replace(b'false', b'true', 1)):
            with self.assertRaises(SnapshotError):bind_preview_sidecar(altered, raw, present_reasoning(raw))
        with self.assertRaises(SnapshotError):bind_preview_sidecar(sidecar, SAMPLE.read_bytes(), present_reasoning(SAMPLE.read_bytes()))
        for mutate in (lambda x:x.update(TEST_unknown=True),
                       lambda x:x['provenance'].update(model_calls=1675),
                       lambda x:x['stories'][0]['claims'][0]['evidence'][0].update(url='javascript:TEST')):
            bad=copy.deepcopy(p);mutate(bad)
            with self.assertRaises(SnapshotError):parse_reasoning(json.dumps(bad).encode())
        with self.assertRaises(SnapshotError):parse_snapshot(raw)
        self.assertEqual(Path(os.environ['QUORUM_TEST_GENUINE_V4_SNAPSHOT']).read_bytes(), raw)
        self.assertEqual(Path(os.environ['QUORUM_TEST_GENUINE_V4_SIDECAR']).read_bytes(), sidecar)
