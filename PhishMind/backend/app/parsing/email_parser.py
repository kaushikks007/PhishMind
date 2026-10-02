"""
Parses raw .eml bytes/text into a clean, structured dict the rest of the
pipeline can work with. Handles both text/plain and text/html bodies
(HTML-only emails are extremely common in real phishing, so failing to
extract them would silently blind the whole system).
"""
from __future__ import annotations

import email
from email.message import Message
from email.utils import parseaddr

from bs4 import BeautifulSoup

from app.utils.url_utils import extract_urls


class EmailParseError(Exception):
    """Raised when the input cannot be parsed as an email at all."""


def _decode_payload(part: Message) -> str:
    try:
        payload = part.get_payload(decode=True)
        if payload is None:
            return part.get_payload() or ""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError, ValueError):
        try:
            return part.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception:
            return ""


def _html_to_text(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator=" ", strip=True)
    except Exception:
        return ""


def _extract_html_links(html: str) -> list[str]:
    """Pull hrefs out of anchor tags directly, including ones whose visible
    text differs from the destination (a classic phishing tell)."""
    links = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.lower().startswith(("http://", "https://")):
                links.append(href)
    except Exception:
        pass
    return links


def parse_eml_bytes(raw: bytes) -> dict:
    """Parse raw .eml bytes into structured fields."""
    try:
        msg = email.message_from_bytes(raw)
    except Exception as exc:
        raise EmailParseError(f"Failed to parse email bytes: {exc}") from exc
    return _parse_message(msg)


def parse_eml_text(raw_text: str) -> dict:
    """Parse a raw email source string (as pasted by a user) into structured fields."""
    try:
        msg = email.message_from_string(raw_text)
    except Exception as exc:
        raise EmailParseError(f"Failed to parse email text: {exc}") from exc
    return _parse_message(msg)


def _parse_message(msg: Message) -> dict:
    subject = msg.get("Subject", "") or ""
    _, sender_addr = parseaddr(msg.get("From", "") or "")
    _, reply_to_addr = parseaddr(msg.get("Reply-To", "") or "")

    body_text = ""
    body_html = ""
    html_links: list[str] = []
    attachments: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition") or "")

            if "attachment" in content_disposition:
                filename = part.get_filename()
                if filename:
                    attachments.append(filename)
                continue

            if content_type == "text/plain" and not body_text:
                body_text = _decode_payload(part)
            elif content_type == "text/html" and not body_html:
                body_html = _decode_payload(part)
    else:
        content_type = msg.get_content_type()
        payload = _decode_payload(msg)
        if content_type == "text/html":
            body_html = payload
        else:
            body_text = payload

    if body_html:
        html_links = _extract_html_links(body_html)
        if not body_text:
            # HTML-only email fallback: still get plain-text-equivalent content
            # so semantic/URL analysis doesn't run on an empty string.
            body_text = _html_to_text(body_html)

    combined_text = body_text or ""
    urls = list(dict.fromkeys(extract_urls(combined_text) + html_links))

    # Auth headers, kept raw here; interpreted in technical.py
    auth_results = msg.get("Authentication-Results", "") or ""
    received_spf = msg.get("Received-SPF", "") or ""

    return {
        "subject": subject,
        "sender": sender_addr or (msg.get("From", "") or ""),
        "reply_to": reply_to_addr,
        "body": combined_text,
        "body_html": body_html,
        "urls": urls,
        "attachments": attachments,
        "auth_results_header": auth_results,
        "received_spf_header": received_spf,
        "raw_headers": dict(msg.items()),
    }
