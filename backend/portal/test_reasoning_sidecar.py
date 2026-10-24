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

    def test_private_and_extra_metadata_never_becomes_response_fields(self):
        self.sidecar['private_evidence']={'journal':'TEST-private-file'}
        self.sidecar['unused']='TEST-unused'
        result=self.load(self.sidecar)
        self.assertEqual(set(result['preview']['corpus_binding']), {'provisional','corpus_as_of_utc','sidecar_sha256'})
        self.assertNotIn('TEST-private-file',json.dumps(result))
        self.assertNotIn('TEST-unused',json.dumps(result))
        self.assertFalse(result['preview']['published'])
        self.assertEqual(result['reasoning'],json.loads(SAMPLE.read_bytes()))
