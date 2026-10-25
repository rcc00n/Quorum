"""Local build receipts bind standalone assets to the web source that produced them."""
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys

RECEIPT = '.quorum-build.json'


def web_digest(repo):
    root = Path(repo) / 'web'
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if any(part in ('node_modules', '.next') for part in relative.parts):
            continue
        if path.is_symlink():
            raise RuntimeError('Web source symlinks cannot enter a release build')
        if path.is_file():
            digest.update(str(relative).encode() + b'\0' + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def artifact_digest(build):
    # DECISION(2026-10-24, rcc00n/Codex): bind receipts to compiled output and reject linked artifacts.
    # Why: a matching source hash alone cannot detect modified server code or linked private files.
    root=Path(build)/'.next'
    if not (root/'standalone/server.js').is_file():
        raise ValueError('Standalone server missing')
    digest=hashlib.sha256()
    for name in ('standalone','static'):
        tree=root/name
        if not tree.is_dir() or tree.is_symlink() or root.is_symlink():
            raise ValueError('Artifact directory missing or linked')
        for path in sorted(tree.rglob('*')):
            if path.is_symlink():
                raise ValueError('Linked build artifact rejected; build with local dependencies')
            if path.is_file():
                digest.update(path.relative_to(root).as_posix().encode()+b'\0'+hashlib.sha256(path.read_bytes()).digest())
            elif not path.is_dir():
                raise ValueError('Special build artifact rejected')
    return digest.hexdigest()


def write_receipt(repo, build, expected_digest):
    if web_digest(repo) != expected_digest:
        raise RuntimeError('Web source changed during the build; rebuild before packaging')
    receipt = dict(version=2, web_source_sha256=web_digest(repo), artifact_sha256=artifact_digest(build),
                   build_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip())
    (Path(build) / RECEIPT).write_text(json.dumps(receipt, sort_keys=True)+'\n')


def validate_build(repo, build):
    try:
        receipt=json.loads((Path(build)/RECEIPT).read_text())
        if not isinstance(receipt,dict) or set(receipt)!={'version','web_source_sha256','artifact_sha256','build_revision'}:
            raise ValueError()
        if type(receipt['version']) is not int or receipt['version']!=2:
            raise ValueError()
        if not isinstance(receipt['build_revision'],str) or not re.fullmatch('[0-9a-f]{40}',receipt['build_revision']):
            raise ValueError()
        if receipt['web_source_sha256'] != web_digest(repo) or receipt['artifact_sha256']!=artifact_digest(build):
            raise ValueError()
    except (OSError,ValueError,KeyError,TypeError):
        raise RuntimeError('Build receipt missing, stale or incomplete; rebuild the reviewed web source') from None
    return receipt


if __name__ == '__main__':
    if sys.argv[1] == '--digest':
        print(web_digest(Path(sys.argv[2])))
    else:
        write_receipt(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])
