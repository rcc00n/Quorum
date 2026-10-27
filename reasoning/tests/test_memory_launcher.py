"""Launcher proposal only: no graph adoption or Windows execution claim."""
from pathlib import Path
from unittest.mock import patch
import pytest
from quorum_reasoning.tools import memory


def test_default_launcher_preserves_paths_with_spaces_without_shell(tmp_path, monkeypatch):
    monkeypatch.delenv('QUORUM_HMEM_TSX', raising=False)
    home = tmp_path / 'reference checkout'
    cli = home / 'engines/hmem/reference/node_modules/tsx/dist/cli.mjs'
    cli.parent.mkdir(parents=True)
    cli.touch()
    with patch.object(memory.shutil, 'which', return_value='C:/Program Files/nodejs/node.exe'):
        assert memory._launcher(home) == ['C:/Program Files/nodejs/node.exe', str(cli)]


def test_missing_runtime_fails_closed_and_explicit_override_stays_one_argument(tmp_path, monkeypatch):
    monkeypatch.delenv('QUORUM_HMEM_TSX', raising=False)
    with patch.object(memory.shutil, 'which', return_value=None), pytest.raises(ValueError):
        memory._launcher(tmp_path)
    monkeypatch.setenv('QUORUM_HMEM_TSX', '/TEST custom executable/tsx')
    assert memory._launcher(tmp_path) == ['/TEST custom executable/tsx']
