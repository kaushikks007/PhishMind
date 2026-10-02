"""Regression test for the bug hit in production on 2026-09-26: the first
email after a (re)connect got scanned, but nothing after that did, on an
otherwise perfectly healthy, still-open connection (no errors, no
reconnects). Root cause: Gmail's IMAP connection does not spontaneously
notice mail that arrives after SELECT — a client has to issue a command
(NOOP is the standard, side-effect-free choice) for the server to refresh
what that connection can see. The poll loop was doing a bare SEARCH every
tick with nothing to trigger that refresh, so on a server with this
behavior, SEARCH kept evaluating against the stale view from connect time.

This fake client models exactly that: new mail only becomes visible to
`search()` after `noop()` has been called at least once since it arrived.
"""
from __future__ import annotations

import threading
import time

import pytest

from app.listeners import imap_listener as mod


class NoopGatedMailbox:
    def __init__(self):
        self.messages = {}  # uid -> {"visible": bool, "body": bytes}
        self.backlog_done = threading.Event()

    def add_hidden_until_noop(self, uid, body):
        """Simulates mail that has arrived server-side but isn't visible to
        this connection's SEARCH yet — matching real Gmail behavior — until
        a NOOP refreshes the connection's view."""
        self.messages[uid] = {"visible": False, "body": body}


class NoopGatedClient:
    instances = []

    def __init__(self, host, use_uid=True, timeout=None):
        self.mailbox = mod._TEST_MAILBOX
        NoopGatedClient.instances.append(self)

    def login(self, username, password):
        pass

    def select_folder(self, name):
        pass

    def noop(self):
        # This is the refresh: only after a NOOP does previously-hidden mail
        # become visible to subsequent searches.
        for m in self.mailbox.messages.values():
            m["visible"] = True

    def search(self, criteria):
        if criteria == ["UNSEEN"]:
            return []
        if criteria == ["ALL"]:
            self.mailbox.backlog_done.set()
            return []
        if criteria[0] == "UID":
            start = int(criteria[1].split(":")[0])
            return sorted(
                u for u, m in self.mailbox.messages.items() if u >= start and m["visible"]
            )
        return []

    def fetch(self, uids, parts):
        return {u: {b"RFC822": self.mailbox.messages[u]["body"]} for u in uids if u in self.mailbox.messages}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)


def _wait_until(predicate, timeout=2.0):
    deadline = time.perf_counter() + timeout
    ready = threading.Event()
    while time.perf_counter() < deadline:
        if predicate():
            return True
        ready.wait(0.02)
    return False


def test_poll_loop_calls_noop_so_new_mail_on_a_stable_connection_is_seen(monkeypatch):
    monkeypatch.setattr(mod, "IMAPClient", NoopGatedClient)
    NoopGatedClient.instances = []

    mailbox = NoopGatedMailbox()
    mod._TEST_MAILBOX = mailbox

    state = mod.ListenerState()
    handled = []
    monkeypatch.setattr(state, "_handle_message", lambda raw: handled.append(raw))
    state.start("imap.example.com", "user@example.com", "app-password")

    assert mailbox.backlog_done.wait(timeout=2.0), "initial connect/backlog scan never completed"

    # Mail arrives on an already-open, otherwise healthy connection -- no
    # error, no reconnect. Without a NOOP in the poll loop, this fake client
    # would never make it visible to search(), reproducing the exact
    # production symptom: first mail (via the backlog scan) works, this one
    # never does.
    mailbox.add_hidden_until_noop(11, b"second email, same connection")

    assert _wait_until(lambda: len(handled) >= 1, timeout=3.0), (
        "the second email on the same still-open connection was never handled — "
        "the poll loop isn't calling noop() to refresh Gmail's view of the mailbox"
    )
    assert handled[0] == b"second email, same connection"
    assert len(NoopGatedClient.instances) == 1, "this must work without any reconnect"

    state.stop()
