"""Sidecar bindings are private input; output is a small untrusted-provenance projection."""
import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.test import SimpleTestCase
from .reasoning_preview import SAMPLE, load_preview
PRODUCER_SIDECAR = SAMPLE.with_name('snapshot.sample.sidecar.json')
from .snapshot_validation import MAX_BYTES, SnapshotError

class SidecarTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'TEST-sidecar.json'
        raw = SAMPLE.read_bytes()
        p = json.loads(raw)
        self.sidecar = dict(snapshot={key:p[key] for key in ('topic_id','edition_date','version','run_id','status')},
            provisional=True, corpus_as_of_utc=p['window']['start'], edition_window_utc=[p['window'][k] for k in ('start','end')])
        self.sidecar['snapshot'].update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        self.patch = patch.dict(os.environ, QUORUM_REASONING_PREVIEW_SIDECAR=str(self.path))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def load(self, value):
        self.path.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
        return load_preview(SAMPLE)

    def test_duplicate_keys_nonfinite_encoding_depth_and_size_rejected(self):
        for raw in (b'{"provisional":false,"provisional":true}',
                    b'{"producer":{"commit":"first","commit":"second"}}',
                    b'{"unused":NaN}', b'{"unused":Infinity}', b'{"unused":-Infinity}',
                    b'\xff', b'['*30+b'0'+b']'*30, b' '* (MAX_BYTES+1)):
            with self.subTest(length=len(raw)), self.assertRaises((SnapshotError, ValueError)):
                self.load(raw)

    def test_producer_shaped_fixture_binds_as_the_hand_built_sidecars_do(self):
        # The fixture is what reasoning/scripts/edition_sidecar.py writes (its builder and serializer), so a change on
        # either side of the sidecar contract fails here, not at the hand-over (2026-10-27, Anastasia / Claude Code).
        raw = PRODUCER_SIDECAR.read_bytes()
        sidecar = json.loads(raw)
        self.assertEqual(list(sidecar), ['snapshot', 'provisional', 'corpus_as_of_utc', 'edition_window_utc', 'producer'])
        self.assertEqual(list(sidecar['snapshot']), ['sha256', 'topic_id', 'edition_date', 'version', 'run_id', 'status', 'bytes'])
        self.assertEqual(list(sidecar['producer']), ['commit', 'config_sha256'])
        self.assertEqual(sidecar['snapshot']['sha256'], hashlib.sha256(SAMPLE.read_bytes()).hexdigest())
        result = self.load(raw)
        self.assertEqual(result['preview']['corpus_binding'],
                         {'provisional': True, 'corpus_as_of_utc': sidecar['corpus_as_of_utc'], 'sidecar_sha256': hashlib.sha256(raw).hexdigest()})

    def test_private_and_extra_metadata_never_becomes_response_fields(self):
        self.sidecar['private_evidence']={'journal':'TEST-private-file'}
        self.sidecar['unused']='TEST-unused'
        result=self.load(self.sidecar)
        self.assertEqual(set(result['preview']['corpus_binding']), {'provisional','corpus_as_of_utc','sidecar_sha256'})
        self.assertNotIn('TEST-private-file',json.dumps(result))
        self.assertNotIn('TEST-unused',json.dumps(result))
        self.assertFalse(result['preview']['published'])
        self.assertEqual(result['reasoning'],json.loads(SAMPLE.read_bytes()))

    def test_identity_types_size_and_chronology_fail_closed(self):
        mutations = [
            lambda x:x['snapshot'].update(version=float(x['snapshot']['version'])),
            lambda x:x['snapshot'].update(bytes=True),
            lambda x:x['snapshot'].update(bytes=x['snapshot']['bytes']+1),
            lambda x:x.update(corpus_as_of_utc='2026-10-23T03:53Z'),
            lambda x:x.update(corpus_as_of_utc='2026-10-20T03:53Z'),
            lambda x:x.update(corpus_as_of_utc='2026-02-30T03:53Z'),
            lambda x:x.update(corpus_as_of_utc='2026-10-22T03:53-06:00'),
            lambda x:x.update(snapshot=[]),
            lambda x:x.update(edition_window_utc=list(reversed(x['edition_window_utc']))),
        ]
        for index, mutate in enumerate(mutations):
            bad=copy.deepcopy(self.sidecar);mutate(bad)
            with self.subTest(index=index), self.assertRaises(SnapshotError):self.load(bad)
        for bad in ([],None,True):
            with self.subTest(root=bad), self.assertRaises(SnapshotError):self.load(bad)
        self.assertTrue(self.load(self.sidecar)['preview']['corpus_binding']['provisional'])
