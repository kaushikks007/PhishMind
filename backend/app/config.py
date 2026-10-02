"""
Central configuration loaded from environment variables (.env).
Never hardcode secrets anywhere else in the codebase — import from here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _split_origins(raw: str) -> list[str]:
    return [o.strip() for o in raw.split(",") if o.strip()]


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
    database_path: str = os.getenv("DATABASE_PATH", "phishmind.db")
    allowed_origins: list[str] = field(
        default_factory=lambda: _split_origins(
            os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
        )
    )
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

    # Optional: if all three are set, the background IMAP listener auto-starts
    # on boot so PhishMind watches the inbox the moment the server launches —
    # no need to open the dashboard and click "Connect" every time.
    imap_host: str = os.getenv("IMAP_HOST", "")
    imap_username: str = os.getenv("IMAP_USERNAME", "")
    imap_app_password: str = os.getenv("IMAP_APP_PASSWORD", "")

    # Show a native OS notification when a live-scanned email comes back
    # SUSPICIOUS or PHISHING. Defaults on; set to "false" to disable.
    desktop_notifications: bool = os.getenv("DESKTOP_NOTIFICATIONS", "true").strip().lower() != "false"

    # Email-activity watcher: instead of scanning the inbox 24/7, PhishMind can
    # watch for an open email window (Gmail/Outlook in a browser tab, the
    # Outlook desktop app, etc.) and only run the IMAP scanner while one is
    # open — stopping it again once you close your email. Windows-only.
    email_watch_enabled: bool = os.getenv("EMAIL_WATCH_ENABLED", "true").strip().lower() != "false"
    email_watch_keywords: list[str] = field(
        default_factory=lambda: [
            k.strip().lower()
            for k in os.getenv("EMAIL_WATCH_KEYWORDS", "gmail,outlook,mail").split(",")
            if k.strip()
        ]
    )
    email_watch_poll_seconds: float = float(os.getenv("EMAIL_WATCH_POLL_SECONDS", "5"))
    # How long an email window can be out of sight before we treat it as
    # "closed" and stop scanning — avoids stopping/starting on every tab switch.
    email_watch_grace_seconds: float = float(os.getenv("EMAIL_WATCH_GRACE_SECONDS", "30"))

    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key) and self.gemini_api_key != "YOUR_API_KEY_HERE"

    def imap_auto_start_configured(self) -> bool:
        return bool(self.imap_host and self.imap_username and self.imap_app_password)


settings = Settings()
