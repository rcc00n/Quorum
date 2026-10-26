"""Negative audit cases use dedicated TEST stores and protected temporary files only."""
from unittest.mock import patch
import pytest
from test_source_memory import state, live_memory, TEXT
from quorum_reasoning.tools import memory


def symlink_or_skip(link, target, **kw):
    # DECISION(2026-10-26, Yelysei Shkirpan/Claude Code): a symlink test skips when the OS refuses to create the link.
    # Why: Windows creates symlinks only with Developer Mode or elevation (WinError 1314); the store check itself
    # (sidecar.mjs inspectStore) is unchanged and still rejects links where they exist.
    try:link.symlink_to(target,**kw)
    except OSError as exc:pytest.skip(f'symlinks unavailable here ({type(exc).__name__})')


def test_symlinked_state_is_rejected_without_reading_or_mutating_target(live_memory,tmp_path):
    s=state();memory.remember(s,[])
    original=(live_memory/'state.json').read_bytes()
    target=tmp_path/'TEST-protected.json';target.write_bytes(original)
    (live_memory/'state.json').unlink();symlink_or_skip(live_memory/'state.json',target)
    with pytest.raises(Exception):memory._call(s,'recall',query=TEXT)
    assert target.read_bytes()==original


def test_symlinked_root_is_rejected(live_memory,tmp_path,monkeypatch):
    s=state();memory.remember(s,[])
    link=tmp_path/'TEST-link';symlink_or_skip(link,live_memory,target_is_directory=True)
    monkeypatch.setenv('QUORUM_HMEM_DIR',str(link))
    with pytest.raises(Exception):memory._call(s,'recall',query=TEXT)


def test_invalid_marker_does_not_claim_an_unrelated_directory(live_memory):
    live_memory.mkdir();marker=live_memory/'quorum-source-memory-v1';marker.write_text('TEST unrelated marker')
    with pytest.raises(Exception):memory._call(state(),'store',rows=[])
    assert list(live_memory.iterdir())==[marker]


@pytest.mark.parametrize('change',[lambda r:r['docref'].update(id=2.0),lambda r:r['docref'].update(access_level=True),lambda r:r.update(fictional=1)])
def test_recall_identity_is_type_exact(live_memory,change):
    s=state();memory.remember(s,[])
    response=memory._call(s,'recall',query=TEXT);change(response['rows'][0]['record'])
    with patch.object(memory,'_call',return_value=response):
        ordered,steps,errors=memory.prioritize(s,'TEST-event',TEXT,s['documents'])
    assert ordered==s['documents'] and not errors and 'recalled 0' in steps[0]['decision']


def test_hardlinked_ledger_is_rejected(live_memory,tmp_path):
    import os
    s=state();memory.remember(s,[])
    ledger=live_memory/'ledger.jsonl';target=tmp_path/'TEST-protected-ledger'
    os.link(ledger,target);original=target.read_bytes()
    with pytest.raises(Exception):memory._call(s,'recall',query=TEXT)
    assert target.read_bytes()==original
