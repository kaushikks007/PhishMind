"""
Compares the brand Gemini says the email claims to represent (e.g. "Netflix")
against the sender's actual domain. This is what catches "looks legitimate,
passed SPF/DKIM, but isn't actually who it says it is."

A small built-in map covers common brands for the demo; anything not in the
map falls back to a straightforward "does the domain contain the brand name"
heuristic, which is intentionally conservative (it can under-flag but should
not over-flag: `is_brand_verified=True` should never be returned for a genuine
mismatch).
"""
from __future__ import annotations

import re

import tldextract

KNOWN_BRAND_DOMAINS = {
    "netflix": "netflix.com",
    "microsoft": "microsoft.com",
    "google": "google.com",
    "apple": "apple.com",
    "amazon": "amazon.com",
    "paypal": "paypal.com",
    "chase": "chase.com",
    "bank of america": "bankofamerica.com",
    "wells fargo": "wellsfargo.com",
    "facebook": "facebook.com",
    "instagram": "instagram.com",
    "linkedin": "linkedin.com",
    "dropbox": "dropbox.com",
    "docusign": "docusign.com",
    "adobe": "adobe.com",
    "youtube": "youtube.com",
    "gmail": "google.com",
    "outlook": "microsoft.com",
    "twitter": "twitter.com",
    "x": "x.com",
    "spotify": "spotify.com",
    "steam": "steampowered.com",
    "discord": "discord.com",
    "whatsapp": "whatsapp.com",
    "linkedin corporation": "linkedin.com",
}


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def verify_brand(claimed_brand: str | None, sender_domain: str) -> dict:
    """
    Returns {"claimed_brand": str|None, "is_brand_verified": bool, "expected_domain": str|None, "note": str}
    """
    if not claimed_brand or claimed_brand.strip().lower() in {"none", "n/a", ""}:
        return {
            "claimed_brand": None,
            "is_brand_verified": False,
            "is_verifiable": False,
            "expected_domain": None,
            "note": "No specific brand was claimed; brand verification not applicable.",
        }

    normalized = _normalize(claimed_brand)
    sender_ext = tldextract.extract(sender_domain) if sender_domain else None
    sender_registered = sender_ext.registered_domain.lower() if sender_ext and sender_ext.registered_domain else ""

    if not sender_registered:
        # We have no sender domain to check at all (e.g. a manually-pasted
        # email missing its headers) — this is a data-completeness problem,
        # not evidence of spoofing, so don't claim "spoofed".
        return {
            "claimed_brand": claimed_brand,
            "is_brand_verified": False,
            "is_verifiable": False,
            "expected_domain": KNOWN_BRAND_DOMAINS.get(normalized),
            "note": (
                f"Could not verify the claim to be {claimed_brand}: no sender domain was "
                "found in this email (the pasted source may be missing its headers)."
            ),
        }

    expected_domain = KNOWN_BRAND_DOMAINS.get(normalized)

    if expected_domain:
        verified = sender_registered == expected_domain
        note = (
            f"Sender domain matches the official domain for {claimed_brand}."
            if verified
            else f"Sender domain ({sender_registered or 'unknown'}) does not match the official domain for {claimed_brand} ({expected_domain})."
        )
        return {
            "claimed_brand": claimed_brand,
            "is_brand_verified": verified,
            "is_verifiable": True,
            "expected_domain": expected_domain,
            "note": note,
        }

    # Unknown brand: fall back to a conservative substring heuristic.
    brand_token = normalized.replace(" ", "")
    verified = bool(brand_token) and brand_token in sender_registered.replace(".", "")
    note = (
        f"'{claimed_brand}' is not in the known-brand list; heuristic domain match "
        f"{'succeeded' if verified else 'failed'} against sender domain '{sender_registered or 'unknown'}'."
    )
    return {
        "claimed_brand": claimed_brand,
        "is_brand_verified": verified,
        "is_verifiable": True,
        "expected_domain": None,
        "note": note,
    }
