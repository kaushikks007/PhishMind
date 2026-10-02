"""
URL extraction and heuristic risk analysis.

Fixes the classic prototype bug: a naive regex + blind `.rstrip('.,;)]>"\'')`
can mutate a perfectly valid URL if it legitimately ends in one of those
characters (e.g. a query string ending in a closing paren that is actually
part of the URL). We extract with a conservative regex, then only trim
trailing punctuation that is clearly *not* part of the URL (a trailing
sentence-ending character with no matching opening bracket earlier in the
same URL), and we never raise on a malformed URL — malformed is itself signal.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

import tldextract

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# Trailing characters that are almost always sentence/markup punctuation,
# not part of the URL, UNLESS the URL contains a matching opening character
# earlier (so we don't mangle a legitimate parenthesized query value).
_TRAILING_STRIP_MAP = {
    ")": "(",
    "]": "[",
    "}": "{",
    ">": "<",
}
_TRAILING_PLAIN = {".", ",", ";", "!", "?", '"', "'"}

SUSPICIOUS_KEYWORDS = (
    "login",
    "verify",
    "account",
    "secure",
    "update",
    "confirm",
    "signin",
    "password",
    "banking",
)
SUSPICIOUS_TLDS = {"zip", "mov", "xyz", "top", "click", "gq", "tk", "cf", "ml"}


def _trim_trailing_punctuation(url: str) -> str:
    """Strip trailing punctuation only when it's not balanced inside the URL."""
    while url:
        last = url[-1]
        if last in _TRAILING_PLAIN:
            url = url[:-1]
            continue
        if last in _TRAILING_STRIP_MAP:
            opener = _TRAILING_STRIP_MAP[last]
            if url.count(opener) < url.count(last):
                url = url[:-1]
                continue
        break
    return url


def extract_urls(text: str) -> list[str]:
    """Extract and de-duplicate URLs from raw email body text."""
    if not text:
        return []
    found = []
    for match in _URL_RE.findall(text):
        cleaned = _trim_trailing_punctuation(match)
        if cleaned and cleaned not in found:
            found.append(cleaned)
    return found


def _is_ip_host(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False


def analyze_url(url: str) -> dict:
    """
    Return heuristic findings for a single URL. Never raises — a URL that
    fails to parse is itself treated as suspicious evidence.
    """
    findings = {
        "url": url,
        "uses_https": False,
        "is_ip_literal": False,
        "hostname": "",
        "registered_domain": "",
        "is_long_url": False,
        "has_suspicious_keyword": False,
        "has_suspicious_tld": False,
        "parse_error": False,
    }
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        findings["hostname"] = hostname
        findings["uses_https"] = parsed.scheme == "https"
        findings["is_long_url"] = len(url) > 120
        findings["is_ip_literal"] = _is_ip_host(hostname) if hostname else False

        ext = tldextract.extract(url)
        findings["registered_domain"] = ext.registered_domain
        findings["has_suspicious_tld"] = ext.suffix.split(".")[-1] in SUSPICIOUS_TLDS if ext.suffix else False

        path_and_query = f"{parsed.path} {parsed.query}".lower()
        findings["has_suspicious_keyword"] = any(kw in path_and_query or kw in hostname for kw in SUSPICIOUS_KEYWORDS)
    except (ValueError, AttributeError):
        findings["parse_error"] = True
    return findings


def score_urls(urls: list[str]) -> tuple[int, list[str]]:
    """
    Deterministic URL risk score, capped at 15 (matches scorer.py's max).
    Returns (raw_indicator_count_based_score, evidence_strings).
    """
    if not urls:
        return 0, []

    evidence: list[str] = []
    indicator_hits = 0

    for url in urls:
        f = analyze_url(url)
        if f["parse_error"]:
            indicator_hits += 1
            evidence.append(f"Malformed/unparseable URL: {url}")
            continue
        if f["is_ip_literal"]:
            indicator_hits += 1
            evidence.append(f"URL uses a raw IP address instead of a domain: {url}")
        if not f["uses_https"]:
            indicator_hits += 1
            evidence.append(f"URL does not use HTTPS: {url}")
        if f["is_long_url"]:
            indicator_hits += 1
            evidence.append(f"Unusually long URL (possible obfuscation): {url}")
        if f["has_suspicious_keyword"]:
            indicator_hits += 1
            evidence.append(f"URL path contains a credential/account keyword: {url}")
        if f["has_suspicious_tld"]:
            indicator_hits += 1
            evidence.append(f"URL uses a high-abuse TLD: {url}")

    score = min(15, indicator_hits * 3)
    return score, evidence
