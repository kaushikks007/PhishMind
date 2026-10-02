"""
Calls Gemini with a strict response_schema so we get a validated
PhishMindAnalysis object back (or a clean, typed failure) — never a raw
freeform string we have to hope is valid JSON.
"""
from __future__ import annotations

import logging

from google import genai
from google.genai import types

from app.ai.prompt import SYSTEM_PROMPT, PhishMindAnalysis, build_prompt
from app.config import settings

logger = logging.getLogger("phishmind.gemini")


class GeminiAnalysisError(Exception):
    """Raised when Gemini cannot be reached or returns an unusable response."""


def _fallback_analysis(reason: str) -> PhishMindAnalysis:
    """
    A safe, clearly-labeled degraded result used when Gemini is unreachable
    or misconfigured, so the rest of the pipeline (and the frontend) always
    gets a well-formed object instead of crashing mid-scan.
    """
    return PhishMindAnalysis(
        intent="unknown",
        intent_confidence=0.0,
        claimed_brand=None,
        requested_action="Unknown — AI analysis unavailable.",
        social_engineering=[],
        suspicious_evidence=[f"AI analysis unavailable: {reason}"],
        ai_assisted_indicators=[],
        semantic_risk=0,
        explanation=(
            "Semantic analysis could not be completed because the AI service was "
            "unavailable or misconfigured. This result reflects technical and URL "
            "heuristics only — treat it as incomplete."
        ),
        user_advice=["Re-run this scan once the AI service is configured and reachable."],
        detected_language="unknown",
        translated_subject=None,
        translated_body=None,
    )


def analyze_with_gemini(email_data: dict) -> PhishMindAnalysis:
    """
    Returns a validated PhishMindAnalysis. Never raises to the caller —
    on any failure (missing key, network error, bad response) it returns a
    clearly-labeled fallback so /api/v1/scan can still return a 200 with a
    technical+URL-only score rather than a 500.
    """
    if not settings.gemini_configured():
        logger.warning("GEMINI_API_KEY not configured; returning fallback analysis.")
        return _fallback_analysis("GEMINI_API_KEY is not set in .env")

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=build_prompt(email_data),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.1,
                response_mime_type="application/json",
                response_schema=PhishMindAnalysis,
            ),
        )
        parsed = response.parsed
        if parsed is None:
            # Model returned JSON that didn't validate against the schema.
            raise GeminiAnalysisError("Gemini response did not match the expected schema.")
        return parsed
    except Exception as exc:  # noqa: BLE001 - deliberately broad: any AI failure must degrade, not crash
        logger.exception("Gemini analysis failed")
        return _fallback_analysis(str(exc))
