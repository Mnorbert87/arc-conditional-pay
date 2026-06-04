"""
Arc Conditional Pay: hold a USDC payment until a milestone is verified, then release it on
Arc. "Pay this address 100 USDC when the work is verified, by this deadline, by this
verifier." An agent or an oracle calls verify, and the payment fires only if the milestone
is met within the rules. Expired or cancelled jobs never pay.

This is the milestone half of agent commerce: it pairs with arc-agent-guard (limits on
what an agent may spend) to make agent-driven payments both bounded and conditional.

Note: the funds are released from the configured wallet on verification (the payer
pre-funds it). A fully trustless on-chain escrow contract that locks funds is the v2 path.

Config via env:
  CONDPAY_DB_PATH    where to keep jobs (default condpay.db)
  ARC_PRIVATE_KEY    the paying wallet's key (needed only to release)
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from .store import JobStore
from .engine import ConditionalPayEngine
from .arc import ArcSender

DB_PATH = os.getenv("CONDPAY_DB_PATH", "condpay.db")

mcp = FastMCP("arc-conditional-pay")
_store = JobStore(DB_PATH)
_sender = ArcSender()
_engine = ConditionalPayEngine(_store, executor=_sender.send)


@mcp.tool()
def condpay_create(payee: str, amount_usdc: float, expiry_ts: float | None = None,
                   required_verifier: str | None = None, memo: str = "") -> dict:
    """Create a conditional payment job (held until verified).

    Args:
        payee: 0x address to pay when the milestone is verified
        amount_usdc: amount to release
        expiry_ts: optional unix timestamp; after it the job expires and never pays
        required_verifier: optional address that alone may verify (None = anyone)
        memo: a note describing the milestone
    """
    return _engine.create_job(payee, amount_usdc, expiry_ts, required_verifier, memo)


@mcp.tool()
def condpay_verify(job_id: int, verifier: str | None = None) -> dict:
    """Attest that the milestone is met. If the job is open, within its deadline, and the
    verifier is allowed, the payment is released on Arc and the job is marked released."""
    return _engine.verify(job_id, verifier=verifier)


@mcp.tool()
def condpay_cancel(job_id: int) -> dict:
    """Cancel an open job before release. It will never pay."""
    return _engine.cancel(job_id)


@mcp.tool()
def condpay_run_expiry() -> dict:
    """Mark any open jobs whose deadline has passed as expired."""
    return _engine.run_expiry()


@mcp.tool()
def condpay_get(job_id: int) -> dict:
    """Get one job by id."""
    return _engine.get(job_id)


@mcp.tool()
def condpay_list(status: str | None = None) -> dict:
    """List jobs, optionally filtered by status (open, released, expired, cancelled)."""
    return {"jobs": _engine.list(status)}


@mcp.tool()
def condpay_wallet() -> dict:
    """The paying wallet address and whether a key is configured."""
    return {"wallet_address": _sender.address(), "configured": _sender.configured}


if __name__ == "__main__":
    mcp.run()
