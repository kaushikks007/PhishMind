"""
Deterministic technical/authentication analysis: SPF/DKIM/DMARC parsing and
Reply-To vs From mismatch detection. This never calls the AI — it's pure
header inspection, capped contribution to the final score is 25 points
(see app/risk/scorer.py).
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import tldextract


def _extract_result(auth_results: str, mechanism: str) -> str:
    """Pull 'pass' / 'fail' / 'softfail' / 'none' etc. for a given mechanism
    (spf, dkim, dmarc) out of a raw Authentication-Results header."""
    pattern = rf"{mechanism}=([a-zA-Z]+)"
    match = re.search(pattern, auth_results, re.IGNORECASE)
    return match.group(1).lower() if match else "unknown"


def _domain_of(address: str) -> str:
    if not address or "@" not in address:
        return ""
    return address.split("@")[-1].strip().lower()


def analyze_technical(email_data: dict) -> dict:
    """
    Returns a dict of findings and a capped 0-25 technical_risk score.
    Even a clean SPF/DKIM/DMARC pass can still be flagged if the Reply-To
    domain silently diverges from the From domain (a common credential-
    harvesting trick: use a legitimate-looking From address but route replies
    elsewhere).
    """
    auth_results = email_data.get("auth_results_header", "") or ""
    received_spf = email_data.get("received_spf_header", "") or ""

    spf = _extract_result(auth_results, "spf") or _extract_result(received_spf, "spf")
    dkim = _extract_result(auth_results, "dkim")
    dmarc = _extract_result(auth_results, "dmarc")

    sender_domain = _domain_of(email_data.get("sender", ""))
    reply_to_domain = _domain_of(email_data.get("reply_to", ""))
    reply_to_mismatch = bool(reply_to_domain) and reply_to_domain != sender_domain

    score = 0
    findings: list[str] = []

    if spf == "fail":
        score += 10
        findings.append("SPF check failed — sending server is not authorized for this domain.")
    elif spf == "softfail":
        score += 5
        findings.append("SPF soft-fail — sending server is only weakly authorized.")

    if dkim == "fail":
        score += 8
        findings.append("DKIM signature failed validation.")

    if dmarc == "fail":
        score += 7
        findings.append("DMARC policy check failed.")

    if reply_to_mismatch:
        score += 10
        findings.append(
            f"Reply-To domain ({reply_to_domain}) does not match the sender domain ({sender_domain})."
        )

    # Lookalike-domain check against any URLs already extracted, compared to sender domain
    urls = email_data.get("urls", []) or []
    sender_ext = tldextract.extract(sender_domain) if sender_domain else None
    for url in urls:
        try:
            url_domain = urlparse(url).hostname or ""
        except ValueError:
            continue
        url_ext = tldextract.extract(url_domain)
        if (
            sender_ext
            and url_ext.domain
            and sender_ext.domain
            and url_ext.domain != sender_ext.domain
            and url_ext.registered_domain
        ):
            # Only flag once, not per-URL, to avoid runaway scoring
            findings.append(
                f"A link in the email points to a different registered domain ({url_ext.registered_domain}) than the sender ({sender_ext.registered_domain})."
            )
            break

    return {
        "spf": spf,
        "dkim": dkim,
        "dmarc": dmarc,
        "sender_domain": sender_domain,
        "reply_to_domain": reply_to_domain,
        "reply_to_mismatch": reply_to_mismatch,
        "technical_risk": min(25, score),
        "findings": findings,
    }
