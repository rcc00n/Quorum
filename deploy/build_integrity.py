"""Local build receipts bind standalone assets to the web source that produced them."""
import hashlib
import json
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


def write_receipt(repo, build, expected_digest):
    if web_digest(repo) != expected_digest:
        raise RuntimeError('Web source changed during the build; rebuild before packaging')
    receipt = dict(version=1, web_source_sha256=web_digest(repo),
                   build_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip())
    (Path(build) / RECEIPT).write_text(json.dumps(receipt, sort_keys=True)+'\n')


def validate_build(repo, build):
    try:
        receipt=json.loads((Path(build)/RECEIPT).read_text())
        if receipt['version'] != 1 or receipt['web_source_sha256'] != web_digest(repo):
            raise ValueError()
        if not all((Path(build)/'.next'/name).is_dir() for name in ('standalone','static')):
            raise ValueError()
    except (OSError,ValueError,KeyError,TypeError):
        raise RuntimeError('Build receipt missing, stale or incomplete; rebuild the reviewed web source') from None
    return receipt


if __name__ == '__main__':
    if sys.argv[1] == '--digest':
        print(web_digest(Path(sys.argv[2])))
    else:
        write_receipt(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])
