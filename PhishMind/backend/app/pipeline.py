"""
The single shared pipeline: raw email in -> full PhishMind result dict out.
Both the /api/v1/scan endpoint and the IMAP listener call this exact function
so behavior is identical whether a scan is manual or automatic.
"""
from __future__ import annotations

import logging

from app.ai.gemini_analyzer import analyze_with_gemini
from app.parsing.technical import analyze_technical
from app.risk.scorer import calculate_risk
from app.utils.url_utils import score_urls
from app.verification.brand_verifier import verify_brand

logger = logging.getLogger("phishmind.pipeline")


def run_pipeline(email_data: dict) -> dict:
    """
    email_data: the dict produced by app.parsing.email_parser (parse_eml_bytes/text).
    Returns a dict matching the PhishMind API response `data` shape.
    """
    technical = analyze_technical(email_data)
    url_score, url_evidence = score_urls(email_data.get("urls", []))
    analysis = analyze_with_gemini(email_data)
    brand = verify_brand(analysis.claimed_brand, technical.get("sender_domain", ""))
    scored = calculate_risk(analysis, technical, url_score)

    suspicious_evidence = (
        technical.get("findings", [])
        + url_evidence
        + analysis.suspicious_evidence
        + ([brand["note"]] if brand.get("claimed_brand") else [])
    )

    return {
        "subject": email_data.get("subject", ""),
        "sender": email_data.get("sender", ""),
        "body": email_data.get("body", ""),
        "claimed_brand": brand["claimed_brand"],
        "is_brand_verified": brand["is_brand_verified"],
        "is_brand_verifiable": brand.get("is_verifiable", True),
        "risk_score": scored["risk_score"],
        "verdict": scored["verdict"],
        "breakdown": scored["breakdown"],
        "social_engineering": [t.model_dump() for t in analysis.social_engineering],
        "suspicious_evidence": suspicious_evidence,
        "explanation": analysis.explanation,
        "actionable_advice": analysis.user_advice,
        "detected_language": analysis.detected_language,
        "translated_subject": analysis.translated_subject,
        "translated_body": analysis.translated_body,
    }
