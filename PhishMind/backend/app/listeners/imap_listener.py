"""
Real-time inbox scanning via IMAP IDLE. Runs in a background thread (IMAP
IDLE is a blocking protocol), parses each new message through the exact same
pipeline as a manual scan, stores the result, and pushes it onto a
thread-safe queue that the SSE endpoint (/api/v1/listener/events) drains for
the frontend's live demo view.

Never crashes the server: all IMAP/network errors are caught and logged, and
the listener reports itself as stopped with a reason rather than killing the
process.
"""
from __future__ import annotations

import logging
import queue
import threading
import time

from imapclient import IMAPClient

from app.config import settings
from app.db.database import save_scan_result
from app.notifications import notify_scan_result
from app.parsing.email_parser import parse_eml_bytes
from app.pipeline import run_pipeline

logger = logging.getLogger("phishmind.imap_listener")


class ListenerState:
    """Thread-safe singleton tracking the background IMAP listener."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.running = False
        self.username: str | None = None
        self.last_error: str | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.events: "queue.Queue[dict]" = queue.Queue()

    def status(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "username": self.username,
                "last_error": self.last_error,
            }

    def start(self, host: str, username: str, app_password: str) -> None:
        with self._lock:
            if self.running:
                raise RuntimeError("Listener is already running. Stop it before starting a new one.")
            self._stop_event.clear()
            self.running = True
            self.username = username
            self.last_error = None
            self._thread = threading.Thread(
                target=self._run,
                args=(host, username, app_password),
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            self.running = False

    def _run(self, host: str, username: str, app_password: str) -> None:
        # Long-lived IMAP connections can be silently dropped by the mail
        # server (idle timeouts, network blips) with no exception raised
        # until the next command is sent. The original version of this loop
        # caught that failure, logged it, and just kept retrying forever on
        # the SAME dead connection object — so `listener/status` would keep
        # reporting `running: true` while the listener had actually stopped
        # catching anything. This version distinguishes two situations:
        #   - never managed to connect/login even once -> almost certainly a
        #     permanent config problem (bad host/username/App Password), so
        #     stop and surface the error rather than hammering Gmail's login.
        #   - was connected and working, then the connection dropped -> most
        #     likely transient, so reconnect automatically with backoff.
        ever_connected = False
        backoff = 3
        max_backoff = 60
        # Tracked OUTSIDE the reconnect loop on purpose. It used to live
        # inside the `with IMAPClient(...)` block and get reset to 0 on every
        # reconnect, which meant a dropped-connection blip re-triggered the
        # \Seen-flag-based catch-up scan below, silently re-introducing the
        # race that catch-up was supposed to have been retired for after the
        # first connect. A reconnect now resumes exactly where the UID-based
        # tracking left off.
        last_uid = 0

        while not self._stop_event.is_set():
            try:
                # A `timeout` is required here: without one, the underlying
                # socket blocks forever on a stalled connection (a dropped
                # Wi-Fi packet the OS never sends a RST for, a sleeping
                # laptop, a flaky network hop). That kind of stall raises no
                # exception at all, so the reconnect-with-backoff logic below
                # never even gets a chance to run -- the thread just sits
                # frozen inside client.search()/fetch() indefinitely, still
                # reporting `running: true`, while genuinely new mail piles
                # up unseen. A timeout turns a silent hang into a normal
                # exception, which IS handled below.
                with IMAPClient(host, use_uid=True, timeout=30) as client:
                    client.login(username, app_password)
                    client.select_folder("INBOX")
                    logger.info("PhishMind background guard active for %s", username)
                    with self._lock:
                        self.last_error = None
                    is_first_connection = not ever_connected
                    ever_connected = True
                    backoff = 3
                    consecutive_failures = 0

                    # One-time catch-up on whatever's currently unread — only
                    # on the very first connection this thread makes. After
                    # that we switch to tracking the highest UID we've
                    # handled rather than relying on the \Seen flag — reading
                    # a message in Gmail's own app, on your phone, or in any
                    # other mail client marks it seen too, and a poller that
                    # only asks "what's unread" would then silently skip a
                    # genuinely new email. A RECONNECT must never redo this
                    # \Seen-based sweep: last_uid already knows the true
                    # high-water mark, seen flags be damned.
                    if is_first_connection:
                        try:
                            backlog = client.search(["UNSEEN"])
                            if backlog:
                                for msg_id, data in client.fetch(backlog, ["RFC822"]).items():
                                    raw_message = data.get(b"RFC822")
                                    if raw_message:
                                        self._handle_message(raw_message)
                                last_uid = max(last_uid, max(backlog))
                            all_uids = client.search(["ALL"])
                            if all_uids:
                                last_uid = max(last_uid, max(all_uids))
                        except Exception:
                            logger.exception(
                                "Error scanning initial backlog; continuing with live-only scanning"
                            )

                    while not self._stop_event.is_set():
                        try:
                            # This NOOP is the actual fix for "the first
                            # email after a restart gets caught, nothing
                            # after that does": Gmail's IMAP connection does
                            # not spontaneously notice mail that arrives
                            # after SELECT — it only refreshes its view of
                            # the mailbox (new EXISTS/UID range) as a side
                            # effect of a command being sent, and a bare
                            # SEARCH on some servers does not trigger that
                            # refresh, so repeated SEARCHes on the same
                            # still-open connection kept silently evaluating
                            # against the stale view from connect time. A
                            # NOOP forces the refresh every poll tick, so the
                            # very next SEARCH actually sees new mail instead
                            # of only picking it up once the connection drops
                            # and reconnects (a fresh SELECT).
                            client.noop()
                            candidates = client.search(["UID", f"{last_uid + 1}:*"])
                            # Some IMAP servers interpret "UID n:*" as "n or
                            # the highest UID, whichever is greater" when n
                            # exceeds any UID that actually exists, instead
                            # of an empty result — which would otherwise
                            # re-deliver the same last message forever. This
                            # filter makes that quirk harmless.
                            new_uids = [uid for uid in candidates if uid > last_uid]
                            if new_uids:
                                for msg_id, data in client.fetch(new_uids, ["RFC822"]).items():
                                    raw_message = data.get(b"RFC822")
                                    if not raw_message:
                                        continue
                                    self._handle_message(raw_message)
                                last_uid = max(last_uid, max(new_uids))
                            consecutive_failures = 0
                        except Exception:
                            consecutive_failures += 1
                            logger.exception(
                                "Error while polling inbox (failure %d/3)", consecutive_failures
                            )
                            if consecutive_failures >= 3:
                                logger.warning(
                                    "Too many consecutive polling failures on %s — reconnecting.",
                                    host,
                                )
                                break  # drop out to the outer loop and reconnect fresh
                        time.sleep(3)
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                if not ever_connected:
                    logger.exception("IMAP listener failed to start")
                    with self._lock:
                        self.running = False
                        self.last_error = str(exc)
                    return
                logger.exception(
                    "IMAP connection to %s lost — reconnecting in %ds", host, backoff
                )
                with self._lock:
                    self.last_error = f"Connection lost, reconnecting: {exc}"
                time.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
                continue

        with self._lock:
            self.running = False

    def _handle_message(self, raw_message: bytes) -> None:
        try:
            email_data = parse_eml_bytes(raw_message)
            result = run_pipeline(email_data)
            scan_id = save_scan_result(result, source="imap_live")
            result["id"] = str(scan_id)
            self.events.put(result)
            if settings.desktop_notifications:
                notify_scan_result(result)
            logger.info(
                "New mail scanned: %s -> %s (%s/100)",
                result.get("subject", ""),
                result.get("verdict"),
                result.get("risk_score"),
            )
        except Exception:
            logger.exception("Failed to process incoming message")


listener_state = ListenerState()
