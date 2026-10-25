"""Deterministic dispatch regressions; these are not sponsor integration evidence."""
import contextlib
import io
import sys
import unittest
from unittest.mock import patch

import checks


class ReadinessWorkflowTests(unittest.TestCase):
    def setUp(self):
        checks.RESULTS.clear()

    def test_doctor_never_probes_cursor_or_windows_editor(self):
        with patch.object(checks, 'run', return_value=(127, '')) as run, \
             patch.object(checks, 'cursor_acceptance') as acceptance, \
             patch('services.available_memory', return_value=8 * 1024**3), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            checks.doctor()
        acceptance.assert_not_called()
        self.assertNotIn('Cursor', output.getvalue())
        self.assertFalse(any(call.args[0][0] == 'powershell.exe' for call in run.call_args_list))

    def test_missing_legacy_evidence_does_not_change_normal_summary(self):
        def doctor():
            checks.emit('PASS', 'test tooling', 'unit-test result only')
        with patch.object(sys, 'argv', ['checks.py', 'doctor']), \
             patch.object(checks, 'load_config'), \
             patch.object(checks, 'doctor', side_effect=doctor), \
             patch.object(checks, 'cursor_history') as legacy, \
             patch.dict(checks.CFG, {'CURSOR_EXE': '/missing', 'CURSOR_ACCEPTANCE_FILE': '/missing'}), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(checks.main(), 0)
        legacy.assert_not_called()
        self.assertIn('BLOCKED=0 | NOT_TESTED=0', output.getvalue())

    def test_verify_preserves_sponsor_checks_without_inference(self):
        with patch.object(sys, 'argv', ['checks.py', 'verify']), \
             patch.object(checks, 'load_config'), \
             patch.object(checks, 'doctor'), \
             patch.object(checks, 'meterless') as meterless, \
             patch.object(checks, 'zetaris') as zetaris, \
             patch.object(checks, 'nemotron') as nemotron, \
             patch.object(checks, 'cursor_history') as legacy, \
             contextlib.redirect_stdout(io.StringIO()):
            checks.main()
        meterless.assert_called_once_with()
        zetaris.assert_called_once_with()
        nemotron.assert_called_once_with(False)
        legacy.assert_not_called()

    def test_historical_diagnostics_are_explicit_and_separate(self):
        def history():
            checks.emit('NOT_TESTED', 'Cursor historical acceptance', 'unit-test result only')
        with patch.object(sys, 'argv', ['checks.py', 'cursor-history']), \
             patch.object(checks, 'load_config'), \
             patch.object(checks, 'doctor') as doctor, \
             patch.object(checks, 'cursor_history', side_effect=history) as legacy, \
             patch.object(checks, 'meterless') as meterless, \
             patch.object(checks, 'zetaris') as zetaris, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(checks.main(), 2)
        legacy.assert_called_once_with()
        doctor.assert_not_called()
        meterless.assert_not_called()
        zetaris.assert_not_called()


if __name__ == '__main__':
    unittest.main()
