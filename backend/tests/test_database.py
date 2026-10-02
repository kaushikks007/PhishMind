import pytest

from app.db import database


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db_path = tmp_path / "test_phishmind.db"
    # settings is a frozen dataclass; bypass immutability just for this test's isolation.
    object.__setattr__(database.settings, "database_path", str(db_path))
    database.init_db()
    yield


def test_save_and_get_scan_by_id_round_trip():
    scan_id = database.save_scan_result(
        {
            "subject": "Test",
            "sender": "a@b.com",
            "claimed_brand": "Netflix",
            "is_brand_verified": False,
            "risk_score": 80,
            "verdict": "PHISHING",
            "breakdown": {"technical": 10, "intent": 30, "social_engineering": 30, "urls": 10, "semantic_support": 0},
            "social_engineering": [],
            "suspicious_evidence": ["evidence one"],
            "explanation": "Because reasons.",
            "actionable_advice": ["Don't click."],
            "body": "Hello, please verify your account.",
        },
        source="manual",
    )

    record = database.get_scan_by_id(scan_id)
    assert record is not None
    assert record["id"] == str(scan_id)
    assert record["subject"] == "Test"
    assert record["body"] == "Hello, please verify your account."
    assert record["verdict"] == "PHISHING"


def test_get_scan_by_id_missing_returns_none():
    assert database.get_scan_by_id(999999) is None


def test_get_history_orders_newest_first():
    id1 = database.save_scan_result({"subject": "First", "sender": "a@b.com"}, source="manual")
    id2 = database.save_scan_result({"subject": "Second", "sender": "a@b.com"}, source="manual")

    history = database.get_history(limit=10)
    assert history[0]["id"] == str(id2)
    assert history[1]["id"] == str(id1)


def test_set_user_feedback_round_trip():
    scan_id = database.save_scan_result({"subject": "Test", "sender": "a@b.com"}, source="manual")

    assert database.get_scan_by_id(scan_id)["user_feedback"] is None
    assert database.set_user_feedback(scan_id, "spam") is True
    assert database.get_scan_by_id(scan_id)["user_feedback"] == "spam"


def test_set_user_feedback_missing_scan_returns_false():
    assert database.set_user_feedback(999999, "spam") is False
