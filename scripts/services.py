#!/usr/bin/env python3
"""Control the externally installed official Zetaris platform, never legacy Freemium."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import checks

PROJECT = 'zetaris'
SERVICES = ('postgres', 'init', 'driver', 'api', 'ui', 'bootstrap')
RUNNING = ('postgres', 'driver', 'api', 'ui')
JOBS = ('init', 'bootstrap')


def platform_dir():
    path = Path(checks.val('ZETARIS_PLATFORM_DIR', str(Path.home()/'.local/share/quorum/zetaris-platform-bundle/zetaris-platform'))).expanduser().resolve()
    if path == checks.ROOT or checks.ROOT in path.parents:
        raise ValueError('Platform must be outside Quorum')
    return path


def bundle_env():
    # Preserve supplied values; never source a credential-bearing file as shell code.
    values = {}
    for line in (platform_dir()/'.env').read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if sep:
            values[key] = value.strip().strip('\"\'')
    return values


def command_env():
    root = platform_dir()
    env = dict(os.environ)
    env['COMPOSE_FILE'] = str(root/'docker-compose.yml')+':'+str(root/'compose.override.yml')
    env['COMPOSE_PROJECT_NAME'] = PROJECT
    env['COMPOSE_PROFILES'] = ''
    env['COMPOSE_ENV_FILES'] = str(root/'.env')
    # Bundled .env wins over unrelated exported settings; do not print the result.
    env.update(bundle_env())
    return env


def compose_args():
    return ['docker', 'compose', '-p', PROJECT]


def resolved_config():
    rc, raw = checks.run(compose_args()+['config', '--format', 'json'], cwd=platform_dir(), env=command_env())
    if rc:
        raise ValueError('Compose resolution failed')
    return json.loads(raw)


def validate_deployment():
    root = platform_dir()
    for filename in ('.env', 'compose.override.yml'):
        if (root/filename).stat().st_mode & 0o077:
            raise ValueError('Private platform configuration requires mode 600')
    data = resolved_config()
    if set(data.get('services', {})) != set(SERVICES):
        raise ValueError('Unexpected service/profile selection')
    for service in data['services'].values():
        for port in service.get('ports', []):
            if port.get('host_ip') != '127.0.0.1':
                raise ValueError('Platform ports must be loopback-only')
    supplied = bundle_env()
    if not all(supplied.get(key) for key in ('ZETARIS_ADMIN_EMAIL', 'ZETARIS_ADMIN_PASSWORD', 'ZETARIS_ADMIN_ORG')):
        raise ValueError('Administrator values missing; enter privately in bundled .env')
    return data


def prepare():
    root = platform_dir()
    for name in ('.env', 'docker-compose.yml', 'preflight.sh', 'verify.sh'):
        if not (root/name).is_file():
            print('BLOCKED | Zetaris platform | Official extracted bundle missing')
            return 2
    os.chmod(root, 0o700)
    os.chmod(root/'.env', 0o600)
    override = root/'compose.override.yml'
    if not override.exists():
        # Preserve every supplied .env value. Only restrict the UI's host exposure.
        data = resolved_without_override()
        ports = data['services']['ui']['ports']
        for port in ports:
            port['host_ip'] = '127.0.0.1'
            port['published'] = '${UI_PORT:-3000}'
        text = 'services:\n  ui:\n    ports: !override '+json.dumps(ports)+'\n'
        with open(override, 'x', opener=lambda p, flags: os.open(p, flags, 0o600)) as handle:
            handle.write(text)
    validate_deployment()
    print('PASS | Zetaris preparation | Official laptop settings/credentials preserved; six required services; loopback ports')
    return 0


def resolved_without_override():
    root = platform_dir()
    env = dict(os.environ, COMPOSE_PROFILES='', COMPOSE_PROJECT_NAME=PROJECT)
    env.update(bundle_env())
    rc, raw = checks.run(['docker', 'compose', '-f', str(root/'docker-compose.yml'), 'config', '--format', 'json'], cwd=root, env=env)
    if rc:
        raise ValueError('Official Compose resolution failed')
    return json.loads(raw)


def available_memory():
    return int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))*1024


def registry_configured():
    path = Path(os.environ.get('DOCKER_CONFIG', str(Path.home()/'.docker')))/'config.json'
    try:
        data = json.loads(path.read_text())
        return any('zetarishackathon.azurecr.io' in host for host in data.get('auths', {})) or bool(data.get('credHelpers', {}).get('zetarishackathon.azurecr.io'))
    except (OSError, ValueError):
        return False


def preflight():
    rc, output = checks.run(['bash', './preflight.sh'], cwd=platform_dir(), env=command_env(), timeout=60)
    # The official script's static status lines are safe; do not print arbitrary logs.
    for line in output.splitlines():
        if line.lstrip().startswith(('PASS ', 'WARN ', 'FAIL ')):
            print(line)
    print(('PASS' if rc == 0 else 'BLOCKED')+' | Official preflight.sh | '+('Required checks passed; heed memory warning' if rc == 0 else 'Resolve reported prerequisites before image pull/start'))
    return 0 if rc == 0 else 2


def main():
    checks.load_config()
    if 'FAIL' in checks.RESULTS:
        return 1
    action = sys.argv[1]
    if action == 'prepare':
        return prepare()
    validate_deployment()
    if action == 'preflight':
        return preflight()
    if action == 'start':
        rc, running = checks.run(compose_args()+['ps', '--status', 'running', '--services'], cwd=platform_dir(), env=command_env())
        if rc == 0 and set(RUNNING).issubset(set(running.split())):
            print('PASS | Zetaris start | Required long-running services already running; verify health separately')
            return 0
    if action in ('pull', 'start'):
        if not registry_configured():
            print('BLOCKED | Azure registry | Complete private Gateway authentication; no pull attempted')
            return 2
        if preflight():
            return 2
    if action == 'pull':
        command = ['pull', *SERVICES]
    elif action == 'start':
        # 2g driver + 1g API plus ~2 GiB working headroom; not a vendor hard minimum.
        if available_memory() < 5*1024**3:
            print('BLOCKED | Zetaris start | Less than 5 GiB currently available for default heaps/headroom; do not disrupt existing workloads')
            return 2
        if os.environ.get('WSL_DISTRO_NAME'):
            rc, free_kib = checks.run(['powershell.exe', '-NoProfile', '-Command', '(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory'], timeout=20)
            if rc or not free_kib.isdigit() or int(free_kib)*1024 < 4*1024**3:
                print('BLOCKED | Zetaris start | Need at least 4 GiB free Windows physical memory for stack and host headroom; no applications stopped')
                return 2
        data = resolved_config()
        for service in data['services'].values():
            for port in service.get('ports', []):
                published = int(port.get('published') or 0)
                if not published:
                    continue
                with socket.socket() as probe:
                    if probe.connect_ex(('127.0.0.1', published)) == 0:
                        print(f'BLOCKED | Zetaris start | Host port {published} occupied; existing service preserved')
                        return 2
        command = ['up', '-d', '--pull', 'never', '--no-build', *SERVICES]
    elif action == 'stop':
        command = ['stop', *SERVICES]
    elif action == 'verify':
        rc, _ = checks.run(['bash', './verify.sh'], cwd=platform_dir(), env=command_env(), timeout=120)
        _, active = checks.run(compose_args()+['ps', '-q', 'api'], cwd=platform_dir(), env=command_env())
        status = 'PASS' if rc == 0 else 'FAIL' if active else 'BLOCKED'
        print(status+' | Official verify.sh | '+('All bundled checks passed' if rc == 0 else 'Verification unsuccessful; raw credential-bearing output withheld'))
        return 0 if rc == 0 else 1 if active else 2
    else:
        raise ValueError('Unsupported action')
    rc, _ = checks.run(compose_args()+command, cwd=platform_dir(), env=command_env(), timeout=1800 if action == 'pull' else 900 if action == 'start' else 60)
    print(('PASS' if rc == 0 else 'BLOCKED')+' | Zetaris '+action+' | '+('Command completed; readiness must be verified separately' if rc == 0 else 'Command unsuccessful; no automatic retry; inspect privately'))
    return 0 if rc == 0 else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, subprocess.SubprocessError):
        print('FAIL | Zetaris platform control | Configuration/control error; inspect private bundle locally')
        sys.exit(1)
