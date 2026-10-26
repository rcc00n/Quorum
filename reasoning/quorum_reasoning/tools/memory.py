"""Opt-in source-memory candidates. Memory never supplies evidence or a verdict."""
from __future__ import annotations
import json
import os
import re
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from .. import config, llm, untrusted
from ..trace import step, finish
from .corpus import OFFICIAL_ID_OFFSET, _edition_window, _previous_window, previous_days


def enabled(state):
    return config.get('engines','hmem','off') == 'on' and not llm.is_dry_run(state.get('dry_run',True))


def identity(doc):
    official=bool(doc.get('official'))
    return dict(namespace='official' if official else 'article',
                id=doc['id']-OFFICIAL_ID_OFFSET if official and doc['id']>=OFFICIAL_ID_OFFSET else doc['id'],
                **{k:doc.get(k) for k in ('source_id','url','published_at','content_hash','fetched_at','access_level','independence_group','wire_origin','kind','doc_type')})


def _launcher(home):
    # DECISION(2026-10-25, rcc00n/Codex): run TSX through Node, avoiding POSIX-only .bin shims.
    # Why: subprocess argv works with spaces on Windows without shell interpretation.
    override = os.getenv('QUORUM_HMEM_TSX')
    if override:
        return [override]  # existing explicit executable override; never invoke a shell
    node = shutil.which('node')
    cli = home / 'engines/hmem/reference/node_modules/tsx/dist/cli.mjs'
    if not node or not cli.is_file():
        raise ValueError('Installed Node and TSX CLI required')
    return [node, str(cli)]


# DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): the sidecar's Node process gets an allowlisted environment,
# never Python's whole one: these names when set (PATHEXT added because tsx's cross-spawn reads it on Windows; no
# COMSPEC, Node is spawned directly), plus METERLESS_HOME, QUORUM_DRY_RUN and QUORUM_HMEM_DIR as checked in _call;
# never NODE_OPTIONS, DATABASE_URL or a name ending in _KEY, _TOKEN, _PASSWORD or _SECRET. Why: the sidecar runs a
# downloaded engine that needs no credential, and inheriting the environment handed it every key in .env.
_SIDECAR_ENV = ('PATH', 'PATHEXT', 'SYSTEMROOT', 'SystemDrive', 'WINDIR', 'TEMP', 'TMP', 'USERPROFILE', 'HOME',
                'LOCALAPPDATA', 'APPDATA')
_NEVER_TO_SIDECAR = re.compile(r'NODE_OPTIONS|DATABASE_URL|.*_(KEY|TOKEN|PASSWORD|SECRET)', re.IGNORECASE)


def _sidecar_env(home, directory):
    env = {name: os.environ[name] for name in _SIDECAR_ENV if name in os.environ}
    if 'QUORUM_DRY_RUN' in os.environ:
        env['QUORUM_DRY_RUN'] = os.environ['QUORUM_DRY_RUN']
    env.update(METERLESS_HOME=str(home), QUORUM_HMEM_DIR=str(directory))
    return {name: value for name, value in env.items() if not _NEVER_TO_SIDECAR.fullmatch(name)}


def _call(state, action, **payload):
    repo=Path(__file__).resolve().parents[3]
    directory=Path(os.environ['QUORUM_HMEM_DIR']).expanduser()
    if not directory.is_absolute() or directory.resolve().is_relative_to(repo) or any((parent/'.git').exists() for parent in (directory.resolve(),*directory.resolve().parents)):
        raise ValueError('Private memory must stay outside the repository')
    home=Path(os.environ['METERLESS_HOME'])
    launcher = _launcher(home)
    data=json.dumps(dict(action=action,dry_run=state.get('dry_run',True),**payload))
    if len(data.encode())>2*1024*1024:raise ValueError('Memory request too large')
    # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): the sidecar's stdin and stdout are UTF-8 explicitly, not
    # the locale's code page. Why: on Windows text=True decodes with cp1252 outside `python -X utf8`, while Node writes
    # UTF-8: a recalled record with a non-ASCII quote or label would be garbled or fail to decode.
    result=subprocess.run(launcher + [str(repo/'reasoning/memory/sidecar.mjs')],input=data,encoding='utf-8',capture_output=True,timeout=20,check=True,
                          env=_sidecar_env(home,directory))  # decision at _SIDECAR_ENV
    if len(result.stdout.encode())>2*1024*1024:raise ValueError('Memory response too large')
    return json.loads(result.stdout)


def _trace(state,event_id,decision,reason):
    with step(state,'memory',event_id=event_id) as s:
        s.decision=decision;s.reason=reason
    return finish(state,s)


def remember(state,events):
    if not enabled(state):return [],[]
    try:
        docs={(identity(d)['namespace'],identity(d)['id']):d for d in state['documents'] if not d.get('superseded')}
        base=dict(topic_id=state['topic_id'],edition_date=state['edition_date'],run_id=state['run_id'],fictional=state.get('corpus')=='fixture')
        rows=[]
        for claim in state['claims'].values():
            if claim.get('final_status')!='confirmed' or claim.get('kind') not in ('fact','number'):continue
            for ev in claim['evidence']:
                ns='official' if ev.get('official_doc_id') is not None else 'article'
                doc=docs.get((ns,ev.get('official_doc_id') if ns=='official' else ev.get('document_id')))
                if not doc or ev['stance']!='supports' or ev.get('source_id')!=doc['source_id'] or ev['url']!=doc['url']:continue
                if type(ev.get('char_start')) is not int or type(ev.get('char_end')) is not int or ev['char_start']<0 or ev['char_end']-ev['char_start']!=len(ev['quote']):continue
                if not re.fullmatch('[0-9a-f]{64}',ev.get('content_hash_at_quote') or '') or type(ev.get('access_achieved')) is not int or ev.get('access_achieved') not in (1,2):continue
                rows.append(dict(base,kind='evidence-candidate',event_id=claim['event_id'],docref=identity(doc),
                                 claim_id=claim['id'],claim_text=claim['text'],quote=ev['quote'],
                                 **{k:ev.get(k) for k in ('char_start','char_end','content_hash_at_quote','access_achieved','fetched_at')}))
        for event in events:
            for row in event.get('framing',{}).get('outlets',[]):
                matches=[d for d in docs.values() if d['url']==row['url']]
                if len(matches)==1 and row.get('interpretation_label'):
                    rows.append(dict(base,kind='framing',event_id=event['id'],docref=identity(matches[0]),interpretation_label=row['interpretation_label']))
        result=_call(state,'store',rows=rows) if rows else dict(count=0,ledger_entries=0)
        return [_trace(state,None,f"stored {result['count']} source memories",f"Reference H-MEM; candidate-only records; {result['ledger_entries']} ledger actions")],[]
    except Exception as exc:
        # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a memory failure names its exception type through
        # untrusted.public_failure, never its text, in the trace reason and the run error. Why: the operator needs
        # to tell a missing METERLESS_HOME (KeyError) from a timeout or a fail-closed store (CalledProcessError)
        # without the store path, stderr or a recalled quote reaching the snapshot.
        failure=untrusted.public_failure(exc)
        return [_trace(state,None,'memory write unavailable',f'No memory success claimed; {failure}')],[dict(node='memory',event_id=None,message=f'Source memory write unavailable: {failure}')]


def prioritize(state,event_id,query,ordered):
    if not enabled(state):return ordered,[],[]
    # DECISION(2026-10-24, rcc00n/Codex): recall can only prioritize exact current authorized DocRefs.
    # Why: neither stale memory nor a recalled quote may bypass fresh fetch/stance/quote/independence checks.
    try:
        result=_call(state,'recall',query=query)
        start,_=_previous_window(state['edition_date'],previous_days());_,end=_edition_window(state['edition_date'])
        as_time=lambda x:datetime.fromisoformat(x.replace('Z','+00:00'))
        candidates=[]
        for row in result['rows']:
            r=row['record']
            if r['topic_id']!=state['topic_id'] or type(r['fictional']) is not bool or r['fictional']!=(state.get('corpus')=='fixture') or r['kind']!='evidence-candidate':continue
            if not as_time(start)<=as_time(r['docref']['published_at'])<as_time(end):continue
            for doc in ordered:
                # DECISION(2026-10-24, rcc00n/Codex): compare serialized DocRefs with exact JSON types.
                # Why: Python treats True, 1 and 1.0 as equal, weakening source identity.
                if not doc.get('superseded') and json.dumps(identity(doc),sort_keys=True,allow_nan=False)==json.dumps(r['docref'],sort_keys=True,allow_nan=False) and doc not in candidates:candidates.append(doc)
        rest=[doc for doc in ordered if doc not in candidates]
        trace=_trace(state,event_id,f'recalled {len(candidates)} authorized source candidates',f"Reference H-MEM; fresh verification required; {result['ledger_entries']} ledger actions")
        return candidates+rest,[trace],[]
    except Exception as exc:
        failure=untrusted.public_failure(exc)  # decision in remember
        return ordered,[_trace(state,event_id,'memory recall unavailable',f'Ordinary research ranking retained; {failure}')],[dict(node='memory',event_id=event_id,message=f'Source memory recall unavailable: {failure}')]
