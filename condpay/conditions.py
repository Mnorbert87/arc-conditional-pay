"""
Pure state machine for a conditional payment ("pay the payee when a milestone is verified").

A job lives in one of these states:
  open       -> waiting for verification
  released   -> condition met, payment sent (terminal)
  expired    -> deadline passed before verification (terminal, no payment)
  cancelled  -> called off before release (terminal, no payment)

The transition function is pure: it takes the current job, an action, and the time, and
returns the next status, whether a payment should fire, and a reason. No I/O, no chain, so
the release rules are deterministically testable. The actual USDC send happens in the
engine only when `should_pay` is true.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Job:
    status: str = "open"
    expiry_ts: Optional[float] = None        # None means no deadline
    required_verifier: Optional[str] = None  # None means anyone may verify


@dataclass
class Transition:
    new_status: str
    should_pay: bool
    reason: str


def is_expired(expiry_ts: Optional[float], now: float) -> bool:
    return expiry_ts is not None and now >= expiry_ts


def transition(job: Job, action: str, now: float, verifier: Optional[str] = None) -> Transition:
    """Compute the next state for `action` on `job` at time `now`.

    Actions: "verify" (a verifier attests the milestone), "cancel", "expire_check".
    """
    if job.status != "open":
        return Transition(job.status, False, f"job is already {job.status}")

    if action == "expire_check":
        if is_expired(job.expiry_ts, now):
            return Transition("expired", False, "deadline passed before verification")
        return Transition("open", False, "still open")

    if action == "cancel":
        return Transition("cancelled", False, "cancelled before release")

    if action == "verify":
        if is_expired(job.expiry_ts, now):
            return Transition("expired", False, "deadline passed; cannot verify")
        if job.required_verifier is not None and (verifier or "").lower() != job.required_verifier.lower():
            return Transition("open", False, "verifier is not the required verifier")
        return Transition("released", True, "verified; releasing payment")

    return Transition(job.status, False, f"unknown action {action}")
