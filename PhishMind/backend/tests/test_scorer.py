from pathlib import Path

from app.ai.prompt import PhishMindAnalysis, SocialEngineeringTechnique
from app.parsing.email_parser import parse_eml_text
from app.parsing.technical import analyze_technical
from app.risk.scorer import calculate_risk
from app.utils.url_utils import score_urls

SAMPLES = Path(__file__).parent / "samples"


def _high_risk_analysis() -> PhishMindAnalysis:
    return PhishMindAnalysis(
        intent="credential_theft",
        intent_confidence=0.95,
        claimed_brand="IT Security",
        requested_action="Click the link to verify the account.",
        social_engineering=[
            SocialEngineeringTechnique(technique="Urgency", evidence="before 5 PM today", severity="high"),
            SocialEngineeringTechnique(technique="Coercion", evidence="account suspension", severity="high"),
            SocialEngineeringTechnique(technique="Authority", evidence="IT Security Team", severity="medium"),
        ],
        suspicious_evidence=["Generic greeting"],
        ai_assisted_indicators=[],
        semantic_risk=90,
        explanation="High-pressure verification demand.",
        user_advice=["Do not click the link."],
        detected_language="en",
        translated_subject=None,
        translated_body=None,
    )


def _benign_analysis() -> PhishMindAnalysis:
    return PhishMindAnalysis(
        intent="benign",
        intent_confidence=0.9,
        claimed_brand=None,
        requested_action="No action requested.",
        social_engineering=[],
        suspicious_evidence=[],
        ai_assisted_indicators=[],
        semantic_risk=2,
        explanation="Routine newsletter content.",
        user_advice=[],
        detected_language="en",
        translated_subject=None,
        translated_body=None,
    )


def test_calculate_risk_flags_high_risk_email_as_phishing():
    raw = (SAMPLES / "phishing_sample.eml").read_text()
    email_data = parse_eml_text(raw)
    technical = analyze_technical(email_data)
    url_score, _ = score_urls(email_data["urls"])

    result = calculate_risk(_high_risk_analysis(), technical, url_score)

    assert result["verdict"] == "PHISHING"
    assert result["risk_score"] >= 70
    assert result["breakdown"]["technical"] > 0  # Reply-To mismatch should be caught


def test_calculate_risk_flags_benign_email_as_safe():
    raw = (SAMPLES / "safe_sample.eml").read_text()
    email_data = parse_eml_text(raw)
    technical = analyze_technical(email_data)
    url_score, _ = score_urls(email_data["urls"])

    result = calculate_risk(_benign_analysis(), technical, url_score)

    assert result["verdict"] == "SAFE"
    assert result["risk_score"] < 30


def test_calculate_risk_never_exceeds_100():
    raw = (SAMPLES / "phishing_sample.eml").read_text()
    email_data = parse_eml_text(raw)
    technical = analyze_technical(email_data)

    result = calculate_risk(_high_risk_analysis(), technical, url_score=15)

    assert result["risk_score"] <= 100
