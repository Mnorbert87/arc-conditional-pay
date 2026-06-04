"""Tests for the conditional-payment state machine: every transition and boundary."""
from condpay.conditions import Job, transition, is_expired

V = "0x" + "c" * 40
OTHER = "0x" + "d" * 40


def test_verify_releases_and_pays():
    t = transition(Job(status="open"), "verify", now=100)
    assert t.new_status == "released"
    assert t.should_pay is True


def test_verify_after_expiry_does_not_pay():
    t = transition(Job(status="open", expiry_ts=50), "verify", now=100)
    assert t.new_status == "expired"
    assert t.should_pay is False


def test_verify_exactly_at_expiry_is_expired():
    t = transition(Job(status="open", expiry_ts=100), "verify", now=100)
    assert t.new_status == "expired"


def test_required_verifier_mismatch_stays_open_no_pay():
    t = transition(Job(status="open", required_verifier=V), "verify", now=10, verifier=OTHER)
    assert t.new_status == "open"
    assert t.should_pay is False


def test_required_verifier_match_releases():
    t = transition(Job(status="open", required_verifier=V), "verify", now=10, verifier=V.upper())
    assert t.new_status == "released"
    assert t.should_pay is True


def test_cancel_terminates_without_pay():
    t = transition(Job(status="open"), "cancel", now=10)
    assert t.new_status == "cancelled"
    assert t.should_pay is False


def test_expire_check_marks_expired_after_deadline():
    t = transition(Job(status="open", expiry_ts=50), "expire_check", now=60)
    assert t.new_status == "expired"


def test_expire_check_keeps_open_before_deadline():
    t = transition(Job(status="open", expiry_ts=50), "expire_check", now=10)
    assert t.new_status == "open"


def test_no_action_on_terminal_job():
    for st in ("released", "expired", "cancelled"):
        t = transition(Job(status=st), "verify", now=10)
        assert t.new_status == st
        assert t.should_pay is False


def test_is_expired_none_never_expires():
    assert is_expired(None, 10**12) is False
