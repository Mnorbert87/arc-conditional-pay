"""SQLite persistence for conditional-payment jobs."""
from __future__ import annotations

import sqlite3
import time
from typing import Optional


class JobStore:
    def __init__(self, path: str = "condpay.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                payee TEXT NOT NULL,
                amount_usdc REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                expiry_ts REAL,
                required_verifier TEXT,
                memo TEXT,
                tx_hash TEXT
            );
            """
        )
        self.conn.commit()

    def create_job(self, payee: str, amount: float, expiry_ts: Optional[float] = None,
                   required_verifier: Optional[str] = None, memo: str = "", now: Optional[float] = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO jobs (ts, payee, amount_usdc, status, expiry_ts, required_verifier, memo) "
            "VALUES (?, ?, ?, 'open', ?, ?, ?)",
            (
                now if now is not None else time.time(),
                payee.lower(),
                amount,
                expiry_ts,
                required_verifier.lower() if required_verifier else None,
                memo,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_job(self, job_id: int) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list_jobs(self, status: Optional[str] = None) -> list[dict]:
        if status:
            rows = self.conn.execute("SELECT * FROM jobs WHERE status = ? ORDER BY id DESC", (status,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    def set_status(self, job_id: int, status: str, tx_hash: Optional[str] = None) -> None:
        self.conn.execute("UPDATE jobs SET status = ?, tx_hash = ? WHERE id = ?", (status, tx_hash, job_id))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
