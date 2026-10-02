from pathlib import Path

from app.parsing.email_parser import parse_eml_text

SAMPLES = Path(__file__).parent / "samples"


def test_parse_phishing_sample():
    raw = (SAMPLES / "phishing_sample.eml").read_text()
    data = parse_eml_text(raw)
    assert data["sender"] == "security-update@example.net"
    assert data["reply_to"] == "verify@different-example.net"
    assert "verify" in data["body"].lower()
    assert any("example.net/account/verify" in u for u in data["urls"])


def test_parse_safe_sample():
    raw = (SAMPLES / "safe_sample.eml").read_text()
    data = parse_eml_text(raw)
    assert data["sender"] == "news@example.edu"
    assert data["reply_to"] == "news@example.edu"
    assert data["urls"] == []
