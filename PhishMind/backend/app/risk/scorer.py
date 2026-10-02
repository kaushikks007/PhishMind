"""
Deterministic risk aggregator. This is the ONLY place the final 0-100 score
is computed — Gemini supplies evidence and semantic judgment, but never the
number itself, so results are reproducible and can't be hallucinated.

Category caps (sum to 100):
    technical            max 25   (SPF/DKIM/DMARC, Reply-To mismatch, lookalike link domain)
    intent               max 30   (Gemini's classified intent x confidence)
    social_engineering   max 30   (Gemini-identified manipulation techniques, by severity)
    url_signals          max 15   (heuristic URL analysis)
    semantic_support     max 10 bonus, folded in but the total is capped at 100 overall

Verdict bands:
    0-29   -> SAFE
    30-69  -> SUSPICIOUS
    70-100 -> PHISHING
"""
from __future__ import annotations

from app.ai.prompt import PhishMindAnalysis

HIGH_RISK_INTENTS = {
    "credential_theft": 30,
    "financial_fraud": 30,
    "data_theft": 28,
    "malware_delivery": 30,
    "oauth_abuse": 26,
    "mfa_manipulation": 26,
    "account_verification": 20,
    "impersonation": 22,
}
LOW_RISK_INTENTS = {"information_disclosure": 12, "benign": 0, "unknown": 0}

SEVERITY_POINTS = {"high": 10, "medium": 6, "low": 3}


def _intent_score(analysis: PhishMindAnalysis) -> int:
    weight = HIGH_RISK_INTENTS.get(analysis.intent, LOW_RISK_INTENTS.get(analysis.intent, 0))
    return round(weight * analysis.intent_confidence)


def _social_engineering_score(analysis: PhishMindAnalysis) -> int:
    total = sum(SEVERITY_POINTS.get(t.severity, 0) for t in analysis.social_engineering)
    return min(30, total)


def _semantic_support_score(analysis: PhishMindAnalysis) -> int:
    return round(analysis.semantic_risk * 0.1)


def calculate_risk(analysis: PhishMindAnalysis, technical: dict, url_score: int) -> dict:
    """
    technical: output dict from app.parsing.technical.analyze_technical()
    url_score: 0-15 score from app.utils.url_utils.score_urls()
    """
    technical_score = min(25, technical.get("technical_risk", 0))
    intent_score = min(30, _intent_score(analysis))
    social_score = _social_engineering_score(analysis)
    semantic_support = min(10, _semantic_support_score(analysis))
    bounded_url_score = min(15, max(0, url_score))

    raw_total = technical_score + intent_score + social_score + bounded_url_score + semantic_support
    risk_score = min(100, raw_total)

    if risk_score >= 70:
        verdict = "PHISHING"
    elif risk_score >= 30:
        verdict = "SUSPICIOUS"
    else:
        verdict = "SAFE"

    return {
        "risk_score": risk_score,
        "verdict": verdict,
        "breakdown": {
            "technical": technical_score,
            "intent": intent_score,
            "social_engineering": social_score,
            "urls": bounded_url_score,
            "semantic_support": semantic_support,
        },
    }
