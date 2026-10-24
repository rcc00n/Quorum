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

# Keep shared configuration when this file runs as the command-line entry point.
if __name__ == '__main__':
    sys.modules['checks'] = sys.modules[__name__]

ROOT = Path(__file__).resolve().parent.parent
PIN = '1742dec56a66e58eef9dda2d2b865823758ca8cd'
RESULTS = []
CFG = dict(os.environ)
# smoke_test.py names are canonical. Nightshift Console names (Power 4.5) and the
# previous Quorum token name fill those when the canonical entry is empty.
GUIDE_ALIASES = {
    'METERLESS_BASE_URL': 'MODEL_BASE_URL',
    'METERLESS_RUNTIME_TOKEN': 'MODEL_API_KEY',
    'METERLESS_API_KEY': 'MODEL_API_KEY',
    'METERLESS_MODEL': 'NEMOTRON_MODEL',
}


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


def apply_guide_aliases(cfg):
    for alias, canonical in GUIDE_ALIASES.items():
        if cfg.get(alias) and not cfg.get(canonical):
            cfg[canonical] = cfg[alias]
    return cfg


def load_config():
    known = set(re.findall(r'^([A-Z_]+)=', (ROOT / '.env.example').read_text(), re.M)) | set(GUIDE_ALIASES)
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
    apply_guide_aliases(CFG)


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
    # DECISION(2026-10-22, rcc00n/Codex): Codex workflow; legacy Cursor
    # acceptance runs only in cursor-history mode, never routine readiness.
    rc, out = run(['df', '-Pk', str(ROOT)])
    if rc == 0:
        fields = out.splitlines()[-1].split()
        emit('PASS' if int(fields[3]) >= 15*1024*1024 else 'BLOCKED', 'disk capacity', f'{int(fields[3])//(1024*1024)} GiB available')
    rc, out = run(['docker', 'info', '--format', '{{.MemTotal}} {{.NCPU}}'])
    if rc == 0:
        memory, cpus = map(int, out.split())
        emit('PASS' if memory >= 6*1024**3 and cpus >= 4 else 'BLOCKED', 'Zetaris Docker capacity',
             f'{memory/1024**3:.2f} GiB / {cpus} CPUs; bundle minimum 6 GiB, recommendation ~8 GiB and 4 CPUs')
    import services
    available = services.available_memory()
    emit('PASS' if available >= 5*1024**3 else 'BLOCKED', 'Zetaris startup headroom',
         f'{available/1024**3:.2f} GiB available; local safety gate 5 GiB for default 2g/1g heaps and headroom')
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


def cursor_history():
    """Optional historical diagnostics; excluded from doctor/verify summaries."""
    ps = r'''$p=$env:QUORUM_CURSOR_EXE; if(!$p){$p="$env:LOCALAPPDATA\Programs\cursor\Cursor.exe"}; if(Test-Path -LiteralPath $p){Write-Output (Get-Item -LiteralPath $p).VersionInfo.ProductVersion; exit 0}; exit 2'''
    env = dict(os.environ, QUORUM_CURSOR_EXE=val('CURSOR_EXE'))
    rc, out = run(['powershell.exe', '-NoProfile', '-Command', ps], env=env)
    emit('PASS' if rc == 0 else 'BLOCKED', 'Cursor installation', 'Windows executable '+out if rc == 0 else 'Windows executable unavailable')
    cursor_acceptance()


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


def zetaris():
    import services
    try:
        data = services.validate_deployment()
    except (ValueError, OSError, KeyError):
        emit('BLOCKED', 'Official Zetaris platform', 'Prepare the external supplied bundle and private configuration')
        return
    emit('PASS', 'Official platform configuration', 'Supplied images/env retained; six default services; loopback-only exposure')
    emit('PASS' if services.registry_configured() else 'BLOCKED', 'Azure Registry login',
         'Credential entry present; actual image access still requires successful pull' if services.registry_configured() else 'Gateway registry credentials unavailable; no images pulled')
    rc, raw = run(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project='+services.PROJECT])
    state = {}
    ids = raw.split() if rc == 0 else []
    if ids:
        rc, raw = run(['docker', 'inspect', '--format', '{{index .Config.Labels "com.docker.compose.service"}}|{{.State.Status}}|{{.State.ExitCode}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}', *ids])
        if rc == 0:
            state = {parts[0]: parts[1:] for line in raw.splitlines() if len(parts := line.split('|')) == 4}
    running_expected = services.RUNNING
    if 'ai-datasteward' in data.get('services', {}):
        running_expected = services.RUNNING + ('ai-datasteward',)
    for name in running_expected:
        entry = state.get(name)
        ok = entry and entry[0] == 'running' and entry[2] in ('healthy', 'none')
        emit('PASS' if ok else 'FAIL' if entry and entry[0] not in ('created', 'running') else 'BLOCKED', 'Zetaris '+name,
             'Running with acceptable health' if ok else 'Not ready; official deployment not started or prerequisite pending')
    for name in services.JOBS:
        entry = state.get(name)
        ok = entry and entry[0] == 'exited' and entry[1] == '0'
        emit('PASS' if ok else 'FAIL' if entry and entry[0] == 'exited' else 'BLOCKED', 'Zetaris '+name,
             'One-shot completed with exit 0' if ok else 'Required one-shot job incomplete')
    ready = all(name in state and state[name][0] == 'running' and state[name][2] in ('healthy', 'none') for name in services.RUNNING)
    if not ready:
        for name in ('GUI /api/config', 'REST API', 'SQL Editor SELECT 1', 'sample dataset SELECT', 'official verify.sh'):
            emit('BLOCKED', 'Zetaris '+name, 'Running official deployment prerequisite missing; no integration PASS claimed')
        return
    settings = services.bundle_env()
    ui = 'http://localhost:'+settings.get('UI_PORT', '3000')
    api = 'http://127.0.0.1:'+settings.get('API_PORT', '8888')
    try:
        config = request(ui+'/api/config')
        emit('PASS' if isinstance(config, dict) else 'NOT_TESTED', 'Zetaris GUI /api/config', 'Actual UI config response; not SQL verification')
    except Exception as exc:
        failure('Zetaris GUI /api/config', exc)
    # The bundle probes HTTP / without curl --fail; SQL is verified separately below.
    try:
        status = probe_api_http(api+'/')
        emit('PASS', 'Zetaris REST API process', f'HTTP {status} at the bundled root probe; SQL tested separately')
    except Exception as exc:
        failure('Zetaris REST API process', exc)
    try:
        login = request(ui+'/api/auth/login', body={'username': settings['ZETARIS_ADMIN_EMAIL'], 'password': settings['ZETARIS_ADMIN_PASSWORD']})
        serialized = json.dumps(login)
        token = re.search(r'[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}', serialized)
        org = re.search(r'"orgId"\s*:\s*([0-9]+)', serialized)
        if not token or not org:
            raise ValueError('Login missing documented token or orgId')
        headers = {'X-Org-ID': org[1], 'X-Request-ID': '11111111-2222-3333-4444-555555555555'}
        def contains_one(obj):
            if isinstance(obj, dict):
                return obj.get('one') in (1, '1') or any(contains_one(v) for v in obj.values())
            if isinstance(obj, list):
                return any(contains_one(v) for v in obj)
            return False
        result = request(ui+'/api/proxy/query/sql/start', token[0], {'select': 'SELECT 1 AS one', 'pageLimit': 1}, headers)
        emit('PASS' if contains_one(result) else 'NOT_TESTED', 'Zetaris SQL Editor SELECT 1',
             'Actual one=1 returned through UI → API → engine' if contains_one(result) else 'Response shape/result not validated; values withheld')
        sample = request(ui+'/api/proxy/query/sql/start', token[0], {'select': 'SELECT * FROM NY_TAXI.customers LIMIT 1', 'pageLimit': 1}, headers)
        # Only accept recognizable nonempty row collections; never a query receipt alone.
        def has_rows(obj):
            if isinstance(obj, dict):
                return any(isinstance(obj.get(k), list) and bool(obj[k]) and isinstance(obj[k][0], (dict, list)) for k in ('rows', 'records')) or any(has_rows(v) for v in obj.values())
            return False
        emit('PASS' if has_rows(sample) else 'NOT_TESTED', 'Zetaris sample dataset SELECT',
             'Bundled NY_TAXI.customers query returned structured rows' if has_rows(sample) else 'Dataset row schema not validated; inspect privately')
    except Exception as exc:
        failure('Zetaris authenticated SQL', exc)
    rc, _ = run(['bash', './verify.sh'], cwd=services.platform_dir(), env=services.command_env(), timeout=120)
    emit('PASS' if rc == 0 else 'FAIL', 'Official Zetaris verify.sh', 'All bundled checks passed' if rc == 0 else 'Official checks unsuccessful; raw output withheld')


def probe_api_http(url):
    # DECISION(2026-10-23, rcc00n/Codex): accept the bundled API's unrouted root (404) as
    # process reachability. Why: authenticated SQL works there; root 200 is not its contract.
    try:
        with urllib.request.build_opener(NoRedirect).open(url, timeout=15) as response:
            if response.status != 200:
                raise ValueError('Unexpected API root response')
            return response.status
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return exc.code
        raise


def nemotron(allow_inference=False):
    # Same three settings smoke_test.py reads. Nightshift Console aliases are already folded in.
    required = ('MODEL_BASE_URL', 'MODEL_API_KEY', 'NEMOTRON_MODEL')
    if not all(val(key) for key in required):
        emit('BLOCKED', 'Nemotron through Meterless', 'MODEL_BASE_URL, MODEL_API_KEY and NEMOTRON_MODEL from your Nightshift Console or the NVIDIA route on that same base URL')
        return
    if not allow_inference:
        emit('NOT_TESTED', 'Nemotron through Meterless', 'Credentials configured; explicitly use --inference for one capped request; diagnostics spend no provider credits')
        return
    try:
        base = val('MODEL_BASE_URL').rstrip('/')
        if base.endswith(('/chat/completions', '/models')):
            raise ValueError('Supply the API base URL, not an operation URL')
        data = request(base+'/chat/completions', val('MODEL_API_KEY'), {
            'model': val('NEMOTRON_MODEL'), 'messages': [{'role': 'user', 'content': 'Reply with OK.'}],
            'max_tokens': 32, 'stream': False, 'temperature': 0})
        content = data['choices'][0]['message']['content']
        emit('PASS' if isinstance(content, str) and content.strip() else 'FAIL', 'Nemotron through Meterless',
             'Nonempty real response from configured Meterless Nemotron route; output withheld' if content else 'No response content')
    except Exception as exc:
        failure('Nemotron through Meterless', exc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['doctor', 'verify', 'cursor-history'])
    parser.add_argument('--inference', action='store_true', help='Explicitly send one capped Meterless request when real credentials are supplied')
    args = parser.parse_args()
    if args.inference and args.mode != 'verify':
        parser.error('--inference requires verify')
    load_config()
    if 'FAIL' in RESULTS:
        print('FAIL | diagnostics | Correct private configuration before running checks')
        return 1
    if args.mode == 'cursor-history':
        cursor_history()
    else:
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
