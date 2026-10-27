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


# DECISION(2026-10-27, rcc00n/Codex): permit only these eight visually inspected PR #52 screenshot bytes.
# Why: Anastasia's local disposable-account/public-registry evidence is safe; keep arbitrary binaries excluded.
REVIEWED_IMAGES.update({
    'docs/reviews/2026-10-27-web-spectrum-polish/before-desktop.png': '3c907df4d91c9d050483ca875b0cd68abc3d11f66180e11fc4c3dfa86103b99d',
    'docs/reviews/2026-10-27-web-spectrum-polish/field-desktop-hover.png': 'f20f84e726251c5a04eaf2a81811e95b007c2f1a0670dc235573adfe0a127579',
    'docs/reviews/2026-10-27-web-spectrum-polish/field-desktop.png': '97353091011d907a9152132d34fdc9be98b112de2cd800357d100a17892bd5cf',
    'docs/reviews/2026-10-27-web-spectrum-polish/field-phone-selected.png': '6afa8d21ce28e4982ba7770b3015712a993a763e7ef82e7e6f47568cd82bde2f',
    'docs/reviews/2026-10-27-web-spectrum-polish/field-tablet.png': 'c2359700d20f876639a698ab99605689433aec7b79d5a06eb82605f885081f11',
    'docs/reviews/2026-10-27-web-spectrum-polish/ledger-open-desktop.png': '1f474b810b982429437221cf3c93789d916bfc7f3623eb0bc40b0e796a6382e0',
    'docs/reviews/2026-10-27-web-spectrum-polish/page-desktop.png': '8ea44d01c543b049267e46015d7829bbeb028f92cc3a271283b0dad05a5d39b7',
    'docs/reviews/2026-10-27-web-spectrum-polish/page-phone.png': '2d81cd794e3696fc3639535ef21d0721d5aafd7b2826677025225d91e1cf6b41',
})


# DECISION(2026-10-27, Anastasia/Claude Code): permit only these fifteen inspected PR #62 review captures: the cabinet
# pages on the committed FICTIONAL 22 October sample under a disposable local account (home, topic panel, Also today
# fold with the sample's rows repeated, Account) and the same pages on integration as the before pictures; no real
# edition, no credential. Why: Vadim's gate for review PNGs (his f3e121e pattern); arbitrary binaries stay excluded.
REVIEWED_IMAGES.update({
    'docs/reviews/2026-10-27-web-cabinet/account-desktop.png': '71c24bac072aad4b731a3eb3500d87e4334ba5cc01b18e96ceda540b1c7baf4f',
    'docs/reviews/2026-10-27-web-cabinet/account-phone.png': '0bbc8ccff14c7788681afab261c566131200832344ff692773f64a5f7f41e7d3',
    'docs/reviews/2026-10-27-web-cabinet/account-tablet.png': '608afb0268b29818ea1e2871c28b4eeddb03f6743f4fa0d64ea9d91b1894fa80',
    'docs/reviews/2026-10-27-web-cabinet/also-fold-desktop.png': 'd42274421c87e34bf6ed1b798d87603fcb7b30964eae4412e7fdea50f7c63548',
    'docs/reviews/2026-10-27-web-cabinet/also-fold-phone.png': 'c5821308c235f5ee633644feabc9635495b629685ce44add47eea582fd7e36f6',
    'docs/reviews/2026-10-27-web-cabinet/before-home-desktop.png': 'fb1ba4967001c531347a75bd32472d585b95fcaedc9ab179b9ce9ecbc335f670',
    'docs/reviews/2026-10-27-web-cabinet/before-home-phone.png': '6277ef45a273cd20e0f4ff8b03355590333caf97074bce949ab9d9ba02b74e3d',
    'docs/reviews/2026-10-27-web-cabinet/before-settings-desktop.png': '0f6ed781af9b1c9cb386bdc68ae4b47348bcb86676a6640e53a4bb8e747691a7',
    'docs/reviews/2026-10-27-web-cabinet/before-settings-phone.png': '66c5276e75ee2612e39dd1e420f3d69fa8401c6b0759dd57229738fa4e21b060',
    'docs/reviews/2026-10-27-web-cabinet/home-desktop.png': 'add5013344de80d3aa09b9c4fef6c3600f95610a1a036e1c5e9f7563cb27d077',
    'docs/reviews/2026-10-27-web-cabinet/home-phone.png': '4ac70e673bc119503a604c2266ca01fae8c1065144a5af1a9f11fef7a200cfda',
    'docs/reviews/2026-10-27-web-cabinet/home-tablet.png': 'a7fe40ca4f66da58071bd4fcf9feb1266cd0babac03b31bd82704e7d4aa1c2bc',
    'docs/reviews/2026-10-27-web-cabinet/home-topics-desktop.png': 'f4166f42cd34795f60ed52d7489894b3dadd9358d7310d162f9555b641216d7d',
    'docs/reviews/2026-10-27-web-cabinet/home-topics-phone.png': '1028225c28445100913184a2ea7f0df71a1e901863202ff7da5f8b25c057f529',
    'docs/reviews/2026-10-27-web-cabinet/home-topics-tablet.png': '8151ebda5a3360a4e48ff22909d7c068699efeff207b970f94ba6b1d701c4e9e',
})


# DECISION(2026-10-27, Anastasia/Claude Code): permit only these 13 inspected PR review captures of the second cabinet pass:
# the story, topic, History, Account and Sources pages on the committed FICTIONAL 22 October sample under a disposable local
# account; no real edition, no credential. Why: Vadim's gate for review PNGs (his f3e121e pattern); arbitrary binaries stay excluded.
REVIEWED_IMAGES.update({
    'docs/reviews/2026-10-27-web-cabinet-pages/account-desktop.png': 'c908f19d3f8fabea053e27dc98bbc4b0f57e79d8e882b8ce5eb5d7dd2b91ec7e',
    'docs/reviews/2026-10-27-web-cabinet-pages/account-phone.png': '1ea0b79c850eb0379c7ca14fd73778a8edd56ff9929661a3a3f5e17043f686b3',
    'docs/reviews/2026-10-27-web-cabinet-pages/history-desktop.png': 'fbcaa7b02c4a36c2466b3cf80d0ad7a3977080088ee228d7c472fb3c99a83ea6',
    'docs/reviews/2026-10-27-web-cabinet-pages/history-phone.png': '5ee789769ac9b51b751f9495cd98437566d628a550c81037eb03f45136778881',
    'docs/reviews/2026-10-27-web-cabinet-pages/sources-desktop.png': 'bbb89492691ea67431770695a3ad6f541545a369f0628fe9851d8a79c2bd6139',
    'docs/reviews/2026-10-27-web-cabinet-pages/sources-phone.png': '25a0d1efba7eded6fddb91205ecbcb96cece36f9ac4eafa6105913b280a160d1',
    'docs/reviews/2026-10-27-web-cabinet-pages/story-claims-desktop.png': 'dfe951890917ddb33ae5948dd02145bb268a27c4a9323f1a17ad20f6742f8ecd',
    'docs/reviews/2026-10-27-web-cabinet-pages/story-desktop.png': '11e3cbada3152dfb0cc701ff9eac98a9bb70fe10864e484c13a63318a21562a2',
    'docs/reviews/2026-10-27-web-cabinet-pages/story-phone.png': 'f81ac3b549da0b744bf76c3748631098f463205ba8d2c459f16c7a6795232199',
    'docs/reviews/2026-10-27-web-cabinet-pages/story-stuck-desktop.png': '282d1e8b2efbc8c1af0e15d34d1154708ba8f7d2c251f9ecbd397667de124311',
    'docs/reviews/2026-10-27-web-cabinet-pages/story-stuck-phone.png': '2fa255400682986925a6cda9a7aad078540bb3d1f3b0792ca374170b3abedd3f',
    'docs/reviews/2026-10-27-web-cabinet-pages/topic-desktop.png': 'eb89bff637e9246e6e84d61f8f876554aa24e69ed7dccfb76b6c19e70447865e',
    'docs/reviews/2026-10-27-web-cabinet-pages/topic-phone.png': '05eed573b1db0c103e00178603f1109c7d393595038d058a3f43ca56d3c2c852',
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
