"""Verifies the fix for the exact bug hit in production: a genuinely new
email that gets marked \\Seen (by Gmail's own web UI, a phone, anywhere)
before the 3-second poller reaches it must still be caught, because the
listener now tracks the highest UID handled rather than relying on the
UNSEEN flag."""
from __future__ import annotations

import threading
import time

import pytest

from app.listeners import imap_listener as mod


class FakeMailbox:
    """A tiny fake mailbox: messages are (uid, seen, body) tuples. Steps let
    the test script new mail arriving / being marked seen between polls."""

    def __init__(self):
        self.messages = {}  # uid -> {"seen": bool, "body": bytes}
        self.steps = []  # list of callables, one consumed per search() call
        # Set once the one-time connect/backlog scan (the "ALL" search used
        # to establish the starting last_uid baseline) has completed, so
        # tests can wait for that before introducing "new" mail — otherwise
        # there's a race where mail added too early gets swept into the
        # baseline instead of being treated as genuinely new.
        self.backlog_done = threading.Event()

    def add(self, uid, seen, body=b"body"):
        self.messages[uid] = {"seen": seen, "body": body}


class FakeClient:
    instances = []

    def __init__(self, host, use_uid=True):
        self.host = host
        self.use_uid = use_uid
        self.mailbox = mod._TEST_MAILBOX
        FakeClient.instances.append(self)

    def login(self, username, password):
        pass

    def select_folder(self, name):
        pass

    def search(self, criteria):
        # Run any scripted mutation (e.g. "mark uid 5 as seen") for this step.
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


def test_catches_new_mail_marked_seen_before_poll(monkeypatch):
    """Reproduces the exact bug: uid 10 already existed (read) at connect
    time; uid 11 arrives new and unread, but gets marked \\Seen (as if the
    user opened Gmail to check on it) before the listener's next poll. The
    old UNSEEN-only filter would skip it forever. The UID-based fix must
    still catch it, because 11 > last_uid regardless of its seen flag."""
    monkeypatch.setattr(mod, "IMAPClient", FakeClient)
    FakeClient.instances = []

    mailbox = FakeMailbox()
    mailbox.add(10, seen=True)  # pre-existing, already read, ignored at connect
    mod._TEST_MAILBOX = mailbox

    state = mod.ListenerState()
    handled = []
    monkeypatch.setattr(
        state, "_handle_message", lambda raw: handled.append(raw)
    )
    state.start("imap.example.com", "user@example.com", "app-password")

    # Wait for the connect + one-time backlog scan to fully finish (i.e. the
    # baseline last_uid is established) before introducing "new" mail --
    # otherwise it could race and get swept into the baseline instead.
    assert mailbox.backlog_done.wait(timeout=2.0), "connect/backlog scan never completed"

    # New mail arrives unread...
    mailbox.add(11, seen=False, body=b"new phishing test")
    # ...but gets marked seen (simulating the user opening Gmail) before the
    # next scripted search() call runs.
    def _mark_seen(mb):
        mb.messages[11]["seen"] = True

    mailbox.steps.append(_mark_seen)

    assert _wait_until(lambda: len(handled) >= 1, timeout=3.0), (
        "the new message (uid 11) was never handled — the UNSEEN-only bug regressed"
    )
    assert handled[0] == b"new phishing test"

    state.stop()


def test_server_quirk_does_not_cause_duplicate_reprocessing(monkeypatch):
    """Some IMAP servers return the highest-UID message for a "UID n:*"
    search where n exceeds any real UID, instead of an empty set. Make sure
    that doesn't cause the same message to be re-handled every poll."""
    monkeypatch.setattr(mod, "IMAPClient", FakeClient)
    FakeClient.instances = []

    mailbox = FakeMailbox()
    mailbox.add(5, seen=True)
    mod._TEST_MAILBOX = mailbox

    # Force every UID search to buggily return [5] regardless of the
    # requested start, mimicking the server quirk.
    orig_search = FakeClient.search

    def buggy_search(self, criteria):
        if criteria[0] == "UID":
            return [5]
        return orig_search(self, criteria)

    monkeypatch.setattr(FakeClient, "search", buggy_search)

    state = mod.ListenerState()
    state.start("imap.example.com", "user@example.com", "app-password")

    handled = []
    monkeypatch.setattr(state, "_handle_message", lambda raw: handled.append(raw))

    # Let several poll cycles happen.
    time.sleep(0.2)
    assert handled == [], "uid 5 (<= last_uid) must never be re-handled despite the server quirk"

    state.stop()
