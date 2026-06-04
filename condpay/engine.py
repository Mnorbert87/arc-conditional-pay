"""
The conditional-payment engine ties the state machine and the store to an executor.

  executor(payee, amount) -> tx_hash   (production: the Arc sender; tests: a fake)

A job is created in the `open` state. When a verifier attests the milestone, the engine
runs the pure transition; only if it returns should_pay does it call the executor and mark
the job `released`. A failed send leaves the job open (so it can be retried), never
silently released. Expired or cancelled jobs never pay.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from .store import JobStore
from .conditions import Job, transition

Executor = Callable[[str, float], str]


class ConditionalPayEngine:
    def __init__(self, store: JobStore, executor: Executor):
        self.store = store
        self.executor = executor

    def create_job(self, payee: str, amount: float, expiry_ts: Optional[float] = None,
                   required_verifier: Optional[str] = None, memo: str = "") -> dict:
        if amount is None or amount <= 0:
            return {"status": "error", "reason": "amount must be positive"}
        if not (payee or "").lower().startswith("0x") or len(payee) != 42:
            return {"status": "error", "reason": "payee must be a valid 0x address"}
        job_id = self.store.create_job(payee, amount, expiry_ts, required_verifier, memo)
        return {"status": "open", "job_id": job_id, "payee": payee, "amount_usdc": amount}

    def _job_dc(self, row: dict) -> Job:
        return Job(status=row["status"], expiry_ts=row["expiry_ts"], required_verifier=row["required_verifier"])

    def verify(self, job_id: int, verifier: Optional[str] = None, now: Optional[float] = None) -> dict:
        now = now if now is not None else time.time()
        row = self.store.get_job(job_id)
        if not row:
            return {"status": "error", "reason": f"no job {job_id}"}

        t = transition(self._job_dc(row), "verify", now, verifier=verifier)

        if not t.should_pay:
            # status may move to expired, or stay open (wrong verifier), or already terminal
            if t.new_status != row["status"]:
                self.store.set_status(job_id, t.new_status)
            return {"status": t.new_status, "job_id": job_id, "released": False, "reason": t.reason}

        # should_pay: send, then mark released
        try:
            tx_hash = self.executor(row["payee"], row["amount_usdc"])
        except Exception as e:
            return {"status": "open", "job_id": job_id, "released": False, "reason": f"send failed, job left open: {e}"}
        self.store.set_status(job_id, "released", tx_hash=tx_hash)
        return {"status": "released", "job_id": job_id, "released": True, "tx_hash": tx_hash,
                "payee": row["payee"], "amount_usdc": row["amount_usdc"]}

    def cancel(self, job_id: int, now: Optional[float] = None) -> dict:
        now = now if now is not None else time.time()
        row = self.store.get_job(job_id)
        if not row:
            return {"status": "error", "reason": f"no job {job_id}"}
        t = transition(self._job_dc(row), "cancel", now)
        if t.new_status != row["status"]:
            self.store.set_status(job_id, t.new_status)
        return {"status": t.new_status, "job_id": job_id, "reason": t.reason}

    def run_expiry(self, now: Optional[float] = None) -> dict:
        now = now if now is not None else time.time()
        expired = []
        for row in self.store.list_jobs(status="open"):
            t = transition(self._job_dc(row), "expire_check", now)
            if t.new_status == "expired":
                self.store.set_status(row["id"], "expired")
                expired.append(row["id"])
        return {"expired": expired, "count": len(expired)}

    def get(self, job_id: int) -> dict:
        return self.store.get_job(job_id) or {"status": "error", "reason": f"no job {job_id}"}

    def list(self, status: Optional[str] = None) -> list[dict]:
        return self.store.list_jobs(status)
