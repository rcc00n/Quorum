#!/usr/bin/env python3
"""Reproduce the pinned local merge rehearsal; never fetch, push or touch an existing worktree."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

PINS = {
    'integration':'c3cc5ac4a65855769ab48e36a1d59d5cc1ae261d',
    'reasoning':'3d894488835b19b22281784cf8bf1e2ad5fa2be3',
    'collection':'8f126c57a9ef9af798543bf23a0a60737b0ce5dc',
    'web':'f59e75840c9aee67ca35a8f44bf5dd42747af75f',
}
REHEARSAL_ROW = '| 2026-10-24 | rcc00n / Codex, explicit local rehearsal authorization | Local rehearsal retains all owner decision rows, additive environment/ignore entries and both development-contract and production-bridge gates; integration workflow approval is Issue #2 comment 6390138653. No product threshold, strict contract or publication authority changed. | Exercise reasoning → collection → web together without overwriting owner history or pushing rehearsal merges. |\n'


def git(root,*args,check=True):
    return subprocess.run(['git','-C',str(root),*args],check=check,text=True,capture_output=True)


def union_conflict(text):
    # DECISION(2026-10-24, rcc00n/Codex): union only known pinned additive conflicts.
    # Why: retaining both owner blocks is safer than selecting a branch's replacement file.
    result=[];inside=False;middle=False
    for line in text.splitlines(keepends=True):
        if line.startswith('<<<<<<< '):
            if inside:raise ValueError('Nested conflict')
            inside=True;middle=False
        elif line.rstrip()=='=======':
            if not inside or middle:raise ValueError('Unexpected conflict separator')
            middle=True
        elif line.startswith('>>>>>>> '):
            if not inside or not middle:raise ValueError('Unexpected conflict end')
            inside=False
        else:result.append(line)
    if inside:raise ValueError('Unclosed conflict')
    return ''.join(result)


def assignments(text):
    result={}
    for line in text.splitlines():
        match=re.match(r'^([A-Z][A-Z0-9_]*)=(.*)$',line)
        if match:
            key,value=match.groups()
            if key in result and result[key]!=value:raise ValueError('Conflicting public template assignments')
            result[key]=value
    return result


def rehearse(repo,destination,with_patches=False):
    repo,destination=Path(repo).resolve(),Path(destination).resolve()
    if destination.exists() or destination.is_relative_to(repo):raise ValueError('Use a new external disposable worktree path')
    for sha in PINS.values():git(repo,'cat-file','-e',sha+'^{commit}')
    git(repo,'worktree','add','--detach',str(destination),PINS['integration'])
    report=dict(inputs=PINS,merges=[],owner_approved=False,production_published=False)
    for owner in ('reasoning','collection','web'):
        result=git(destination,'merge','--no-ff','--no-edit',PINS[owner],check=False)
        conflicts=git(destination,'diff','--name-only','--diff-filter=U').stdout.splitlines()
        allowed={'collection':{'.env.example','docs/DECISIONS.md'},'web':{'.gitignore','docs/DECISIONS.md'}}.get(owner,set())
        if result.returncode and (not conflicts or set(conflicts)!=allowed):raise ValueError('Unexpected merge failure; inspect disposable tree')
        for name in conflicts:
            path=destination/name;path.write_text(union_conflict(path.read_text()))
        if owner=='web':
            path=destination/'docs/DECISIONS.md';text=path.read_text()
            old='- [ ] The impact-bar threshold: start at 6 of 9 with confirmation ≥ 1, then calibrate on the first real days.\n'
            text=text.replace(old,'- Historical web wording (superseded 2026-10-24 by the detailed impact-bar entry above; retained): '+old[6:])
            text=text.replace('| --- | --- | --- | --- |\n','| --- | --- | --- | --- |\n'+REHEARSAL_ROW,1)
            path.write_text(text)
        assignments((destination/'.env.example').read_text())
        if conflicts:
            git(destination,'add','--',*conflicts)
            git(destination,'commit','-m',f'Rehearse {owner} merge preserving owner decisions and additive configuration')
        merged=set((destination/'docs/DECISIONS.md').read_text().splitlines())
        owners=('reasoning','collection','web')
        for ref in ('integration',)+owners[:owners.index(owner)+1]:
            rows={line for line in git(repo,'show',PINS[ref]+':docs/DECISIONS.md').stdout.splitlines() if line.startswith('| 2026-')}
            if not rows<=merged:raise ValueError('Owner decision history lost')
        report['merges'].append(dict(owner=owner,commit=git(destination,'rev-parse','HEAD').stdout.strip(),resolved=conflicts))
    if with_patches:
        report['patches']=[]
        for patch in sorted((Path(__file__).parent/'patches').glob('*.patch')):
            git(destination,'apply','--check',str(patch))
            git(destination,'apply','--index',str(patch))
            git(destination,'diff','--cached','--check')
            git(destination,'commit','-m','Rehearse proposed support patch '+patch.stem)
            report['patches'].append(dict(name=patch.name,sha256=hashlib.sha256(patch.read_bytes()).hexdigest()))
    report['head']=git(destination,'rev-parse','HEAD').stdout.strip()
    report['clean']=not git(destination,'status','--porcelain').stdout.strip()
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',required=True)
    parser.add_argument('--destination',required=True)
    parser.add_argument('--with-proposed-patches',action='store_true')
    args=parser.parse_args()
    try:print(json.dumps(rehearse(args.repo,args.destination,args.with_proposed_patches),indent=2))
    except (OSError,ValueError,subprocess.CalledProcessError):raise SystemExit('Rehearsal stopped; inspect the disposable worktree. No branch was pushed.') from None
