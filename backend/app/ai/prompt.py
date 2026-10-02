"""
Pydantic schema for Gemini's structured output, plus the system/user prompts.
The AI supplies evidence and semantic judgment only — it NEVER outputs the
final risk score. That is always computed deterministically in
app/risk/scorer.py so results are consistent and can't be hallucinated.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class SocialEngineeringTechnique(BaseModel):
    technique: str = Field(description="Technique name, e.g., Urgency, Authority, Coercion")
    evidence: str = Field(description="Direct snippet or reason from the email")
    severity: Literal["low", "medium", "high"]


class PhishMindAnalysis(BaseModel):
    intent: Literal[
        "credential_theft",
        "financial_fraud",
        "data_theft",
        "malware_delivery",
        "oauth_abuse",
        "mfa_manipulation",
        "information_disclosure",
        "account_verification",
        "impersonation",
        "benign",
        "unknown",
    ]
    intent_confidence: float = Field(ge=0.0, le=1.0, description="Confidence between 0.0 and 1.0")
    claimed_brand: Optional[str] = Field(
        default=None,
        description="The specific company/organization the sender claims to represent, or null if none/personal email",
    )
    requested_action: str = Field(description="What the email is asking the recipient to do")
    social_engineering: List[SocialEngineeringTechnique] = Field(default_factory=list)
    suspicious_evidence: List[str] = Field(default_factory=list)
    ai_assisted_indicators: List[str] = Field(
        default_factory=list, description="Observable stylistic evidence only — never claim certainty"
    )
    semantic_risk: int = Field(ge=0, le=100, description="Semantic risk level from 0 to 100")
    explanation: str
    user_advice: List[str] = Field(default_factory=list)
    detected_language: str = Field(
        description="ISO 639-1 code of the language the email SUBJECT and BODY are written in, e.g. 'en', 'pt', 'es'"
    )
    translated_subject: Optional[str] = Field(
        default=None,
        description="Full English translation of the SUBJECT line. Null/omit if detected_language is already 'en'.",
    )
    translated_body: Optional[str] = Field(
        default=None,
        description="Full English translation of the entire BODY, preserving meaning and structure. Null/omit if detected_language is already 'en'.",
    )


SYSTEM_PROMPT = """You are PhishMind, an AI phishing-analysis assistant for a cybersecurity \
application. Analyze observable evidence only. Do not claim certainty that an email was \
AI-generated — only note stylistic indicators if present. Be conservative: only flag \
social engineering techniques and suspicious evidence you can directly point to in the \
provided text. Always write "explanation", "requested_action", and every item in \
"user_advice" and "suspicious_evidence" in English, regardless of what language the email \
itself is written in. Detect the email's language and set "detected_language" to its ISO \
639-1 code. If that language is not English, provide a complete, accurate English \
translation of the subject and body in "translated_subject" and "translated_body" so an \
English-speaking user can read the full email content. If the email is already in English, \
leave both translation fields null. Return only valid JSON matching the given schema."""


def build_prompt(email_data: dict) -> str:
    return f"""Analyze this email for phishing indicators.

SUBJECT: {email_data.get("subject", "")}
SENDER: {email_data.get("sender", "")}
REPLY-TO: {email_data.get("reply_to", "")}
BODY:
{email_data.get("body", "")}

URLS FOUND IN EMAIL: {email_data.get("urls", [])}
"""
