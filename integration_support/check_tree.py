#!/usr/bin/env python3
"""Static cross-owner checks. No database, credential, provider or service access."""
import argparse
import ast
import csv
import json
from pathlib import Path
import re
from rehearse import assignments,git,PINS


def literal(path,name):
    for node in ast.parse(path.read_text()).body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('Missing interface constant')


def check(root):
    root=Path(root)
    for name in ('reasoning','collectors','backend','web'):
        if not (root/name).is_dir():return dict(status='BLOCKED',reason='Combined owner tree required')
    merged=assignments((root/'.env.example').read_text())
    rows=set((root/'docs/DECISIONS.md').read_text().splitlines())
    ignores=set((root/'.gitignore').read_text().splitlines())
    for owner in ('reasoning','collection','web'):
        original=assignments(git(root,'show',PINS[owner]+':.env.example').stdout)
        if not original.items()<=merged.items():raise ValueError('Owner environment assignment lost or changed')
        decisions={x for x in git(root,'show',PINS[owner]+':docs/DECISIONS.md').stdout.splitlines() if x.startswith('| 2026-')}
        if not decisions<=rows:raise ValueError('Owner decision history lost')
        patterns={x for x in git(root,'show',PINS[owner]+':.gitignore').stdout.splitlines() if x and not x.startswith('#')}
        # A directory-only rule remains covered by the same name matching files and directories.
        if any(pattern not in ignores and not (pattern.endswith('/') and pattern[:-1] in ignores) for pattern in patterns):
            raise ValueError('Owner ignore rule lost')
    schema=(root/'collectors/schema.sql').read_text()
    for column,constant in (('doc_type','DOC_TYPES'),('wire_origin','WIRE_VALUES')):
        values=set(re.findall("'([^']+)'",re.search(r'CHECK \('+column+r' IN \(([^)]+)\)\)',schema)[1]))
        if values!=set(literal(root/'collectors/verify_collectors.py',constant)):raise ValueError('Schema/verifier enum mismatch')
    if literal(root/'reasoning/quorum_reasoning/rules/confirmation.py','DOCUMENT_TYPES_THAT_ESTABLISH')!={'law','order','vote','ruling'}:raise ValueError('Document confirmation contract changed')
    sources=list(csv.DictReader((root/'collectors/sources.csv').open()))
    if len({r['id'] for r in sources})!=len(sources):raise ValueError('Duplicate registry identity')
    agencies={r['independence_group'] for r in sources if r['kind']=='agency'}
    if agencies!={'ap','reuters','afp'}:raise ValueError('Wire independence groups differ')
    return dict(status='PASS',sources=len(sources),decision_history='preserved',environment='additive',ignore_rules='preserved',schema_interface='static match',database_verified=False,execution_provenance_verified=False,published=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',required=True);args=parser.parse_args()
    try:
        result=check(args.root);print(json.dumps(result,sort_keys=True));raise SystemExit(0 if result['status']=='PASS' else 2)
    except (OSError,ValueError,AttributeError,TypeError):raise SystemExit('FAIL: static owner-interface check; details withheld') from None
