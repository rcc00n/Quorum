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
# DECISION(2026-10-27, rcc00n/Codex): permit only the exact hash-bound public/fictional review PNGs below.
# Why: preserve approved visual evidence without admitting arbitrary binary/runtime assets. New bytes need review.
REVIEWED_IMAGES = {'docs/reviews/2026-10-27-visual-hierarchy/impact-after-1440.png': 'e2a2da6d67068bef01ccb64f88bb63c4d1082b13d069742447ad0a34cb849efc',
 'docs/reviews/2026-10-27-visual-hierarchy/impact-after-390.png': '374596d18e9f49d85c96235e20be59130a6921d339a690acc84e25aa7f1b9df4',
 'docs/reviews/2026-10-27-visual-hierarchy/impact-before-1440.png': '19185341e6d19bb3eea286a6b1e99e38c404aabcb2e1531b19a96ba46cba0093',
 'docs/reviews/2026-10-27-visual-hierarchy/impact-before-390.png': '1f681b6c7d73cb2224b5eabaa404480bf1cac81f65d36d1312eb1a97fe278b65',
 'docs/reviews/2026-10-27-visual-hierarchy/landing-after-1440.png': 'ba5bc8ad9ec2d94f428f18d3c8347663a0834536900a8169eeccbe5aa546f1c7',
 'docs/reviews/2026-10-27-visual-hierarchy/landing-after-390.png': 'ce7cec8d43ae6e172edfb8fc485a37aebb9bb8762efc5b592fb565dfb746c148',
 'docs/reviews/2026-10-27-visual-hierarchy/landing-before-1440.png': '81cef444ace9ca49baf64f558bea1f4ff3ac6023ac90078af6d6793558828367',
 'docs/reviews/2026-10-27-visual-hierarchy/landing-before-390.png': '1cd13f8259a15865cf1c5e0361e3e6e7a37e08dd1dbec0341542e21742ebfe65',
 'docs/reviews/2026-10-27-web-polish/history-desktop.png': 'a86889859753c7f5dd16e11eebd40930551517c064ed15527a561a573f10b89c',
 'docs/reviews/2026-10-27-web-polish/landing-desktop.png': '61bff76b170acdcd8f733117be992c9ffad4e1e1692c8bf9f436badc102e0d63',
 'docs/reviews/2026-10-27-web-polish/landing-phone.png': '778d9c838f5d0c494446c0989ace0c610c79c6cf08cd0aa291791c6ad28ab602',
 'docs/reviews/2026-10-27-web-polish/landing-sources-tablet.png': '5b60be035085f95013560645d4ec705b6d68cd3e5130697e290fe333fc3f4dd7',
 'docs/reviews/2026-10-27-web-polish/not-found-desktop.png': 'b7761e1c7d171edbf90ba5947adf34f3a3582892ef417c65ee800480a557ab5b',
 'docs/reviews/2026-10-27-web-polish/settings-desktop.png': 'c4d1e6ca365f269e28904fb20fa96b22737ce0874854d89a7919fe256fa821ab',
 'docs/reviews/2026-10-27-web-polish/sign-in-desktop.png': '66c09720a79851d67e90bfc38fdf331662e2fa85756963241c80fddcfb9718b3',
 'docs/reviews/2026-10-27-web-polish/sign-up-phone-dark.png': 'a7d638f89e46fe9ad681c6306788a96cf3b7bdf92842a02768227c94c940444d',
 'docs/reviews/2026-10-27-web-polish/story-desktop.png': '4416a91f73dc4740c6d5a40b3253e7f6fc1231f7b1ea29aa21cf109b42b93f1d',
 'docs/reviews/2026-10-27-web-polish/story-phone.png': '1161e9cfad55648927d337b22d5cb9c28a2aa9c1c57fad2915f51231f7ea2ad7',
 'docs/reviews/2026-10-27-web-polish/today-desktop.png': '7788f384c500e894070856797ccff14461310fa4e1bbe05f1cfd7d399290f5b1',
 'docs/reviews/2026-10-27-web-polish/today-phone.png': '39c3001e392f51508c11fa36267a8fe47d3b7815740dc8066a9677eed042ac93'}


# DECISION(2026-10-27, rcc00n/Codex): permit only these three inspected local navigation-review PNGs.
# Why: show pending-date controls with a disposable account; no production account, original news or credentials.
REVIEWED_IMAGES.update({
    'docs/reviews/2026-10-27-edition-navigation/dashboard-phone.png': 'e8bd1ca5f05de2d4fe7dfa1a470ce1d7ea4e3a78ddd40ba107e6000a66f7787c',
    'docs/reviews/2026-10-27-edition-navigation/history-desktop.png': 'a3f63385faba1e1375a8d648ede7c754ad3d862bbd5e42ba53c71afb8dad31e4',
    'docs/reviews/2026-10-27-edition-navigation/history-phone.png': '896f59d0510a61ae9ab4858d6dac89ce3c9521a514f57ad307a75a1486254f0a',
})


# DECISION(2026-10-27, rcc00n/Codex): permit only these inspected FICTIONAL #55 comparison bytes.
# Why: complete Anastasia's requested before/after record without publishing private production data.
REVIEWED_IMAGES.update({
    'docs/reviews/2026-10-27-paperclip-comparison/search-before-1440.png': '2e5167179a1c5688a5a7f12715e5751557ebdda20b9482d136e1c89d8398fca5',
    'docs/reviews/2026-10-27-paperclip-comparison/search-after-1440.png': 'f6b75bea335c39fc8594906d5645c21d8f6e60f496ed07fd976f0f69858f822e',
    'docs/reviews/2026-10-27-paperclip-comparison/search-before-390.png': 'f771f13f38ba429b94b38bcaa1a51e928aac52146aabc72cdbc2e7212dbe031b',
    'docs/reviews/2026-10-27-paperclip-comparison/search-after-390.png': '01fe78d4897eae2e7d985e7a6aa8d3bb519c066babf247cffb03aaec1c950a21',
})


# DECISION(2026-10-27, rcc00n/Codex): permit only these inspected public source-tint comparison bytes.
# Why: document the requested colour-only change without allowing arbitrary binaries or private captures.
REVIEWED_IMAGES.update({
    'docs/reviews/2026-10-27-source-tints/sources-before-1440.png': 'e3f82eec39b024156d8ccec10536702a6b33ac0bb871291bb2655196306b7979',
    'docs/reviews/2026-10-27-source-tints/sources-after-1440.png': 'ce99a5ea0dad451fafbdcdff8b2e69e26dd2e68e5586fa9d26028babb18a3e0b',
    'docs/reviews/2026-10-27-source-tints/sources-before-390.png': '11dd680549d866751488470aa1b0d46c8d811d06e6c2027366eaee761bd11d9b',
    'docs/reviews/2026-10-27-source-tints/sources-after-390.png': '5a61409bb9da176c60b18e59ffa053eb8578112499e7425f949a88b79bd334e9',
})


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
