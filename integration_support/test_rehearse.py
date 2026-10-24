"""Pure conflict-safety cases; the actual pinned rehearsal is verified separately."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
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


    def test_web_owned_profile_excludes_pending_owner_code(self):
        directory=Path(__file__).with_name('patches')
        selected=module.selected_patches(directory,profile='web-owned')
        self.assertEqual(len(selected),5)
        for path in selected:
            text=path.read_text()
            self.assertNotIn('diff --git a/reasoning/',text)
            self.assertNotIn('diff --git a/collectors/',text)
        self.assertTrue(any('build_integrity.py' in p.read_text() for p in selected))
        with self.assertRaises(ValueError):module.selected_patches(directory,True,'web-owned')
        with self.assertRaises(ValueError):module.selected_patches(directory,profile='unknown')
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):module.selected_patches(d,profile='web-owned')

    def test_stale_remote_heads_stop_before_creating_a_candidate(self):
        with tempfile.TemporaryDirectory() as d, patch.object(module,'git',return_value=SimpleNamespace(stdout='0'*40)) as git:
            with self.assertRaises(ValueError):module.rehearse(d,Path(d)/'new',profile='web-owned',require_current=True)
            self.assertFalse((Path(d)/'new').exists())
            self.assertFalse(any('worktree' in call.args for call in git.call_args_list))
