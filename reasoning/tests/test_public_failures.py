"""Synthetic failing nodes: public trace keeps failures visible without exception contents."""
import json
from unittest.mock import patch
import pytest
from quorum_reasoning import untrusted
from quorum_reasoning.nodes import score, publish, extract
from quorum_reasoning.state import initial_state

PRIVATE = 'TEST_PRIVATE_ENDPOINT_PARAMETER'

@pytest.mark.parametrize('node',[score,extract])
def test_failed_node_does_not_export_exception_in_public_trace(node):
    state=initial_state('TEST-run','russia-ukraine-war','2026-10-22',dry_run=True)
    state['events']=[dict(id='TEST-event',headline='TEST event',document_ids=[])]
    with patch('quorum_reasoning.llm.json_task',side_effect=RuntimeError(PRIVATE)):
        result=node.run(state)
    assert PRIVATE not in json.dumps(result['steps'])
    assert result['steps'][0]['reason']==untrusted.public_failure(RuntimeError(PRIVATE))
    assert PRIVATE in result['errors'][0]['message']  # restricted diagnostic remains available


def test_failed_summary_is_partial_and_safe_without_hiding_failure():
    state=initial_state('TEST-run','russia-ukraine-war','2026-10-22',dry_run=True)
    with patch('quorum_reasoning.llm.json_task',side_effect=RuntimeError(PRIVATE)):
        p=publish.run(state)['snapshot']
    assert p['status']=='partial' and p['summary_source']=='fallback'
    assert PRIVATE not in json.dumps(p['trace'])
    assert PRIVATE in p['errors'][0]['message']


@pytest.mark.parametrize('name',['research','fact_check','write','frame','review_disputed'])
def test_remaining_failure_paths_preserve_status_without_public_exception(name):
    from quorum_reasoning import llm
    from quorum_reasoning.nodes import research, fact_check, write, frame, review_disputed
    from test_per_call_failures import _state
    from test_review_disputed import state_with, claim, SUPPORT_A, SUPPORT_B
    state=_state()
    if name in ('write','frame'):
        state['events'][0]['above_bar']=True
    if name=='review_disputed':
        state=state_with([claim('TEST-claim','ev1','confirmed','unverified',[SUPPORT_A,SUPPORT_B])])
    node=locals()[name]
    exc = RuntimeError(PRIVATE)
    exc.status_code = 429
    with patch.object(llm,'is_dry_run',return_value=False), patch.object(llm,'json_task',side_effect=exc):
        result=node.run(state)
    assert result['errors'] and result['steps']
    public={key:value for key,value in result.items() if key!='errors'}
    assert PRIVATE not in json.dumps(public)
    assert 'RuntimeError, HTTP 429' in json.dumps(public)
    if name!='frame':  # Frame deliberately records only exception type even in its error summary.
        assert PRIVATE in json.dumps(result['errors'])
    if name=='review_disputed':
        assert result['claims']['TEST-claim']['final_status']=='disputed'
    if name=='fact_check':
        assert all(c['fact_checker_status']=='unverified' for c in result['claims'].values())


@pytest.mark.parametrize("status", [429, 500, 401])
def test_structured_http_status_survives_without_response_body(status):
    import httpx
    request = httpx.Request("POST", "https://private.invalid/secret")
    response = httpx.Response(status, request=request)
    exc = httpx.HTTPStatusError(PRIVATE, request=request, response=response)
    assert untrusted.public_failure(exc) == f"{untrusted.PUBLIC_FAILURE} (HTTPStatusError, HTTP {status})"
    assert PRIVATE not in untrusted.public_failure(exc)


@pytest.mark.parametrize("status", [True, 429.0, "429", 99, 600, None])
def test_untrusted_status_values_and_message_are_not_parsed(status):
    exc = RuntimeError("HTTP 429 " + PRIVATE)
    exc.status_code = status
    assert untrusted.public_failure(exc) == f"{untrusted.PUBLIC_FAILURE} (RuntimeError)"


def test_hostile_exception_attributes_and_names_are_safe():
    class Hostile(Exception):
        @property
        def status_code(self):
            raise RuntimeError(PRIVATE)
        def __str__(self):
            raise AssertionError("must not stringify")
    assert untrusted.public_failure(Hostile()) == f"{untrusted.PUBLIC_FAILURE} (Hostile)"
    malformed = type("private/url", (Exception,), {})
    assert untrusted.public_failure(malformed()) == f"{untrusted.PUBLIC_FAILURE} (Exception)"
    assert untrusted.PUBLIC_FAILURE[0].islower()


def test_frame_failure_keeps_source_identity_without_exception_body():
    from quorum_reasoning import llm
    from quorum_reasoning.nodes import frame
    from test_per_call_failures import _state
    state = _state()
    state['events'][0]['above_bar'] = True
    exc = RuntimeError(PRIVATE)
    exc.status_code = 503
    with patch.object(llm, 'is_dry_run', return_value=False), patch.object(llm, 'json_task', side_effect=exc):
        result = frame.run(state)
    public = json.dumps(result['steps'])
    assert PRIVATE not in public
    names = {d['source_name'] for d in state['documents'] if d['id'] in state['events'][0]['document_ids']}
    assert any(f"{name}: {untrusted.public_failure(exc)}" in public for name in names)
    assert any(name in json.dumps(result['errors']) for name in names)
