#!/usr/bin/env python3
"""Control only an explicitly configured external official Zetaris bundle."""
from pathlib import Path
import sys
import checks


def main():
    checks.load_config()
    if 'FAIL' in checks.RESULTS:
        return 1
    raw = checks.val('ZETARIS_BUNDLE_DIR')
    if not raw:
        print('BLOCKED | Zetaris services | Set ZETARIS_BUNDLE_DIR to the official external bundle')
        return 2
    directory = Path(raw).expanduser().resolve()
    if not Path(raw).expanduser().is_absolute() or directory == checks.ROOT or checks.ROOT in directory.parents:
        print('FAIL | Zetaris services | Bundle must be an absolute path outside Quorum')
        return 1
    compose = directory/'docker-compose.yml'
    if not compose.is_file() or not (directory/'.env').is_file():
        print('BLOCKED | Zetaris services | Matching official docker-compose.yml and private .env required')
        return 2
    if (directory/'.env').stat().st_mode & 0o077:
        print('FAIL | Zetaris services | Set bundle .env permissions to 600')
        return 1
    args = ['docker', 'compose', '--project-directory', str(directory), '-f', str(compose)]
    rc, _ = checks.run(args+['config', '--quiet'], cwd=directory)
    if rc:
        print('FAIL | Zetaris services | Compose validation failed; output withheld')
        return 1
    action = sys.argv[1]
    if action == 'start':
        rc, memory = checks.run(['docker', 'info', '--format', '{{.MemTotal}}'])
        available = int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
        if rc or not memory.isdigit() or int(memory) < 6*1024**3 or available < 6*1024**3:
            print('BLOCKED | Zetaris services | At least 6 GiB allocated and currently available required; 8 GiB recommended')
            return 2
        # Enforce vendor prerequisites. Do not fetch images automatically.
        if not (directory/'preflight.sh').is_file():
            print('BLOCKED | Zetaris services | Official bundle preflight.sh missing')
            return 2
        rc, _ = checks.run(['bash', './preflight.sh'], cwd=directory, timeout=60)
        if rc:
            print('BLOCKED | Zetaris services | Official preflight unsuccessful; review privately in bundle directory')
            return 2
        command = ['up', '-d', '--pull', 'never', '--no-build']
    else:
        command = ['stop']
    # Suppress service output because vendor configuration may include secrets.
    rc, _ = checks.run(args+command, cwd=directory, timeout=120)
    print(('PASS' if rc == 0 else 'FAIL')+' | Zetaris services | '+('Start requested; run verify-all.sh for readiness' if action == 'start' else 'Stopped; volumes retained'))
    return 0 if rc == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
