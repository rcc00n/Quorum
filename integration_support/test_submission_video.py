"""Final-edit guards do not read private originals or start an encoder."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('edit',Path(__file__).with_name('build_submission_video.py'));edit=importlib.util.module_from_spec(spec);spec.loader.exec_module(edit)
class SubmissionEditTests(unittest.TestCase):
    def test_captions_cover_exact_timeline_without_overlap(self):
        cues=edit.timeline();self.assertEqual(cues[0]['start'],0);self.assertEqual(cues[-1]['end'],222)
        for left,right in zip(cues,cues[1:]):self.assertAlmostEqual(left['end'],right['start'])
        for cue in cues:self.assertLess(cue['start'],cue['end'])
        self.assertIn('zero featured stories',' '.join(c['text'] for c in cues))
        self.assertIn('configuration digest discrepancy',' '.join(c['text'] for c in cues))
    def test_all_four_modes_have_explicit_authenticated_scenes(self):
        scenes=[source[1] for _,source,_ in edit.PLAN if source[0]=='still']
        self.assertTrue({125,140,155,162}<=set(scenes))
    def test_existing_or_repository_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(ValueError):edit.validate_output(root)
            (root/'.git').mkdir()
            with self.assertRaises(ValueError):edit.validate_output(root/'new')
        with self.assertRaises(ValueError):edit.validate_output(Path('relative'))
