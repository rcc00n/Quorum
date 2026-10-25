"""No private configuration or live service may be used by offline diagnostics."""
import contextlib
import io
import sys
import unittest
from unittest.mock import patch
import checks

class OfflineDiagnosticsTests(unittest.TestCase):
    def setUp(self):checks.RESULTS.clear()

    def test_offline_verify_never_loads_private_config_or_service_clients(self):
        with patch.object(sys,'argv',['checks.py','verify','--offline']), \
             patch.object(checks,'load_config') as config,patch.object(checks,'doctor') as doctor, \
             patch.object(checks,'meterless') as meterless,patch.object(checks,'zetaris') as zetaris, \
             patch.object(checks,'nemotron') as nemotron,patch.object(checks,'run',return_value=(0,'TEST tool')), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(checks.main(),2)
        for mocked in (config,doctor,meterless,zetaris,nemotron):mocked.assert_not_called()
        self.assertIn('BLOCKED=1',output.getvalue())

    def test_offline_doctor_missing_tools_stays_blocked_without_private_config(self):
        with patch.object(sys,'argv',['checks.py','doctor','--offline']), \
             patch.object(checks,'load_config') as config,patch.object(checks,'doctor') as live, \
             patch.object(checks,'run',return_value=(127,'TEST unavailable')), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(checks.main(),1)  # Git diff failure takes precedence over blocked tools.
        config.assert_not_called();live.assert_not_called()
        self.assertIn('FAIL=1',output.getvalue());self.assertIn('BLOCKED=5',output.getvalue())

    def test_offline_rejects_historical_checks_before_configuration_access(self):
        with patch.object(sys,'argv',['checks.py','cursor-history','--offline']), \
             patch.object(checks,'load_config') as config,patch.object(checks,'cursor_history') as history, \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:checks.main()
        self.assertEqual(error.exception.code,2);config.assert_not_called();history.assert_not_called()

    def test_offline_cannot_enable_inference(self):
        with patch.object(sys,'argv',['checks.py','verify','--offline','--inference']), \
             patch.object(checks,'load_config') as config,contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):checks.main()
        config.assert_not_called()
