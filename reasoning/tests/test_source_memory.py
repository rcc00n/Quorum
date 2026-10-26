"""Real reference persistence with explicit TEST records; no provider or live corpus."""
import copy
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from quorum_reasoning.tools import memory
from quorum_reasoning.nodes import research, frame
from quorum_reasoning.state import initial_state
from quorum_reasoning.tools.fetch_text import fetch_result, FetchResult, content_hash

TEXT='The Senate passed the aid bill.'


def state():
    s=initial_state('TEST-memory-run','russia-ukraine-war','2026-10-22',dry_run=False)
    s['corpus']='fixture'
    s['documents']=[dict(id=i,source_id=f'TEST-{i}',source_name=f'TEST-{i}',independence_group=f'TEST-{i}',
        kind='outlet',flank='left',tier='minor',url=f'https://example.org/TEST/{i}',title='TEST bill',lead=TEXT,
        published_at='2026-10-21T12:00:00Z',access_level=1,wire_origin=None,text=TEXT) for i in (1,2)]
    s['events']=[dict(id='TEST-event',document_ids=[1],headline='TEST bill',above_bar=False,framing={})]
    d=s['documents'][1]
    ev=research.evidence_from(d,TEXT,'supports','researcher',fetch_result(d,dry_run=True))
    s['claims']={'TEST-claim':dict(id='TEST-claim',event_id='TEST-event',text=TEXT,kind='fact',origin_document_id=1,
        final_status='confirmed',evidence=[ev])}
    s['research_rounds']={'TEST-event':1}
    return s


@pytest.fixture
def live_memory(monkeypatch,tmp_path):
    import os
    home=Path(os.getenv('METERLESS_HOME','/nonexistent'))
    if not (home/'engines/hmem/reference/node_modules/.bin/tsx').is_file():pytest.skip('installed reference/TSX not supplied')
    monkeypatch.delenv('QUORUM_DRY_RUN',raising=False)
    directory=tmp_path/'private-memory'
    monkeypatch.setenv('QUORUM_HMEM_DIR',str(directory))
    # Simulated live nodes only; json_task/fetch are stubbed, while the reference engine is real.
    monkeypatch.setattr(memory,'enabled',lambda s:not s['dry_run'])
    return directory


def test_default_off_and_forced_dry_do_not_touch_store(monkeypatch,tmp_path):
    s=state();directory=tmp_path/'never-created';monkeypatch.setenv('QUORUM_HMEM_DIR',str(directory))
    assert not memory.enabled(s)
    monkeypatch.setattr(memory.config,'get',lambda section,key,default=None:'on' if (section,key)==('engines','hmem') else default)
    s['dry_run']=True
    with patch.object(memory,'_call',side_effect=AssertionError('dry mode touched memory')):
        assert memory.remember(s,[])==([],[])
        assert memory.prioritize(s,'TEST-event','TEST',[])==([],[],[])
    assert not directory.exists()


def test_reference_persists_and_recalls_exact_docref_across_processes(live_memory):
    s=state();steps,errors=memory.remember(s,[])
    assert not errors and 'stored 1' in steps[0]['decision']
    rows,steps,errors=memory.prioritize(s,'TEST-event',TEXT,list(reversed(s['documents'])))
    assert not errors and rows[0]['id']==2 and 'recalled 1' in steps[0]['decision']
    assert (live_memory/'state.json').exists() and (live_memory/'ledger.jsonl').exists()
    raw=memory._call(s,'recall',query=TEXT)['rows'][0]['record']
    assert raw['docref']==memory.identity(s['documents'][1])
    assert raw['quote']==TEXT and raw['kind']=='evidence-candidate'
    assert 'stored 0' in memory.remember(s,[])[0][0]['decision']


def test_recalled_quote_is_not_evidence_without_fresh_fetch_and_stance(live_memory):
    s=state();memory.remember(s,[]);s['claims']['TEST-claim']['evidence']=[]
    fresh='The Senate did not pass the aid bill.'
    fetched=FetchResult(fresh,fresh,content_hash('TEST bill',TEXT,fresh),1,'2026-10-22T10:00:00Z','TEST shared fetcher')
    with patch.object(research,'fetch_result',return_value=fetched) as fetch, patch.object(research.llm,'json_task',return_value={'stance':'contradicts'}) as model:
        result=research.run(s)
    ev=result['claims']['TEST-claim']['evidence']
    assert fetch.called and model.called
    assert len(ev)==1 and ev[0]['stance']=='contradicts' and ev[0]['quote']==fresh
    assert ev[0]['content_hash_at_quote']==fetched.content_hash
    assert any(x['node']=='memory' and 'recalled 1' in x['decision'] for x in result['steps'])


def test_stale_unknown_wrong_namespace_or_fictional_identity_never_injected(live_memory):
    s=state();memory.remember(s,[])
    for field,value in (('source_id','OTHER'),('content_hash','a'*64),('official',True),('superseded',True)):
        candidate=copy.deepcopy(s['documents'][1]);candidate[field]=value
        ordered,steps,errors=memory.prioritize(s,'TEST-event',TEXT,[candidate])
        assert not errors and ordered==[candidate] and 'recalled 0' in steps[0]['decision']
    s['corpus']='zetaris'
    assert 'recalled 0' in memory.prioritize(s,'TEST-event',TEXT,s['documents'])[1][0]['decision']


def test_pending_write_fails_closed_and_frame_hook_reports_zero_truthfully(live_memory):
    s=state();s['claims']={}
    assert 'stored 0' in frame.run(s)['steps'][-1]['decision']
    assert not live_memory.exists()
    memory.remember(state(),[])
    (live_memory/'quorum.pending').write_text('TEST incomplete write')
    ordered,steps,errors=memory.prioritize(s,'TEST-event',TEXT,s['documents'])
    assert ordered==s['documents'] and errors and steps[0]['decision']=='memory recall unavailable'


def test_frame_hook_persists_attributed_framing_with_exact_docref(live_memory):
    s=state();s['events'][0]['above_bar']=True
    with patch.object(frame.llm,'json_task',return_value={'interpretation_label':'TEST source framing'}):
        result=frame.run(s)
    assert 'stored 2' in result['steps'][-1]['decision']
    rows=memory._call(s,'recall',query=TEXT)['rows']
    framing=next(x['record'] for x in rows if x['record']['kind']=='framing')
    assert framing['docref']==memory.identity(s['documents'][0])
    assert framing['interpretation_label']=='TEST source framing'


def test_memory_does_not_increase_existing_candidate_cap(live_memory,monkeypatch):
    s=state();memory.remember(s,[]);s['claims']['TEST-claim']['evidence']=[]
    for i in range(3,14):
        d=copy.deepcopy(s['documents'][1]);d.update(id=i,source_id=f'TEST-{i}',url=f'https://example.org/TEST/{i}');s['documents'].append(d)
    original=memory.config.get
    monkeypatch.setattr(memory.config,'get',lambda section,key,default=None:1 if (section,key)==('research','candidates_per_claim') else original(section,key,default))
    with patch.object(research.llm,'json_task',return_value={'stance':'contradicts'}) as model:
        result=research.run(s)
    assert model.call_count==1 and len(result['claims']['TEST-claim']['evidence'])==1


def test_missing_fresh_source_never_reuses_remembered_quote(live_memory):
    s=state();memory.remember(s,[]);s['claims']['TEST-claim']['evidence']=[]
    with patch.object(research,'fetch_result',return_value=None), patch.object(research.llm,'json_task') as model:
        result=research.run(s)
    model.assert_not_called()
    assert result['claims']['TEST-claim']['evidence']==[]



def test_raw_sidecar_dry_request_and_unrelated_directory_do_not_write(live_memory):
    s=state();s['dry_run']=True
    report=memory._call(s,'store',rows=[])
    assert report['disabled'] and not live_memory.exists()
    s['dry_run']=False;live_memory.mkdir();(live_memory/'TEST-unrelated').write_text('TEST protected data')
    with pytest.raises(Exception):memory._call(s,'store',rows=[])
    assert list(live_memory.iterdir())==[live_memory/'TEST-unrelated']
