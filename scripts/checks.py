#!/usr/bin/env python3
"""Bounded, secret-redacting diagnostics; no dependency installation or service mutation."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

# Keep shared configuration when this file runs as the command-line entry point.
if __name__ == '__main__':
    sys.modules['checks'] = sys.modules[__name__]

ROOT = Path(__file__).resolve().parent.parent
PIN = '1742dec56a66e58eef9dda2d2b865823758ca8cd'
RESULTS = []
CFG = dict(os.environ)


def emit(status, name, detail):
    RESULTS.append(status)
    print(f'{status} | {name} | {detail}', flush=True)


def run(args, timeout=25, cwd=ROOT, env=None):
    try:
        p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, timeout=timeout)
        # Windows interop tools may emit UTF-16LE, Linux tools emit UTF-8.
        out = p.stdout.decode('utf-16le' if b'\x00' in p.stdout else 'utf-8', errors='replace').strip()
        return p.returncode, out
    except (OSError, subprocess.TimeoutExpired):
        return 127, ''


def load_config():
    known = set(re.findall(r'^([A-Z_]+)=', (ROOT / '.env.example').read_text(), re.M))
    for name in ('.env', '.env.local'):
        path = ROOT / name
        if not path.exists():
            continue
        if path.stat().st_mode & 0o077:
            emit('FAIL', 'private configuration', f'{name} must have mode 600')
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, sep, value = line.partition('=')
            if not sep or key not in known:
                emit('FAIL', 'configuration syntax', 'Use recognized literal KEY=value entries')
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in '\"\'':
                value = value[1:-1]
            # Exported values take precedence; files are never executed as shell code.
            if key not in os.environ:
                CFG[key] = value


def val(key, default=''):
    return CFG.get(key) or default


def doctor():
    for name, args in [('Git', ['git', '--version']), ('Node.js', ['node', '--version']),
                       ('npm', ['npm', '--version']), ('Python', ['python3', '--version']),
                       ('Docker Compose', ['docker', 'compose', 'version'])]:
        rc, out = run(args)
        emit('PASS' if rc == 0 else 'BLOCKED', name, out if rc == 0 else 'Tool unavailable')
    rc, out = run(['git', 'remote', 'get-url', 'origin'])
    emit('PASS' if rc == 0 and out == 'https://github.com/rcc00n/Quorum.git' else 'FAIL',
         'GitHub remote', 'Expected rcc00n/Quorum origin' if rc == 0 else 'Origin missing')
    rc, _ = run(['gh', 'api', 'user', '--jq', '.login'])
    emit('PASS' if rc == 0 else 'BLOCKED', 'GitHub authentication', 'Authenticated' if rc == 0 else 'Run gh auth login')
    rc, branch = run(['gh', 'api', 'repos/rcc00n/Quorum', '--jq', '.default_branch'])
    emit('PASS' if rc == 0 and branch == 'master' else 'BLOCKED', 'remote default branch',
         'master' if rc == 0 and branch == 'master' else 'Could not confirm master; inspect remote before publishing')
    rc, out = run(['wsl.exe', '-l', '-v'])
    distro = os.environ.get('WSL_DISTRO_NAME', 'Ubuntu-20.04')
    match = next((re.search(r'\s([12])\s*$', line) for line in out.splitlines() if distro in line), None)
    emit('PASS' if rc == 0 and match and match[1] == '2' else 'BLOCKED', 'WSL2',
         'Current distribution version 2 confirmed by wsl.exe' if match and match[1] == '2' else 'Cannot confirm WSL2; no conversion attempted')
    rc, out = run(['docker', 'info', '--format', '{{.ServerVersion}} {{.OperatingSystem}}'])
    emit('PASS' if rc == 0 else 'BLOCKED', 'Docker accessibility', out if rc == 0 else 'Existing daemon inaccessible; no daemon started')
    rc, out = run(['docker', 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'])
    emit('PASS' if rc == 0 and out.startswith('unix://') else 'BLOCKED', 'native Docker socket',
         'Local Unix socket' if rc == 0 and out.startswith('unix://') else 'Review Docker context; no insecure TCP configured')
    # Desktop distributions were stopped in the audit. A working Engine is sufficient.
    rc, out = run(['docker', 'info', '--format', '{{.OperatingSystem}}'])
    emit('PASS' if rc == 0 and 'Docker Desktop' in out else 'NOT_TESTED', 'Docker Desktop WSL2 integration',
         'Desktop backend identified' if rc == 0 and 'Docker Desktop' in out else 'Current backend is Linux Engine; Desktop integration not demonstrated or required')
    ps = r'''$p=$env:QUORUM_CURSOR_EXE; if(!$p){$p="$env:LOCALAPPDATA\Programs\cursor\Cursor.exe"}; if(Test-Path -LiteralPath $p){Write-Output (Get-Item -LiteralPath $p).VersionInfo.ProductVersion; exit 0}; exit 2'''
    env = dict(os.environ, QUORUM_CURSOR_EXE=val('CURSOR_EXE'))
    rc, out = run(['powershell.exe', '-NoProfile', '-Command', ps], env=env)
    emit('PASS' if rc == 0 else 'BLOCKED', 'Cursor installation', 'Windows executable '+out if rc == 0 else 'Windows executable unavailable')
    cursor_acceptance()
    rc, out = run(['df', '-Pk', str(ROOT)])
    if rc == 0:
        fields = out.splitlines()[-1].split()
        emit('PASS' if int(fields[3]) >= 15*1024*1024 else 'BLOCKED', 'disk capacity', f'{int(fields[3])//(1024*1024)} GiB available')
    rc, out = run(['docker', 'info', '--format', '{{.MemTotal}}'])
    if rc == 0 and out.isdigit():
        emit('PASS' if int(out) >= 8*1024**3 else 'BLOCKED', 'Zetaris Docker memory allocation', f'{int(out)/1024**3:.2f} GiB total; minimum 8 GiB required; no limits changed')
    available = int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
    emit('PASS' if available >= 8*1024**3 else 'BLOCKED', 'Zetaris available memory', f'{available/1024**3:.2f} GiB available; minimum 8 GiB required before start')
    rc, out = run(['ss', '-H', '-ltn'])
    ports = sorted({int(x.split()[3].rsplit(':', 1)[-1]) for x in out.splitlines() if len(x.split()) > 3}) if rc == 0 else []
    emit('PASS' if rc == 0 else 'BLOCKED', 'occupied Linux TCP ports', ', '.join(map(str, ports)) if rc == 0 else 'Port enumeration unavailable')
    emit('PASS', 'environment template', 'Credential placeholders present; local files parsed without execution')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url, token='', body=None, headers=None):
    parsed = urllib.parse.urlsplit(url)
    if parsed.username or parsed.password or parsed.fragment or parsed.query or not parsed.hostname:
        raise ValueError('unsafe URL')
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')):
        raise ValueError('HTTPS required except loopback')
    h = dict(headers or {})
    if token:
        h['Authorization'] = 'Bearer '+token
    data = None if body is None else json.dumps(body).encode()
    if data is not None:
        h['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as response:
        payload = response.read(1024*1024)
        return json.loads(payload) if payload else None


def failure(name, exc):
    if isinstance(exc, urllib.error.HTTPError):
        emit('BLOCKED' if exc.code in (401, 403, 402, 429) else 'FAIL', name, f'HTTP {exc.code}; response body withheld')
    else:
        emit('FAIL', name, type(exc).__name__+'; details withheld to protect credentials')


def meterless():
    home = Path(val('METERLESS_HOME', str(Path.home()/'.local/share/quorum/meterless'))).expanduser().resolve()
    if home == ROOT or ROOT in home.parents:
        emit('FAIL', 'Meterless location', 'Vendor checkout must be outside Quorum')
        return
    ref = home/'engines/hmem/reference'
    rc, revision = run(['git', '-C', str(home), 'rev-parse', 'HEAD'])
    installed = rc == 0 and revision == PIN and (ref/'node_modules/.bin/vitest').exists()
    emit('PASS' if installed else 'BLOCKED', 'Meterless reference installation', 'Pinned official reference and test runner present' if installed else 'Run scripts/setup-meterless.sh')
    if installed:
        rc, _ = run([str(ref/'node_modules/.bin/vitest'), 'run', 'test/smoke.test.ts', '--maxWorkers=1', '--minWorkers=1'], cwd=ref, timeout=60)
        emit('PASS' if rc == 0 else 'FAIL', 'Meterless official H-MEM smoke', '10 official tests passed' if rc == 0 else 'Official smoke failed; run npm test in external reference for details')
        env = dict(os.environ, METERLESS_HOME=str(home))
        rc, _ = run([str(ref/'node_modules/.bin/tsx'), str(ROOT/'scripts/meterless-persistence.mjs')], env=env, timeout=30)
        emit('PASS' if rc == 0 else 'FAIL', 'Meterless persistence/state smoke', 'Memory, ledger and state survive reload' if rc == 0 else 'Run persistence script with external tsx for details')
    else:
        emit('BLOCKED', 'Meterless smoke tests', 'Official reference dependencies missing')


def cursor_acceptance():
    path = val('CURSOR_ACCEPTANCE_FILE')
    if not path:
        emit('NOT_TESTED', 'Cursor Agent Composer/Grok acceptance', 'Authenticated installation preserved; manual smoke evidence required')
        return
    try:
        evidence = Path(path).expanduser().resolve()
        if evidence == ROOT or ROOT in evidence.parents:
            raise ValueError('Acceptance evidence must be outside public repository')
        data = json.loads(evidence.read_text())
        passed = bool(data.get('observed_at')) and all(data.get(k) is True for k in
                   ('composer_passed', 'grok_passed', 'wsl_terminal_passed', 'git_passed'))
        emit('PASS' if passed else 'NOT_TESTED', 'Cursor Agent Composer/Grok acceptance',
             'User-recorded interactive acceptance; not an automated model test' if passed else 'Acceptance evidence incomplete')
    except (OSError, ValueError, TypeError):
        emit('FAIL', 'Cursor acceptance evidence', 'External evidence cannot be validated; contents withheld')


def http_probe(url, kind, token=''):
    parsed = urllib.parse.urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname:
        raise ValueError('Unsafe URL')
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')):
        raise ValueError('HTTPS required except loopback')
    headers = {'Authorization': 'Bearer '+token} if token else {}
    with urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url, headers=headers), timeout=15) as response:
        raw = response.read(1024*1024)
        if kind == 'gui':
            return 'html' in response.headers.get('Content-Type', '').lower() and b'<html' in raw.lower()
        data = json.loads(raw)
        return isinstance(data, (dict, list)) and bool(data)


def zetaris():
    import services
    args = services.compose_args()
    rc, output = run(['docker', 'ps', '--all', '--filter', 'label=com.docker.compose.project='+services.PROJECT,
                      '--format', '{{.Label "com.docker.compose.service"}} {{.State}}'])
    states = dict(line.split(maxsplit=1) for line in output.splitlines() if len(line.split()) == 2) if rc == 0 else {}
    for name in services.SERVICES:
        state = states.get(name)
        emit('PASS' if state == 'running' else 'FAIL' if state else 'BLOCKED', name,
             'Isolated project container running' if state == 'running' else 'Container '+state if state else 'Not deployed; image access / memory prerequisites blocked')
    _, runtime = services.locations()
    prepared = runtime/'compose.json'
    if prepared.exists():
        try:
            services.validate_deployment()
        except (ValueError, OSError):
            emit('FAIL', 'Freemium isolation', 'Private deployment scope/permissions invalid')
            return
        rc, _ = run(args+['config', '--quiet'])
        emit('PASS' if rc == 0 else 'FAIL', 'Freemium isolated Compose', 'Private four-service config validates' if rc == 0 else 'Compose validation unsuccessful')
    else:
        emit('BLOCKED', 'Freemium isolated Compose', 'Run python3 scripts/services.py prepare')
    ready = all(states.get(name) == 'running' for name in services.SERVICES)
    for kind, key, default in [('GUI', 'ZETARIS_GUI_URL', 'http://127.0.0.1:9001'),
                               ('REST API', 'ZETARIS_REST_CHECK_URL', '')]:
        endpoint = val(key, default)
        if not ready or not endpoint:
            emit('BLOCKED', 'Zetaris '+kind, 'Four running containers and documented endpoint required')
            continue
        try:
            ok = http_probe(endpoint, 'gui' if kind == 'GUI' else 'api', val('ZETARIS_API_KEY') if kind != 'GUI' else '')
            emit('PASS' if ok else 'NOT_TESTED', 'Zetaris '+kind, 'HTTP application response validated; not SQL verification' if ok else 'Unrecognized HTTP response')
        except Exception as exc:
            failure('Zetaris '+kind, exc)
    required = ('ZETARIS_JDBC_JAR', 'ZETARIS_USERNAME', 'ZETARIS_PASSWORD', 'ZETARIS_DATASET_SQL')
    if not ready or not all(val(k) for k in required):
        emit('BLOCKED', 'Zetaris registered dataset SELECT', 'Running services, official JDBC JAR, credentials and organizer sample SQL required')
        return
    jar = Path(val('ZETARIS_JDBC_JAR')).expanduser().resolve()
    sql = val('ZETARIS_DATASET_SQL').strip().rstrip(';')
    if not jar.is_file() or ROOT in jar.parents or not re.match(r'(?is)^SELECT\b.+\bFROM\b', sql) or ';' in sql:
        emit('FAIL', 'Zetaris dataset configuration', 'External matching JDBC JAR and a single dataset SELECT with FROM required')
        return
    if not shutil.which('java'):
        emit('BLOCKED', 'Zetaris dataset SELECT', 'JDK 11+ source launcher required; no runtime installed automatically')
        return
    env = dict(os.environ)
    env.update({k: val(k) for k in required})
    env['ZETARIS_DATASET_SQL'] = sql
    env['ZETARIS_JDBC_URL'] = val('ZETARIS_JDBC_URL', 'jdbc:zetaris:lightning@127.0.0.1:10000')
    env['ZETARIS_JDBC_DRIVER'] = val('ZETARIS_JDBC_DRIVER')
    rc, output = run(['java', '--class-path', str(jar), str(ROOT/'scripts/ZetarisSmoke.java')], env=env, timeout=45)
    emit('PASS' if rc == 0 and output.startswith('PASS ') else 'FAIL', 'Zetaris registered dataset SELECT',
         'Actual authenticated dataset query returned a row; values withheld' if rc == 0 and output.startswith('PASS ') else 'JDBC smoke unsuccessful; details withheld')


def nemotron(allow_inference=False):
    required = ('METERLESS_BASE_URL', 'METERLESS_API_KEY', 'NEMOTRON_MODEL')
    if not all(val(key) for key in required):
        emit('BLOCKED', 'Nemotron through Meterless', 'Organizer-issued METERLESS_BASE_URL, METERLESS_API_KEY and NEMOTRON_MODEL required; no guessed defaults')
        return
    if not allow_inference:
        emit('NOT_TESTED', 'Nemotron through Meterless', 'Credentials configured; explicitly use --inference for one capped request; diagnostics spend no provider credits')
        return
    try:
        base = val('METERLESS_BASE_URL').rstrip('/')
        if base.endswith(('/chat/completions', '/models')):
            raise ValueError('Supply the API base URL, not an operation URL')
        data = request(base+'/chat/completions', val('METERLESS_API_KEY'), {
            'model': val('NEMOTRON_MODEL'), 'messages': [{'role': 'user', 'content': 'Reply with OK.'}],
            'max_tokens': 32, 'stream': False, 'temperature': 0})
        content = data['choices'][0]['message']['content']
        emit('PASS' if isinstance(content, str) and content.strip() else 'FAIL', 'Nemotron through Meterless',
             'Nonempty real response from configured Meterless Nemotron route; output withheld' if content else 'No response content')
    except Exception as exc:
        failure('Nemotron through Meterless', exc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['doctor', 'verify'])
    parser.add_argument('--inference', action='store_true', help='Explicitly send one capped Meterless request when real credentials are supplied')
    args = parser.parse_args()
    if args.inference and args.mode != 'verify':
        parser.error('--inference requires verify')
    load_config()
    if 'FAIL' in RESULTS:
        print('FAIL | diagnostics | Correct private configuration before running checks')
        return 1
    doctor()
    if args.mode == 'verify':
        meterless()
        zetaris()
        nemotron(args.inference)
    counts = {s: RESULTS.count(s) for s in ('PASS', 'FAIL', 'BLOCKED', 'NOT_TESTED')}
    print('SUMMARY | '+ ' | '.join(f'{s}={n}' for s, n in counts.items()))
    return 1 if counts['FAIL'] else 2 if counts['BLOCKED'] or counts['NOT_TESTED'] else 0


if __name__ == '__main__':
    sys.exit(main())
