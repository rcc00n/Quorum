#!/usr/bin/env python3
"""Check public-repository index without emitting secret contents."""
import re
import hashlib
import subprocess
import sys
from pathlib import PurePosixPath

# DECISION(2026-10-25, rcc00n/Codex): scan every token suffix and numbered model-key slot.
# Why: Meterless aliases and operator key rotation must not bypass the public-index secret check.
patterns = [rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
            rb'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|nvapi-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})',
            rb'https?://[^\s/@:]+:[^\s/@]+@',
            rb'(?im)^[ \t]*(?:[A-Z_]*(?:API_KEY(?:_[0-9]+)?|TOKEN|SECRET_KEY|PASSWORD))[ \t]*=[ \t]*[\"\']?[A-Za-z0-9_+/=-]{12,}']
# DECISION(2026-10-27, rcc00n/Codex): permit only the exact PR47 public/fictional review PNGs below.
# Why: preserve approved visual evidence without admitting arbitrary binary/runtime assets. New bytes need review.
REVIEWED_IMAGES = {'docs/reviews/2026-10-27-web-polish/history-desktop.png': 'a86889859753c7f5dd16e11eebd40930551517c064ed15527a561a573f10b89c', 'docs/reviews/2026-10-27-web-polish/landing-desktop.png': '61bff76b170acdcd8f733117be992c9ffad4e1e1692c8bf9f436badc102e0d63', 'docs/reviews/2026-10-27-web-polish/landing-phone.png': '778d9c838f5d0c494446c0989ace0c610c79c6cf08cd0aa291791c6ad28ab602', 'docs/reviews/2026-10-27-web-polish/landing-sources-tablet.png': '5b60be035085f95013560645d4ec705b6d68cd3e5130697e290fe333fc3f4dd7', 'docs/reviews/2026-10-27-web-polish/not-found-desktop.png': 'b7761e1c7d171edbf90ba5947adf34f3a3582892ef417c65ee800480a557ab5b', 'docs/reviews/2026-10-27-web-polish/settings-desktop.png': 'c4d1e6ca365f269e28904fb20fa96b22737ce0874854d89a7919fe256fa821ab', 'docs/reviews/2026-10-27-web-polish/sign-in-desktop.png': '66c09720a79851d67e90bfc38fdf331662e2fa85756963241c80fddcfb9718b3', 'docs/reviews/2026-10-27-web-polish/sign-up-phone-dark.png': 'a7d638f89e46fe9ad681c6306788a96cf3b7bdf92842a02768227c94c940444d', 'docs/reviews/2026-10-27-web-polish/story-desktop.png': '4416a91f73dc4740c6d5a40b3253e7f6fc1231f7b1ea29aa21cf109b42b93f1d', 'docs/reviews/2026-10-27-web-polish/story-phone.png': '1161e9cfad55648927d337b22d5cb9c28a2aa9c1c57fad2915f51231f7ea2ad7', 'docs/reviews/2026-10-27-web-polish/today-desktop.png': '7788f384c500e894070856797ccff14461310fa4e1bbe05f1cfd7d399290f5b1', 'docs/reviews/2026-10-27-web-polish/today-phone.png': '39c3001e392f51508c11fa36267a8fe47d3b7815740dc8066a9677eed042ac93'}


def approved_review_image(name, data):
    return (name in REVIEWED_IMAGES and data.startswith(b'\x89PNG\r\n\x1a\n')
            and hashlib.sha256(data).hexdigest() == REVIEWED_IMAGES[name])


def main():
    paths = subprocess.check_output(['git', 'ls-files', '-z']).split(b'\0')
    failed = False
    count = 0
    for raw in paths:
        if not raw:
            continue
        name = raw.decode()
        p = PurePosixPath(name)
        forbidden = (p.name.startswith('.env') and p.name != '.env.example') or any(x in p.parts for x in ('node_modules', 'vendor', '.aws', '.ssh', 'volumes', 'Freemium', 'zetaris-freemium', 'zetaris-runtime')) or p.suffix.lower() in ('.exe', '.msi', '.zip', '.gguf', '.pem', '.key', '.pfx', '.db', '.dump', '.log', '.der', '.class')
        data = subprocess.check_output(['git', 'show', ':'+name])
        if forbidden or len(data) > 1024*1024 or (b'\0' in data and not approved_review_image(name, data)) or any(re.search(pattern, data) for pattern in patterns):
            print('FAIL | public repository safety | review '+name)
            failed = True
        count += 1
    print(('FAIL' if failed else 'PASS')+f' | public repository safety | inspected {count} index files; values withheld')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
