"""
Typed shape of a stored scan result (matches the rows produced by
app.db.database). Kept as a plain dataclass rather than a full ORM model —
a single-table SQLite store doesn't need one, but this gives callers and
API response models something concrete to type against.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScanResult:
    id: int
    timestamp: str
    subject: str
    sender: str
    claimed_brand: Optional[str]
    is_brand_verified: bool
    risk_score: int
    verdict: str
    breakdown: dict
    social_engineering: list = field(default_factory=list)
    suspicious_evidence: list = field(default_factory=list)
    explanation: str = ""
    actionable_advice: list = field(default_factory=list)
    source: str = "manual"
