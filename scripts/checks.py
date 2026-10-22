#!/usr/bin/env python3
"""Bounded, secret-redacting diagnostics; no dependency installation or service mutation."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

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
    emit('NOT_TESTED', 'Cursor GUI / WSL terminal / Git', 'Interactive acceptance required; see docs/MANUAL_ACTIONS.md')
    rc, out = run(['df', '-Pk', str(ROOT)])
    if rc == 0:
        fields = out.splitlines()[-1].split()
        emit('PASS' if int(fields[3]) >= 15*1024*1024 else 'BLOCKED', 'disk capacity', f'{int(fields[3])//(1024*1024)} GiB available')
    rc, out = run(['docker', 'info', '--format', '{{.MemTotal}}'])
    if rc == 0 and out.isdigit():
        emit('PASS' if int(out) >= 6*1024**3 else 'BLOCKED', 'Docker memory allocation', f'{int(out)/1024**3:.1f} GiB total; check current free RAM before Zetaris startup')
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
    if not (val('METERLESS_BASE_URL') and val('METERLESS_RUNTIME_TOKEN')):
        emit('BLOCKED', 'Meterless inference runtime', 'Optional runtime URL/token absent; reference tests do not establish inference readiness')
    else:
        try:
            data = request(val('METERLESS_BASE_URL').rstrip('/')+'/models', val('METERLESS_RUNTIME_TOKEN'), headers={'meterless-app': 'quorum-setup'})
            valid = any(x.get('id', '').startswith('meterless/') for x in data.get('data', []))
            emit('PASS' if valid else 'FAIL', 'Meterless runtime discovery', 'Authenticated routing modes returned' if valid else 'No Meterless routing modes returned')
            emit('NOT_TESTED', 'Meterless inference', 'Discovery is not a completed inference')
        except Exception as exc:
            failure('Meterless runtime discovery', exc)


def zetaris():
    names = ['Zetaris connection/authentication', 'Zetaris database discovery', 'Zetaris SQL SELECT 1', 'Zetaris data source discovery']
    base, org = val('ZETARIS_BASE_URL').rstrip('/'), val('ZETARIS_ORG_ID')
    token = val('ZETARIS_API_KEY')
    if not (base and org and (token or (val('ZETARIS_USERNAME') and val('ZETARIS_PASSWORD')))):
        for name in names:
            emit('BLOCKED', name, 'Instance URL, numeric org ID and credential required')
    else:
        try:
            parsed = urllib.parse.urlsplit(base)
            if parsed.path or not org.isdigit():
                raise ValueError('origin and numeric org required')
            if not token:
                login = request(base+'/api/auth/login', body={'username': val('ZETARIS_USERNAME'), 'password': val('ZETARIS_PASSWORD')})
                token = next((login.get(k) for k in ('idToken', 'token', 'accessToken') if login.get(k)), '')
                if not isinstance(token, str) or not token:
                    raise ValueError('login returned no token')
            headers = {'X-Org-ID': org}
            data = request(base+'/api/proxy/lightning-database/databases', token, headers=headers)
            if not isinstance(data, list):
                raise ValueError('unexpected database response')
            emit('PASS', names[0], 'Authenticated database request succeeded')
            emit('PASS', names[1], f'{len(data)} visible databases; names withheld')
        except Exception as exc:
            failure(names[0], exc)
            for name in names[1:]:
                emit('BLOCKED', name, 'Connection/authentication prerequisite unsuccessful')
        else:
            body = {'sql': 'SELECT 1 AS one', 'limit': 1}
            if val('ZETARIS_ENGINE_ID'):
                body['engineId'] = val('ZETARIS_ENGINE_ID')
            try:
                data = request(base+'/api/proxy/sql-editor/sqls/run-query', token, body, headers)
                def has_one(obj):
                    if isinstance(obj, list):
                        return obj == [[1]] or obj == [{'one': 1}] or any(has_one(x) for x in obj)
                    if isinstance(obj, dict):
                        return any(has_one(obj[k]) for k in ('rows', 'data', 'results', 'result', 'records') if k in obj)
                    return False
                emit('PASS' if has_one(data) else 'NOT_TESTED', names[2], 'Actual result row contains 1' if has_one(data) else 'Response shape not validated; inspect privately in SQL Editor')
            except Exception as exc:
                failure(names[2], exc)
            try:
                discovery = dict(body, sql='SHOW DATASOURCES', limit=100)
                sources = request(base+'/api/proxy/sql-editor/sqls/run-query', token, discovery, headers)
                def rows_present(obj):
                    if isinstance(obj, dict):
                        return isinstance(obj.get('rows'), list) or any(rows_present(obj[k]) for k in ('data', 'results', 'result') if k in obj)
                    return False
                emit('PASS' if rows_present(sources) else 'NOT_TESTED', names[3],
                     'Official SHOW DATASOURCES returned structured rows; names withheld' if rows_present(sources) else 'Response shape not validated; inspect privately in SQL Editor')
            except Exception as exc:
                failure(names[3], exc)
    if val('ZETARIS_HEALTH_URL'):
        try:
            health = request(val('ZETARIS_HEALTH_URL'))
            healthy = isinstance(health, dict) and str(health.get('status', '')).lower() in ('up', 'ok', 'healthy')
            emit('PASS' if healthy else 'NOT_TESTED', 'Zetaris health endpoint', 'Explicit healthy status returned' if healthy else 'Successful response but health schema not validated')
        except Exception as exc:
            failure('Zetaris health endpoint', exc)
    else:
        emit('BLOCKED', 'Zetaris health endpoint', 'Exact supported endpoint not supplied; no endpoint invented')


def nemotron():
    if not val('NVIDIA_API_KEY'):
        emit('BLOCKED', 'Nemotron API inference', 'NVIDIA_API_KEY absent; no request sent')
        return
    try:
        base = val('NVIDIA_BASE_URL', 'https://integrate.api.nvidia.com/v1').rstrip('/')
        if base != 'https://integrate.api.nvidia.com/v1':
            emit('BLOCKED', 'Nemotron API inference', 'Review custom endpoint before sending an NVIDIA credential')
            return
        data = request(base+'/chat/completions', val('NVIDIA_API_KEY'), {
            'model': val('NVIDIA_MODEL', 'nvidia/llama-3.3-nemotron-super-49b-v1.5'),
            'messages': [{'role': 'user', 'content': 'Reply with OK.'}], 'max_tokens': 32, 'stream': False,
            'temperature': 0, 'chat_template_kwargs': {'enable_thinking': False}})
        content = data['choices'][0]['message']['content']
        emit('PASS' if isinstance(content, str) and content.strip() else 'FAIL', 'Nemotron API inference', 'Nonempty real model response' if content else 'No response content')
    except Exception as exc:
        failure('Nemotron API inference', exc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['doctor', 'verify'])
    args = parser.parse_args()
    load_config()
    doctor()
    if args.mode == 'verify':
        meterless()
        zetaris()
        nemotron()
    counts = {s: RESULTS.count(s) for s in ('PASS', 'FAIL', 'BLOCKED', 'NOT_TESTED')}
    print('SUMMARY | '+ ' | '.join(f'{s}={n}' for s, n in counts.items()))
    return 1 if counts['FAIL'] else 2 if counts['BLOCKED'] or counts['NOT_TESTED'] else 0


if __name__ == '__main__':
    sys.exit(main())
