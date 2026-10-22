#!/usr/bin/env python3
"""Prepare and control only Quorum's isolated four-service Freemium deployment."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import checks

PIN = '9dd4fe943afebca6b204b6ed5eccdca91b831e6c'
PROJECT = 'quorum-zetaris'
SERVICES = ('zetaris-db', 'zetaris-server', 'zetaris-api', 'zetaris-gui')


def locations():
    vendor = Path(checks.val('ZETARIS_FREEMIUM_HOME', str(Path.home()/'.local/share/quorum/zetaris-freemium'))).expanduser().resolve()
    runtime = Path(checks.val('ZETARIS_RUNTIME_DIR', str(Path.home()/'.local/share/quorum/zetaris-runtime'))).expanduser().resolve()
    for path in (vendor, runtime):
        if path == checks.ROOT or checks.ROOT in path.parents:
            raise ValueError('Vendor and runtime must be outside Quorum')
    return vendor, runtime


def compose_args():
    _, runtime = locations()
    return ['docker', 'compose', '-p', PROJECT, '--project-directory', str(runtime), '-f', str(runtime/'compose.json')]


def validate_deployment():
    _, runtime = locations()
    path = runtime/'compose.json'
    config = json.loads(path.read_text())
    if path.stat().st_mode & 0o077 or set(config.get('services', {})) != set(SERVICES) or config.get('name') != PROJECT:
        raise ValueError('Private deployment permissions or service scope invalid')
    expected_ports = {'zetaris-server': 10000, 'zetaris-api': 8888, 'zetaris-gui': 9001}
    for name, service in config['services'].items():
        ports = service.get('ports', [])
        if name == 'zetaris-db' and ports:
            raise ValueError('Database must not publish a host port')
        if name in expected_ports and (len(ports) != 1 or ports[0].get('host_ip') != '127.0.0.1' or
                                      ports[0].get('target') != expected_ports[name] or
                                      str(ports[0].get('published')) != str(expected_ports[name])):
            raise ValueError('Unexpected host port binding')


def memory_ready():
    rc, memory = checks.run(['docker', 'info', '--format', '{{.MemTotal}}'])
    available = int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
    return rc == 0 and memory.isdigit() and int(memory) >= 8*1024**3 and available >= 8*1024**3


def prepare():
    vendor, runtime = locations()
    rc, rev = checks.run(['git', '-C', str(vendor), 'rev-parse', 'HEAD'])
    if rc or rev != PIN:
        print('BLOCKED | Freemium preparation | Expected external pinned official checkout missing')
        return 2
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(runtime, 0o700)
    target = runtime/'compose.json'
    if target.exists():
        validate_deployment()
        print('PASS | Freemium preparation | Existing private configuration preserved')
        return 0
    # Resolve upstream without printing its .env or unrelated service settings.
    rc, raw = checks.run(['docker', 'compose', '-f', str(vendor/'docker-compose.yml'), 'config', '--format', 'json'], cwd=vendor)
    if rc:
        print('BLOCKED | Freemium preparation | Upstream Compose cannot be resolved')
        return 2
    upstream = json.loads(raw)['services']
    selected = {name: upstream[name] for name in SERVICES}
    password = secrets.token_hex(32)
    # Fresh isolated PostgreSQL role also makes upstream init grants to postgres valid.
    selected['zetaris-db']['environment'].update(POSTGRES_USER='postgres', POSTGRES_PASSWORD=password)
    selected['zetaris-db']['command'] = ['postgres']  # Do not log every SQL statement.
    for name, service in selected.items():
        service['restart'] = 'unless-stopped'
        service.pop('ports', None)
        service.pop('networks', None)
        for key in list(service.get('environment', {})):
            if key in ('METASTORE_JDBC_URL', 'METASTORE_DATABASE_URL', 'AUDIT_LOG_JDBC_URL', 'AUDIT_LOG_DATABASE_URL'):
                database = 'audit' if key.startswith('AUDIT') else 'metastore'
                service['environment'][key] = f'jdbc:postgresql://zetaris-db:5432/{database}?user=postgres&password={password}'
        for mount in service.get('volumes', []):
            destination = mount['target']
            if destination.startswith('/var/lib/postgresql'):
                source = runtime/'pgdata'
            elif destination == '/home/zetaris/data':
                source = runtime/'customer_data'
            elif destination.endswith('/tokens'):
                source = runtime/'tokens'
            elif destination.endswith('/passwordkeys'):
                source = runtime/'passwordkeys'
            else:
                continue  # Read-only vendor initialization/start scripts.
            source.mkdir(parents=True, exist_ok=True, mode=0o700)
            mount['source'] = str(source)
            if destination.endswith('/passwordkeys'):
                mount['read_only'] = True
            mount.pop('bind', None)
        for mount in service.get('volumes', []):
            if mount['source'].startswith(str(vendor)):
                mount['read_only'] = True
    for name, port in (('zetaris-server', 10000), ('zetaris-api', 8888), ('zetaris-gui', 9001)):
        selected[name]['ports'] = [{'target': port, 'published': str(port), 'host_ip': '127.0.0.1', 'protocol': 'tcp'}]
    selected['zetaris-api']['environment']['ALLOWED_ORIGINS'] = 'http://localhost:9001;http://127.0.0.1:9001'
    # Replace the public upstream test encryption keys with private per-install RSA DER keys.
    private = runtime/'passwordkeys/private_key.der'
    public = runtime/'passwordkeys/public_key.der'
    if not private.exists():
        rawkey = private.with_suffix('.temporary.der')
        try:
            subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048', '-outform', 'DER', '-out', str(rawkey)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Upstream Java key is PKCS8 DER, not traditional PKCS1 DER.
            subprocess.run(['openssl', 'pkcs8', '-topk8', '-nocrypt', '-inform', 'DER', '-in', str(rawkey), '-outform', 'DER', '-out', str(private)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        finally:
            rawkey.unlink(missing_ok=True)
    if not public.exists():
        subprocess.run(['openssl', 'pkey', '-inform', 'DER', '-in', str(private), '-pubout', '-outform', 'DER', '-out', str(public)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.chmod(private, 0o600)
    os.chmod(public, 0o600)
    # Upstream startup recursively makes data world-writable. Restrict this to the owner instead.
    startup = (vendor/'lightning/server/start.sh').read_text().replace('chmod -R 777', 'chmod -R u+rwX,go-rwx')
    startfile = runtime/'server-start.sh'
    startfile.write_text(startup)
    os.chmod(startfile, 0o700)
    for mount in selected['zetaris-server']['volumes']:
        if mount['target'] == '/home/zetaris/lightning/bin/start.sh':
            mount['source'] = str(startfile)
    with open(target, 'x', opener=lambda path, flags: os.open(path, flags, 0o600)) as handle:
        json.dump({'name': PROJECT, 'services': selected}, handle, indent=2)
    print('PASS | Freemium preparation | Four services isolated; DB unpublished; only localhost 9001/8888/10000')
    return 0


def main():
    checks.load_config()
    if 'FAIL' in checks.RESULTS:
        return 1
    action = sys.argv[1]
    if action == 'prepare':
        return prepare()
    _, runtime = locations()
    if not (runtime/'compose.json').exists():
        print('BLOCKED | Zetaris services | Run python3 scripts/services.py prepare first')
        return 2
    validate_deployment()
    args = compose_args()
    rc, _ = checks.run(args+['config', '--quiet'])
    if rc:
        print('FAIL | Zetaris services | Private Compose validation unsuccessful')
        return 1
    if action == 'start':
        if not memory_ready():
            print('BLOCKED | Zetaris services | Require 8 GiB allocated to Docker and currently available; no WSL limit changed')
            return 2
        command = ['up', '-d', '--pull', 'never', '--no-build', *SERVICES]
    elif action == 'stop':
        command = ['stop', *SERVICES]
    else:
        raise ValueError('Unsupported action')
    rc, _ = checks.run(args+command, timeout=60)
    print(('PASS' if rc == 0 else 'BLOCKED')+' | Zetaris services | '+('Start requested; verify readiness separately' if action == 'start' else 'Isolated project stopped; data retained'))
    return 0 if rc == 0 else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, subprocess.SubprocessError):
        print('FAIL | Zetaris services | Preparation/control error; inspect private configuration locally')
        sys.exit(1)
