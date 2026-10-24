#!/usr/bin/env python3
"""Package a clean reviewed portal and matching external build; no services or publication."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
from build_integrity import validate_build


def copy_portal_sources(repo, release):
    # DECISION(2026-10-24, rcc00n/Codex): export tracked portal/deploy files only.
    # Why: local databases, logs, credentials and private experiment files must not enter release archives.
    paths=subprocess.check_output(['git','ls-files','-z','--','backend','deploy'],cwd=repo).decode().split('\0')
    for name in filter(None,paths):
        source=repo/name
        if source.is_symlink() or source.name.startswith('.env') or source.suffix in ('.sqlite','.sqlite3','.dump','.log'):
            raise RuntimeError('Unsafe tracked release path; inspect source before packaging')
        target=release/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)


def main():
    repo=Path(__file__).resolve().parents[1]
    if subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).strip():
        raise RuntimeError('Package only a clean reviewed commit')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    label=sys.argv[1] if len(sys.argv)>1 else revision[:12]
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',label):
        raise RuntimeError('Use a simple release label')
    root=Path.home()/'.local/share/quorum'
    build=Path(os.getenv('QUORUM_WEB_BUILD',str(root/'portal-web-build'))).resolve()
    validate_build(repo,build)
    release=root/'releases'/label
    archive=root/(label+'.tar.gz')
    if release.exists() or archive.exists():
        raise RuntimeError('Release or archive exists; choose a new label')
    release.mkdir(parents=True)
    shutil.copytree(build/'.next/standalone',release/'web')
    shutil.copytree(build/'.next/static',release/'web/.next/static')
    copy_portal_sources(repo,release)
    shutil.copy2(build/'.quorum-build.json',release/'WEB_BUILD.json')
    (release/'REVISION').write_text(revision+'\n')
    with tarfile.open(archive,'w:gz') as tar:
        tar.add(release,arcname=label)
    print(archive)


if __name__=='__main__':
    try:main()
    except (OSError,RuntimeError,subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from None
