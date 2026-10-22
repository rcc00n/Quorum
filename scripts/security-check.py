#!/usr/bin/env python3
"""Check public-repository index without emitting secret contents."""
import re
import subprocess
import sys
from pathlib import PurePosixPath

paths = subprocess.check_output(['git', 'ls-files', '-z']).split(b'\0')
patterns = [rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
            rb'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|nvapi-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})',
            rb'https?://[^\s/@:]+:[^\s/@]+@',
            rb'(?im)^[ \t]*(?:[A-Z_]*(?:API_KEY|ACCESS_TOKEN|SECRET_KEY|PASSWORD|RUNTIME_TOKEN))[ \t]*=[ \t]*[\"\']?[A-Za-z0-9_+/=-]{12,}']
failed = False
count = 0
for raw in paths:
    if not raw:
        continue
    name = raw.decode()
    p = PurePosixPath(name)
    forbidden = (p.name.startswith('.env') and p.name != '.env.example') or any(x in p.parts for x in ('node_modules', 'vendor', '.aws', '.ssh', 'volumes', 'Freemium', 'zetaris-freemium', 'zetaris-runtime')) or p.suffix.lower() in ('.exe', '.msi', '.zip', '.gguf', '.pem', '.key', '.pfx', '.db', '.dump', '.log', '.der', '.class')
    data = subprocess.check_output(['git', 'show', ':'+name])
    if forbidden or len(data) > 1024*1024 or b'\0' in data or any(re.search(pattern, data) for pattern in patterns):
        print('FAIL | public repository safety | review '+name)
        failed = True
    count += 1
print(('FAIL' if failed else 'PASS')+f' | public repository safety | inspected {count} index files; values withheld')
sys.exit(1 if failed else 0)
