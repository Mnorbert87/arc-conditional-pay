"""
Integration tests for the conditional-payment engine with a fake executor: prove that a
payment fires exactly when (and only when) the milestone is verified within the rules, and
never on expiry, cancellation, wrong verifier, or a failed send.
"""
from condpay.store import JobStore
from condpay.engine import ConditionalPayEngine

PAYEE = "0x" + "a" * 40
V = "0x" + "c" * 40
OTHER = "0x" + "d" * 40


class FakeExecutor:
    def __init__(self):
        self.sent = []
        self.n = 0

    def __call__(self, to, amount):
        self.sent.append((to, amount))
        self.n += 1
        return f"0xrel{self.n}"


def _engine(tmp_path):
    store = JobStore(str(tmp_path / "c.db"))
    fake = FakeExecutor()
    return ConditionalPayEngine(store, fake), store, fake


def test_create_then_verify_pays(tmp_path):
    eng, store, fake = _engine(tmp_path)
    jid = eng.create_job(PAYEE, 25)["job_id"]
    out = eng.verify(jid)
    assert out["released"] is True
    assert fake.sent == [(PAYEE.lower(), 25)]
    assert store.get_job(jid)["status"] == "released"


def test_create_rejects_bad_input(tmp_path):
    eng, _, _ = _engine(tmp_path)
    assert eng.create_job(PAYEE, 0)["status"] == "error"
    assert eng.create_job("nope", 5)["status"] == "error"


def test_cancel_then_verify_never_pays(tmp_path):
    eng, store, fake = _engine(tmp_path)
    jid = eng.create_job(PAYEE, 25)["job_id"]
    eng.cancel(jid)
    out = eng.verify(jid)
    assert out["released"] is False
    assert fake.sent == []
    assert store.get_job(jid)["status"] == "cancelled"


def test_expired_job_does_not_pay(tmp_path):
    eng, store, fake = _engine(tmp_path)
    jid = eng.create_job(PAYEE, 25, expiry_ts=100)["job_id"]
    out = eng.verify(jid, now=200)  # after expiry
    assert out["released"] is False
    assert out["status"] == "expired"
    assert fake.sent == []


def test_wrong_verifier_blocks_then_right_one_pays(tmp_path):
    eng, store, fake = _engine(tmp_path)
    jid = eng.create_job(PAYEE, 25, required_verifier=V)["job_id"]
    blocked = eng.verify(jid, verifier=OTHER, now=10)
    assert blocked["released"] is False
    assert fake.sent == []
    ok = eng.verify(jid, verifier=V, now=10)
    assert ok["released"] is True
    assert fake.sent == [(PAYEE.lower(), 25)]


def test_run_expiry_marks_only_past_deadline(tmp_path):
    eng, store, fake = _engine(tmp_path)
    a = eng.create_job(PAYEE, 1, expiry_ts=100)["job_id"]
    b = eng.create_job(PAYEE, 1, expiry_ts=500)["job_id"]
    res = eng.run_expiry(now=200)
    assert res["count"] == 1 and a in res["expired"]
    assert store.get_job(b)["status"] == "open"


def test_double_verify_pays_once(tmp_path):
    eng, store, fake = _engine(tmp_path)
    jid = eng.create_job(PAYEE, 25)["job_id"]
    eng.verify(jid)
    eng.verify(jid)  # already released, must not pay again
    assert len(fake.sent) == 1


def test_failed_send_leaves_job_open(tmp_path):
    store = JobStore(str(tmp_path / "c.db"))

    def boom(to, amount):
        raise RuntimeError("rpc down")

    eng = ConditionalPayEngine(store, boom)
    jid = eng.create_job(PAYEE, 25)["job_id"]
    out = eng.verify(jid)
    assert out["released"] is False
    assert store.get_job(jid)["status"] == "open"  # retryable, not silently released
