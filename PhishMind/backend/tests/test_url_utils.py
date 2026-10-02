from app.utils.url_utils import extract_urls, score_urls


def test_extract_urls_basic():
    text = "Please visit https://example.com/verify?next=1 today."
    urls = extract_urls(text)
    assert urls == ["https://example.com/verify?next=1"]


def test_extract_urls_does_not_mutate_valid_trailing_paren():
    text = "See https://example.com/path(item) for details"
    urls = extract_urls(text)
    # trailing ')' has a matching '(' earlier in the URL, so it must be kept
    assert urls == ["https://example.com/path(item)"]


def test_extract_urls_strips_sentence_punctuation():
    text = "Click http://bad.example.net/login."
    urls = extract_urls(text)
    assert urls == ["http://bad.example.net/login"]


def test_score_urls_flags_ip_literal():
    score, evidence = score_urls(["http://192.168.1.1/login"])
    assert score > 0
    assert any("IP address" in e for e in evidence)


def test_score_urls_empty_list():
    score, evidence = score_urls([])
    assert score == 0
    assert evidence == []
