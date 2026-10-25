"""Secret checks distinguish detector source from actual secret-shaped payloads."""
import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('package_docs',Path(__file__).with_name('prepare_submission_docs.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class PackagePrivacyTests(unittest.TestCase):
    def test_security_detector_source_is_not_a_private_key(self):
        marker=b'-----BEGIN '
        text=b're.compile('+repr(marker+br'[A-Z ]*PRIVATE KEY').encode()+b')'
        self.assertFalse(module.contains_secret(text))
    def test_complete_headers_and_tokens_are_rejected(self):
        begin=b'-----BEGIN '
        for kind in (b'',b'RSA ',b'EC ',b'OPENSSH '):
            self.assertTrue(module.contains_secret(b'{"config":"'+begin+kind+b'PRIVATE KEY'+b'-----"}'))
        self.assertTrue(module.contains_secret(b'nvapi-'+b'TEST'*6))
        self.assertTrue(module.contains_secret(b'Bearer '+b'TEST'*6))
