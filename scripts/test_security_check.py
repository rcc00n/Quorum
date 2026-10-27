"""Synthetic Git indexes verify secret aliases without reading private configuration."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCANNER = Path(__file__).with_name('security-check.py').resolve()

class SecretAliasTests(unittest.TestCase):
    def scan(self, content):
        with tempfile.TemporaryDirectory(prefix='quorum-index-') as temp:
            root = Path(temp)
            subprocess.run(['git', 'init', '-q', temp], check=True)
            (root/'settings.conf').write_text(content)
            subprocess.run(['git', 'add', 'settings.conf'], cwd=root, check=True)
            return subprocess.run([sys.executable, str(SCANNER)], cwd=root, capture_output=True, text=True)

    def test_token_aliases_and_numbered_model_keys_are_blocked_without_printing_values(self):
        value = 'TEST' + 'x' * 32
        for key in ('METERLESS_TOKEN', 'METERLESS_RUNTIME_TOKEN', 'MODEL_API_KEY_2', 'ACCESS_TOKEN'):
            with self.subTest(key=key):
                result = self.scan(f'{key}={value}\n')
                self.assertEqual(result.returncode, 1)
                self.assertNotIn(value, result.stdout + result.stderr)
                self.assertIn('settings.conf', result.stdout)

    def test_blank_and_documented_placeholder_values_remain_valid(self):
        result = self.scan('METERLESS_TOKEN=\nMODEL_API_KEY_2=<private-key>\n')
        self.assertEqual(result.returncode, 0)


class ReviewedAssetTests(unittest.TestCase):
    def test_only_exact_reviewed_png_bytes_are_permitted(self):
        import hashlib
        import importlib.util
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('index_scanner', SCANNER)
        scanner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scanner)
        image = b'\x89PNG\r\n\x1a\nTEST-only-image-data'
        name = 'docs/reviews/TEST/public.png'
        with patch.dict(scanner.REVIEWED_IMAGES, {name: hashlib.sha256(image).hexdigest()}, clear=True):
            self.assertTrue(scanner.approved_review_image(name, image))
            self.assertFalse(scanner.approved_review_image(name, image + b'changed'))
            self.assertFalse(scanner.approved_review_image('private.png', image))
            self.assertFalse(scanner.approved_review_image(name, b'not a PNG'))
