import base64
import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('ssh_key', Path(__file__).with_name('install-ssh-key.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SSHKeyTests(unittest.TestCase):
    def setUp(self):
        blob = struct.pack('>I', 11) + b'ssh-ed25519' + struct.pack('>I', 32) + bytes(range(32))
        self.key = 'ssh-ed25519 ' + base64.b64encode(blob).decode() + ' TEST-key'
        self.fingerprint = 'SHA256:' + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip('=')

    def test_only_exact_complete_key_passes(self):
        self.assertEqual(module.checked_key(self.key, self.fingerprint)[0], self.key)
        for raw, expected in [(self.fingerprint, self.fingerprint), (self.key, 'SHA256:wrong'),
                              (self.key + '\n' + self.key, self.fingerprint), ('command="bad" ' + self.key, self.fingerprint)]:
            with self.assertRaises(ValueError):
                module.checked_key(raw, expected)

    def test_existing_access_backup_and_idempotency(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / '.ssh/authorized_keys'
            target.parent.mkdir()
            original = b'# owner key preserved verbatim\nssh-ed25519 AAAA OWNER-without-newline'
            target.write_bytes(original)
            backup = module.add_key(target, self.key, os.getuid(), os.getgid())
            self.assertEqual(backup.read_bytes(), original)
            self.assertTrue(target.read_bytes().startswith(original + b'\n'))
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(target.parent.stat().st_mode & 0o777, 0o700)
            before = target.read_bytes()
            self.assertIsNone(module.add_key(target, self.key, os.getuid(), os.getgid()))
            self.assertEqual(target.read_bytes(), before)

    def test_symlink_never_overwrites_other_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            other = root / 'other'
            other.write_text('keep')
            link = root / 'authorized_keys'
            link.symlink_to(other)
            with self.assertRaises(ValueError):
                module.add_key(link, self.key, os.getuid(), os.getgid())
            self.assertEqual(other.read_text(), 'keep')
