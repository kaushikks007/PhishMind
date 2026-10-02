"""Sanity test for the reconnect-on-dropped-connection fix in imap_listener.

Simulates: a successful initial connect, some transient polling failures
that should trigger a forced reconnect, and a connection that raises inside
the `with IMAPClient(...)` block (mimicking a server-side disconnect) — the
listener should reconnect automatically rather than giving up, and never
report `running: False` while doing so.
"""
from __future__ import annotations

import threading
import time

import pytest

from app.listeners import imap_listener as mod


class FakeClient:
    """Stands in for imapclient.IMAPClient. `behavior` is a list of steps
    consumed one at a time across calls to search(); once exhausted it just
    keeps returning no messages."""

    instances = []

    def __init__(self, host, use_uid=True):
        self.host = host
        self.use_uid = use_uid
        self.logged_in = False
        self.selected = False
        FakeClient.instances.append(self)

    def login(self, username, password):
        self.logged_in = True

    def select_folder(self, name):
        self.selected = True

    def search(self, criteria):
        # The one-time connect/backlog scan (UNSEEN, then ALL) always
        # succeeds trivially here — the simulated failures below are only
        # for the live polling loop's UID-based search, which is what this
        # test is actually exercising.
        if not criteria or criteria[0] != "UID":
            return []
        step = mod._TEST_BEHAVIOR.pop(0) if mod._TEST_BEHAVIOR else "ok"
        if step == "raise_in_search":
            raise ConnectionResetError("simulated dropped connection")
        return []

    def fetch(self, messages, parts):
        return {}

    def noop(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    # Don't actually wait through the real 3s poll interval / backoff during
    # the test.
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)


def test_reconnects_after_dropped_connection(monkeypatch):
    monkeypatch.setattr(mod, "IMAPClient", FakeClient)
    FakeClient.instances = []
    # 3 consecutive polling failures forces the inner loop to break and
    # reconnect (a fresh `with IMAPClient(...)` block / new instance).
    mod._TEST_BEHAVIOR = ["raise_in_search", "raise_in_search", "raise_in_search"]

    state = mod.ListenerState()
    state.start("imap.example.com", "user@example.com", "app-password")

    # Give the background thread a moment to run through the simulated
    # failures and reconnect.
    ready = threading.Event()
    deadline = time.perf_counter() + 2.0
    while time.perf_counter() < deadline:
        if len(FakeClient.instances) >= 2:
            break
        ready.wait(0.02)

    status = state.status()
    assert status["running"] is True, "listener should still report running while reconnecting"
    assert len(FakeClient.instances) >= 2, "expected a fresh IMAPClient instance after reconnect"

    state.stop()


def test_never_connected_surfaces_error_and_stops(monkeypatch):
    class AlwaysFailsClient(FakeClient):
        def login(self, username, password):
            raise ValueError("bad credentials")

    monkeypatch.setattr(mod, "IMAPClient", AlwaysFailsClient)

    state = mod.ListenerState()
    state.start("imap.example.com", "user@example.com", "wrong-password")

    ready = threading.Event()
    deadline = time.perf_counter() + 2.0
    while time.perf_counter() < deadline:
        if not state.status()["running"]:
            break
        ready.wait(0.02)

    status = state.status()
    assert status["running"] is False
    assert "bad credentials" in (status["last_error"] or "")
