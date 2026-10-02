"""Regression test for the bug hit in production on 2026-09-26: a message
that arrives during a brief connection drop, and gets marked \\Seen (by
Gmail's own preview/indexing, or anything else) before the reconnect's
one-time backlog scan runs, must still be caught — because `last_uid` is now
tracked outside the `with IMAPClient(...)` block and survives a reconnect,
so a reconnect never re-runs the \\Seen-flag-based catch-up and can never
silently fold a genuinely new UID into its baseline.
"""
from __future__ import annotations

import threading
import time

import pytest

from app.listeners import imap_listener as mod


class FakeMailbox:
    def __init__(self):
        self.messages = {}  # uid -> {"seen": bool, "body": bytes}
        self.steps = []  # one-shot callables, each consumed by the next search()
        self.backlog_done = threading.Event()

    def add(self, uid, seen, body=b"body"):
        self.messages[uid] = {"seen": seen, "body": body}


class FakeClient:
    instances = []

    def __init__(self, host, use_uid=True, timeout=None):
        self.host = host
        self.use_uid = use_uid
        self.mailbox = mod._TEST_MAILBOX
        FakeClient.instances.append(self)

    def login(self, username, password):
        pass

    def select_folder(self, name):
        pass

    def search(self, criteria):
        if self.mailbox.steps:
            step = self.mailbox.steps.pop(0)
            step(self.mailbox)

        if criteria == ["UNSEEN"]:
            return sorted(u for u, m in self.mailbox.messages.items() if not m["seen"])
        if criteria == ["ALL"]:
            result = sorted(self.mailbox.messages.keys())
            self.mailbox.backlog_done.set()
            return result
        if criteria[0] == "UID":
            start = int(criteria[1].split(":")[0])
            return sorted(u for u in self.mailbox.messages if u >= start)
        return []

    def fetch(self, uids, parts):
        return {u: {b"RFC822": self.mailbox.messages[u]["body"]} for u in uids if u in self.mailbox.messages}

    def noop(self):
        pass

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


def test_reconnect_does_not_swallow_mail_marked_seen_during_outage(monkeypatch):
    monkeypatch.setattr(mod, "IMAPClient", FakeClient)
    FakeClient.instances = []

    mailbox = FakeMailbox()
    mailbox.add(10, seen=True)  # pre-existing baseline
    mod._TEST_MAILBOX = mailbox

    state = mod.ListenerState()
    handled = []
    monkeypatch.setattr(state, "_handle_message", lambda raw: handled.append(raw))
    state.start("imap.example.com", "user@example.com", "app-password")

    assert mailbox.backlog_done.wait(timeout=2.0), "initial connect/backlog scan never completed"

    # Force the very next UID search (the live poll loop's first tick) to
    # blow up, simulating the connection dropping right as new mail arrives.
    original_search = FakeClient.search

    def _drop_once(self, criteria):
        if criteria and criteria[0] == "UID":
            FakeClient.search = original_search  # only drop once
            raise ConnectionResetError("simulated dropped connection")
        return original_search(self, criteria)

    FakeClient.search = _drop_once

    # New mail arrives during the outage, and — same as the production
    # incident — gets marked \Seen before anything gets a chance to notice
    # it, e.g. Gmail's own preview fetch.
    mailbox.add(11, seen=True, body=b"mail sent during the outage")

    assert _wait_until(lambda: len(FakeClient.instances) >= 2, timeout=3.0), (
        "expected a reconnect (fresh IMAPClient instance) after the dropped connection"
    )

    assert _wait_until(lambda: len(handled) >= 1, timeout=3.0), (
        "uid 11 was never handled — the reconnect re-ran the \\Seen-based catch-up "
        "and silently swallowed mail that arrived during the outage"
    )
    assert handled[0] == b"mail sent during the outage"

    state.stop()
