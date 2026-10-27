#!/usr/bin/env python3
"""Verify an Ed25519 public key before an additive, backed-up authorized_keys update."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import pwd
import shutil
import struct
import tempfile


def checked_key(raw, expected):
    lines = raw.strip().splitlines()
    if len(lines) != 1:
        raise ValueError('Exactly one complete public key is required')
    parts = lines[0].split()
    if len(parts) < 2 or parts[0] != 'ssh-ed25519':
        raise ValueError('Expected a complete ssh-ed25519 public key, not a fingerprint')
    blob = base64.b64decode(parts[1], validate=True)
    algorithm = b'ssh-ed25519'
    if blob != struct.pack('>I', len(algorithm)) + algorithm + struct.pack('>I', 32) + blob[-32:] or len(blob) != 51:
        raise ValueError('Invalid Ed25519 public key encoding')
    actual = 'SHA256:' + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip('=')
    if actual != expected:
        raise ValueError('Public key fingerprint mismatch; nothing changed')
    return ' '.join(parts), actual


def add_key(target, key, uid, gid):
    # DECISION(2026-10-26, rcc00n/Codex): preserve exact existing authorized_keys bytes and append only a verified key.
    # Why: teammate provisioning must never replace the owner's working SSH access or follow linked paths.
    target = Path(target)
    for item in (target, *target.parents):
        if item.is_symlink():
            raise ValueError('Linked SSH paths are refused')
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if target.exists() and (not target.is_file() or target.stat().st_nlink != 1):
        raise ValueError('Unsafe authorized_keys file')
    original = target.read_bytes() if target.exists() else b''
    identity = key.split()[:2]
    if any(line.split()[:2] == identity for line in original.decode().splitlines()):
        return None
    backup = None
    if target.exists():
        backup = target.with_name('authorized_keys.before-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        with backup.open('xb') as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(original)
            handle.flush()
            os.fsync(handle.fileno())
        os.chown(backup, uid, gid)
    fd, temporary = tempfile.mkstemp(prefix='.authorized_keys-', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(original + (b'\n' if original and not original.endswith(b'\n') else b'') + key.encode() + b'\n')
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), 0o600)
            os.fchown(handle.fileno(), uid, gid)
        os.replace(temporary, target)
        os.chown(target.parent, uid, gid)
        target.parent.chmod(0o700)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-key', type=Path, required=True)
    parser.add_argument('--fingerprint', required=True)
    parser.add_argument('--user', default='yelysei-deploy', help='Existing account; never creates users or grants sudo')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    key, fingerprint = checked_key(args.public_key.read_text(), args.fingerprint)
    account = pwd.getpwnam(args.user)
    target = Path(account.pw_dir) / '.ssh/authorized_keys'
    print(f'Verified {fingerprint}; account={args.user}; target={target}')
    if args.apply:
        if os.geteuid() != 0:
            raise ValueError('Root is required for authorized account provisioning')
        backup = add_key(target, key, account.pw_uid, account.pw_gid)
        print('Key installed or already present; existing access preserved; backup=' + str(backup))


if __name__ == '__main__':
    main()
