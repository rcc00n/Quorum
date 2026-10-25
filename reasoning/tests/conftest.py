"""Suite-wide guard: no test reaches the real Meterless control plane (2026-10-25).

DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): every test runs with METERLESS_CONTROL_SOCKET pointing at a pipe
that does not exist and with three seams of llm guarded: `llm._control_exchange` (the request/response exchange on the
pipe or socket) is replaced by a stub that fails the test; `llm._open_pipe` (the code that opens the pipe) and
`llm._wait_named_pipe` (WaitNamedPipeW, the busy-pipe wait) still run but refuse the daemon's real pipe and socket by
name. Every refusal is recorded and fails the test again at teardown if the test swallowed it. A test that drives the
real exchange through a fake `open` asks for the `real_control_exchange` fixture, which still refuses the real pipe and
socket by name; a test that fakes `llm._control_http` or `llm._control_exchange` itself needs nothing. Why: review
rounds 1-3 of the H-MEM change: the guard lived in tests/test_meterless_route.py only, so a test elsewhere that drove a
live `run.main` on a Meterless route POSTed to the live daemon (coordinator decision 2, round 3); review round 4: the
stub covered `_control_exchange` only, so a test calling `llm._open_pipe` on the derived name opened the real pipe.
tests/test_meterless_route.py › test_suite_guard_fails_a_test_that_forgets_the_stub proves every layer with inner
pytest sessions run in this process (no `pytest_plugins` here: a non-top-level conftest may not declare it).
"""

from __future__ import annotations

import functools

import pytest

from quorum_reasoning import llm

NO_SUCH_PIPE = r"\\.\pipe\quorum-test-no-such-pipe"
# captured at import, before any test replaces them
REAL_CONTROL_EXCHANGE = llm._control_exchange
REAL_OPEN_PIPE = llm._open_pipe
REAL_WAIT_NAMED_PIPE = llm._wait_named_pipe


def _is_real_control_plane(where: object) -> bool:
    """The daemon's own pipe (transport.mjs: ai.meterless.runtime-<userKey>-runtime) or the packaged Unix socket."""
    return "ai.meterless.runtime" in str(where).lower() or str(where) == llm.CONTROL_SOCKET_POSIX


def _request_line(request: object) -> str:
    return bytes(request).split(b"\r\n", 1)[0].decode("ascii", "replace") if isinstance(request, (bytes, bytearray)) else "?"


def _refusing_real_names(real, what: str, reached: list[str]):
    """`real` behind a check that fails the test (and records it for the teardown re-check) on the real pipe/socket."""

    @functools.wraps(real)
    def guarded(where, *args, **kwargs):
        if _is_real_control_plane(where):
            reached.append(f"{what} on {where}")
            pytest.fail(f"a test reached the daemon's real control pipe or socket through llm.{what}: {where}", pytrace=False)
        return real(where, *args, **kwargs)

    return guarded


@pytest.fixture(autouse=True)
def no_real_control_plane(monkeypatch):
    """Autouse: the control pipe's name is a pipe that does not exist, any control-plane exchange fails the test, and
    opening or waiting on the daemon's real pipe or socket fails it too."""
    reached: list[str] = []

    def blocked(where, request, timeout=None):
        reached.append(f"{_request_line(request)} on {where}")
        pytest.fail(f"a test reached the Meterless control plane unfaked: {reached[-1]} (fake llm._control_http, or "
                    "ask for the real_control_exchange fixture with a fake open)", pytrace=False)

    monkeypatch.setenv("METERLESS_CONTROL_SOCKET", NO_SUCH_PIPE)
    monkeypatch.setattr(llm, "_control_exchange", blocked)
    monkeypatch.setattr(llm, "_open_pipe", _refusing_real_names(REAL_OPEN_PIPE, "_open_pipe", reached))
    monkeypatch.setattr(llm, "_wait_named_pipe", _refusing_real_names(REAL_WAIT_NAMED_PIPE, "_wait_named_pipe", reached))
    yield reached
    if reached:  # also when the test caught the failure above
        pytest.fail(f"a test reached the Meterless control plane unfaked: {'; '.join(reached)}", pytrace=False)


@pytest.fixture
def real_control_exchange(no_real_control_plane, monkeypatch):
    """Opt-in for tests that drive the real `llm._control_exchange` through a fake `open`: installs it behind a check
    that still refuses the daemon's real pipe or socket by name; returns the unwrapped function."""

    @functools.wraps(REAL_CONTROL_EXCHANGE)
    def guarded(where, request, *args, **kwargs):
        if _is_real_control_plane(where):
            no_real_control_plane.append(f"{_request_line(request)} on {where}")
            pytest.fail(f"a test sent a control-plane request to the daemon's real pipe or socket: {where}", pytrace=False)
        return REAL_CONTROL_EXCHANGE(where, request, *args, **kwargs)

    monkeypatch.setattr(llm, "_control_exchange", guarded)
    return REAL_CONTROL_EXCHANGE
