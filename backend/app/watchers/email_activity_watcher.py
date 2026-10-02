"""
Ties PhishMind's inbox scanning to whether the user actually has email open,
instead of scanning 24/7. The idea: start the IMAP listener the moment a
Gmail/Outlook window shows up, keep scanning while it's open, and stop again
once it's closed (after a short grace period so switching tabs briefly
doesn't stop/start scanning constantly).

Split into two pieces on purpose:
  - EmailActivityWatcher: a pure state machine (open/closed + grace period ->
    start/stop callbacks). No OS calls, fully unit-testable with a fake
    detector, fake clock and fake sleep.
  - _detect_email_window: the actual Windows window-title check. Windows-only
    (uses ctypes to call user32.dll directly, no extra dependency needed);
    quietly returns False everywhere else so importing/using this module
    never breaks a non-Windows dev machine or CI.
"""
from __future__ import annotations

import logging
import platform
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("phishmind.email_watcher")


def _detect_email_window(keywords: list[str]) -> bool:
    """Return True if any visible top-level window's title contains one of
    `keywords` (case-insensitive) — e.g. a browser tab titled
    "Inbox (3) - user@gmail.com - Gmail", or the Outlook desktop app."""
    if platform.system() != "Windows" or not keywords:
        return False

    import ctypes

    found = False
    user32 = ctypes.windll.user32
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)

    def _callback(hwnd, _lparam):
        nonlocal found
        if not user32.IsWindowVisible(hwnd):
            return 1  # keep enumerating
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return 1
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = (buffer.value or "").lower()
        if any(keyword in title for keyword in keywords):
            found = True
            return 0  # stop enumerating, we found a match
        return 1

    try:
        user32.EnumWindows(EnumWindowsProc(_callback), 0)
    except Exception:
        logger.exception("Window enumeration failed; treating email as closed for this check")
        return False
    return found


class EmailActivityWatcher:
    """Starts/stops scanning based on whether an email window is open.

    `on_email_open` / `on_email_closed` are called at most once per
    open/close transition (not on every poll), so they're safe to wire
    directly to listener_state.start()/stop().
    """

    def __init__(
        self,
        on_email_open: Callable[[], None],
        on_email_closed: Callable[[], None],
        is_email_open: Optional[Callable[[], bool]] = None,
        keywords: Optional[list[str]] = None,
        poll_seconds: float = 5.0,
        grace_seconds: float = 30.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        clock_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.on_email_open = on_email_open
        self.on_email_closed = on_email_closed
        self._keywords = keywords or []
        self.is_email_open = is_email_open or (lambda: _detect_email_window(self._keywords))
        self.poll_seconds = poll_seconds
        self.grace_seconds = grace_seconds
        self._sleep = sleep_fn
        self._clock = clock_fn

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.scanning_active = False
        self.last_seen_open_at: Optional[float] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def status(self) -> dict:
        return {
            "scanning_active": self.scanning_active,
            "last_seen_open_at": self.last_seen_open_at,
        }

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.tick()
            self._sleep(self.poll_seconds)

    def tick(self) -> None:
        """Evaluate current state once and fire callbacks on transitions.
        Public and side-effect-isolated so tests can drive it directly
        without spinning up a real thread."""
        try:
            open_now = bool(self.is_email_open())
        except Exception:
            logger.exception("Email-open check failed; assuming closed for this check")
            open_now = False

        now = self._clock()

        if open_now:
            self.last_seen_open_at = now
            if not self.scanning_active:
                self.scanning_active = True
                self._safe_call(self.on_email_open)
        else:
            grace_expired = (
                self.last_seen_open_at is not None
                and (now - self.last_seen_open_at) >= self.grace_seconds
            )
            if self.scanning_active and grace_expired:
                self.scanning_active = False
                self._safe_call(self.on_email_closed)

    @staticmethod
    def _safe_call(fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception:
            logger.exception("Email-activity callback raised (continuing anyway)")
