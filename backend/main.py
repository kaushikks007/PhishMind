"""
PhishMind backend entrypoint.

Run with:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import asyncio
import base64
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.db.database import get_history, get_scan_by_id, init_db, save_scan_result, set_user_feedback
from app.listeners.imap_listener import listener_state
from app.parsing.email_parser import EmailParseError, parse_eml_bytes, parse_eml_text
from app.pipeline import run_pipeline
from app.watchers.email_activity_watcher import EmailActivityWatcher

email_watcher: EmailActivityWatcher | None = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("phishmind.api")

app = FastAPI(title="PhishMind API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    # Vite auto-bumps to 5174/5175/... whenever 5173 is already taken, which
    # kept breaking the dashboard with "Failed to fetch" every time that
    # happened. Rather than relying on ALLOWED_ORIGINS in .env always being
    # kept in sync with whatever port Vite grabbed, allow any localhost/
    # 127.0.0.1 port for local dev in addition to the configured origins.
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    if not settings.gemini_configured():
        logger.warning(
            "GEMINI_API_KEY is not set — scans will run with technical/URL heuristics only "
            "until it is configured in .env."
        )

    global email_watcher

    if not settings.imap_auto_start_configured():
        return

    if settings.email_watch_enabled:
        def _start_scanning() -> None:
            try:
                listener_state.start(settings.imap_host, settings.imap_username, settings.imap_app_password)
                logger.info("Email window detected — PhishMind started scanning %s.", settings.imap_username)
            except RuntimeError:
                pass  # already running (e.g. started manually from the dashboard) — fine

        def _stop_scanning() -> None:
            listener_state.stop()
            logger.info("No email window detected for a while — PhishMind stopped scanning to save resources.")

        email_watcher = EmailActivityWatcher(
            on_email_open=_start_scanning,
            on_email_closed=_stop_scanning,
            keywords=settings.email_watch_keywords,
            poll_seconds=settings.email_watch_poll_seconds,
            grace_seconds=settings.email_watch_grace_seconds,
        )
        email_watcher.start()
        logger.info(
            "Email-activity watcher started (keywords=%s) — PhishMind will scan %s only while "
            "an email window matching those keywords is open.",
            settings.email_watch_keywords,
            settings.imap_username,
        )
    else:
        # EMAIL_WATCH_ENABLED=false: fall back to always-on scanning from boot.
        try:
            listener_state.start(settings.imap_host, settings.imap_username, settings.imap_app_password)
            logger.info(
                "PhishMind is now watching %s in the background (auto-started from .env).",
                settings.imap_username,
            )
        except Exception:
            logger.exception(
                "Auto-start of the IMAP listener failed — check IMAP_HOST/IMAP_USERNAME/"
                "IMAP_APP_PASSWORD in .env. The API is still up; you can retry via "
                "POST /api/v1/listener/start."
            )


@app.on_event("shutdown")
def _shutdown() -> None:
    if email_watcher is not None:
        email_watcher.stop()
    listener_state.stop()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    raw_eml_base64: str | None = Field(default=None, description="Base64-encoded raw .eml bytes")
    raw_email_text: str | None = Field(default=None, description="Raw email source as plain text")


class ListenerStartRequest(BaseModel):
    host: str
    username: str
    app_password: str


class FeedbackRequest(BaseModel):
    feedback: str = Field(description="'spam' or 'valid' — the human's own call on the email")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/scan")
def scan_email(payload: ScanRequest):
    if not payload.raw_eml_base64 and not payload.raw_email_text:
        raise HTTPException(status_code=400, detail="Provide either raw_eml_base64 or raw_email_text.")

    try:
        if payload.raw_eml_base64:
            try:
                raw_bytes = base64.b64decode(payload.raw_eml_base64, validate=True)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid base64 in raw_eml_base64: {exc}") from exc
            email_data = parse_eml_bytes(raw_bytes)
        else:
            email_data = parse_eml_text(payload.raw_email_text)
    except EmailParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        result = run_pipeline(email_data)
    except Exception as exc:  # noqa: BLE001 - never let an unexpected error 500 without a JSON body
        logger.exception("Pipeline failure during /api/v1/scan")
        raise HTTPException(status_code=500, detail=f"Scan failed: {exc}") from exc

    try:
        scan_id = save_scan_result(result, source="manual")
        result["id"] = str(scan_id)
    except Exception:
        logger.exception("Failed to persist scan result (continuing anyway)")
        result.setdefault("id", None)

    return {"status": "success", "data": result}


@app.get("/api/v1/history")
def history(limit: int = 50):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500.")
    return {"status": "success", "data": get_history(limit=limit)}


@app.get("/api/v1/scan/{scan_id}")
def get_scan(scan_id: int):
    record = get_scan_by_id(scan_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No scan found with id {scan_id}.")
    return {"status": "success", "data": record}


@app.post("/api/v1/scan/{scan_id}/feedback")
def submit_feedback(scan_id: int, payload: FeedbackRequest):
    """Used by the Chrome extension's 'Is this spam or valid?' prompt (and the
    dashboard) to record what the human decided, alongside PhishMind's own
    verdict, for later review."""
    feedback = payload.feedback.strip().lower()
    if feedback not in {"spam", "valid"}:
        raise HTTPException(status_code=400, detail="feedback must be 'spam' or 'valid'.")
    if not set_user_feedback(scan_id, feedback):
        raise HTTPException(status_code=404, detail=f"No scan found with id {scan_id}.")
    return {"status": "success", "data": {"id": scan_id, "user_feedback": feedback}}


@app.post("/api/v1/listener/start")
def start_listener(payload: ListenerStartRequest):
    try:
        listener_state.start(payload.host, payload.username, payload.app_password)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "success", "data": listener_state.status()}


@app.post("/api/v1/listener/stop")
def stop_listener():
    listener_state.stop()
    return {"status": "success", "data": listener_state.status()}


@app.get("/api/v1/listener/status")
def listener_status():
    return {"status": "success", "data": listener_state.status()}


@app.get("/api/v1/watcher/status")
def watcher_status():
    if email_watcher is None:
        return {
            "status": "success",
            "data": {"enabled": False, "note": "Email-activity watcher is not running (always-on mode or no IMAP credentials configured)."},
        }
    return {"status": "success", "data": {"enabled": True, **email_watcher.status()}}


@app.get("/api/v1/listener/events")
async def listener_events():
    async def event_generator():
        while True:
            try:
                event = await asyncio.to_thread(listener_state.events.get, True, 1.0)
                yield {"event": "scan_result", "data": _to_json(event)}
            except Exception:
                # queue.Empty on timeout — send a keepalive comment and loop
                yield {"event": "ping", "data": "{}"}

    return EventSourceResponse(event_generator())


def _to_json(obj: dict) -> str:
    import json

    return json.dumps(obj)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)
