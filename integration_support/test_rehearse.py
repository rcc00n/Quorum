"""Pure conflict-safety cases; the actual pinned rehearsal is verified separately."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('rehearse',Path(__file__).with_name('rehearse.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class RehearsalTests(unittest.TestCase):
    def test_additive_union_preserves_both_owner_rows(self):
        text='same\n<<<<<<< HEAD\n| 2026-10-24 | OWNER A | decision | why |\n=======\n| 2026-10-24 | OWNER B | decision | why |\n>>>>>>> branch\ntail\n'
        result=module.union_conflict(text)
        self.assertIn('OWNER A',result);self.assertIn('OWNER B',result)
        self.assertNotIn('<<<<<<<',result);self.assertTrue(result.endswith('tail\n'))

    def test_conflicting_assignments_and_malformed_markers_fail_closed(self):
        self.assertEqual(module.assignments('KEY=one\nKEY=one\n'),{'KEY':'one'})
        with self.assertRaises(ValueError):module.assignments('KEY=one\nKEY=two\n')
        for text in ('<<<<<<< a\nmissing end\n','=======\n','>>>>>>> x\n'):
            with self.assertRaises(ValueError):module.union_conflict(text)

    def test_existing_destination_is_rejected_before_any_git_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):module.rehearse(d,d)
