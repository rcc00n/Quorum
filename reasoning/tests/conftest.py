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

DECISION(2026-10-25, Yelysei Shkirpan/Claude Code): the same guard is also installed for the whole session, from
`pytest_configure` (before collection) to `pytest_unconfigure`, so test-module imports and fixtures of every scope
(session, module, class) run under it too; what it records outside a test function fails the session's last teardown
(`no_real_control_plane_outside_tests`), also when that code caught the failure. The per-test guard above stays on top
of it. Because the session guard replaces the seams before test modules are imported, the guard's proof takes the
unguarded seams from the `unguarded_control_seams` fixture (captured when this file was imported), never from a
capture in a test module. Why: final review round 2: the guard was a function-scoped fixture only, so a module-scoped
fixture that forgot the stub ran with METERLESS_CONTROL_SOCKET unset and the real seams and opened the derived pipe
name, the daemon's real pipe on a real profile (tests/test_graph.py, tests/test_injection.py and
tests/test_provenance.py drive the graph from module-scoped fixtures).
"""

from __future__ import annotations

import functools

import pytest

from quorum_reasoning import llm

NO_SUCH_PIPE = r"\\.\pipe\quorum-test-no-such-pipe"
# captured at import, before the session guard (pytest_configure) or any test replaces them
REAL_CONTROL_EXCHANGE = llm._control_exchange
REAL_OPEN_PIPE = llm._open_pipe
REAL_WAIT_NAMED_PIPE = llm._wait_named_pipe

IN_A_TEST = "a test"
OUTSIDE_TESTS = "code outside a test function (a test module's import or a session-, module- or class-scoped fixture)"
_SESSION_GUARD = pytest.MonkeyPatch()
OUTSIDE_TESTS_REACHED: list[str] = []  # what the session guard recorded; re-checked when the session ends


def _is_real_control_plane(where: object) -> bool:
    """The daemon's own pipe (transport.mjs: ai.meterless.runtime-<userKey>-runtime) or the packaged Unix socket."""
    return "ai.meterless.runtime" in str(where).lower() or str(where) == llm.CONTROL_SOCKET_POSIX


def _request_line(request: object) -> str:
    return bytes(request).split(b"\r\n", 1)[0].decode("ascii", "replace") if isinstance(request, (bytes, bytearray)) else "?"


def _refusing_real_names(real, what: str, reached: list[str], who: str = IN_A_TEST):
    """`real` behind a check that fails the test (and records it for the teardown re-check) on the real pipe/socket."""

    @functools.wraps(real)
    def guarded(where, *args, **kwargs):
        if _is_real_control_plane(where):
            reached.append(f"{what} on {where}")
            pytest.fail(f"{who} reached the daemon's real control pipe or socket through llm.{what}: {where}", pytrace=False)
        return real(where, *args, **kwargs)

    return guarded


def _install_guard(mp: pytest.MonkeyPatch, reached: list[str], who: str, hint: str) -> None:
    """The control pipe's name becomes a pipe that does not exist, any control-plane exchange fails, and opening or
    waiting on the daemon's real pipe or socket fails too; every hit is appended to `reached`."""

    def blocked(where, request, timeout=None):
        reached.append(f"{_request_line(request)} on {where}")
        pytest.fail(f"{who} reached the Meterless control plane unfaked: {reached[-1]} ({hint})", pytrace=False)

    mp.setenv("METERLESS_CONTROL_SOCKET", NO_SUCH_PIPE)
    mp.setattr(llm, "_control_exchange", blocked)
    mp.setattr(llm, "_open_pipe", _refusing_real_names(REAL_OPEN_PIPE, "_open_pipe", reached, who))
    mp.setattr(llm, "_wait_named_pipe", _refusing_real_names(REAL_WAIT_NAMED_PIPE, "_wait_named_pipe", reached, who))


def pytest_configure(config):
    """The session guard: in place before any test module is imported and until the session is unconfigured."""
    _install_guard(_SESSION_GUARD, OUTSIDE_TESTS_REACHED, OUTSIDE_TESTS, "fake llm._control_http")


def pytest_unconfigure(config):
    _SESSION_GUARD.undo()


@pytest.fixture(scope="session", autouse=True)
def no_real_control_plane_outside_tests():
    """Autouse, session-scoped (set up first, torn down last): fails the session's last teardown when code outside a
    test function reached the control plane, also when that code caught the failure."""
    yield OUTSIDE_TESTS_REACHED
    if OUTSIDE_TESTS_REACHED:
        pytest.fail(f"{OUTSIDE_TESTS} reached the Meterless control plane unfaked: {'; '.join(OUTSIDE_TESTS_REACHED)}",
                    pytrace=False)


@pytest.fixture(autouse=True)
def no_real_control_plane(monkeypatch):
    """Autouse: the control pipe's name is a pipe that does not exist, any control-plane exchange fails the test, and
    opening or waiting on the daemon's real pipe or socket fails it too."""
    reached: list[str] = []
    _install_guard(monkeypatch, reached, IN_A_TEST,
                   "fake llm._control_http, or ask for the real_control_exchange fixture with a fake open")
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


@pytest.fixture
def unguarded_control_seams():
    """For the guard's own proof only (tests/test_meterless_route.py): the three seams as llm defines them, captured when
    this file was imported, before the session guard replaced them."""
    return {"_control_exchange": REAL_CONTROL_EXCHANGE, "_open_pipe": REAL_OPEN_PIPE, "_wait_named_pipe": REAL_WAIT_NAMED_PIPE}
