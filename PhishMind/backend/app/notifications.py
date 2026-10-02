"""
Native OS desktop notifications for live-detected phishing/suspicious mail.

This is what makes the background listener feel "alive" without the
dashboard open: a real Windows toast pops up the moment a bad email is
caught. Windows-only (uses win10toast); on any other platform, or if the
notification library/backend isn't available, this quietly no-ops and logs
instead of failing the scan.
"""
from __future__ import annotations

import logging
import platform

logger = logging.getLogger("phishmind.notifications")

_toaster = None
_toaster_init_attempted = False


def _get_toaster():
    global _toaster, _toaster_init_attempted
    if _toaster_init_attempted:
        return _toaster
    _toaster_init_attempted = True

    if platform.system() != "Windows":
        return None

    try:
        from win10toast import ToastNotifier  # type: ignore

        _toaster = ToastNotifier()
    except Exception:
        logger.info("win10toast not available; desktop notifications disabled.")
        _toaster = None
    return _toaster


def notify_scan_result(result: dict) -> None:
    """Fire a toast for a PHISHING/SUSPICIOUS live scan result. Never raises."""
    verdict = result.get("verdict")
    if verdict not in ("PHISHING", "SUSPICIOUS"):
        return

    toaster = _get_toaster()
    if toaster is None:
        return

    icon = "PHISHING ALERT" if verdict == "PHISHING" else "Suspicious email"
    title = f"PhishMind: {icon}"
    subject = result.get("subject", "(no subject)")
    sender = result.get("sender", "unknown sender")
    score = result.get("risk_score", 0)
    message = f"{subject}\nFrom: {sender}\nRisk score: {score}/100"

    try:
        # threaded=True so this doesn't block the listener loop waiting on the toast.
        toaster.show_toast(title, message, duration=8, threaded=True)
    except Exception:
        logger.exception("Failed to show desktop notification (continuing anyway)")
