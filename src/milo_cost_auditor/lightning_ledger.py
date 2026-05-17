"""
Local SQLite ledger of Lightning-paid invoices and their issued pro_keys.

Lives at ~/.milo-cost-auditor/lightning_paid.db (or $MILO_COST_AUDITOR_HOME).
Single source of truth for "did this payment_hash settle, and what pro_key
did we issue against it?"

Schema:
    invoices(
        payment_hash TEXT PRIMARY KEY,
        amount_sats INTEGER NOT NULL,
        tier TEXT NOT NULL,
        memo TEXT,
        bolt11 TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        paid_at INTEGER,
        pro_key TEXT,
        days_valid INTEGER NOT NULL DEFAULT 30,
        provider TEXT NOT NULL DEFAULT 'lnbits'
    )

Idempotency: payment_hash is the natural key. Re-recording a paid invoice
is a no-op. Re-claiming a key returns the existing key.

Privacy note: the bolt11 string + raw pro_key live in this file. Operators
should treat ~/.milo-cost-auditor/lightning_paid.db as sensitive — it's not
encrypted at rest. The PayPal IPN ledger upstream stores only sha8 hashes;
LN here stores the key because the watcher needs to return it to the buyer.
"""

from __future__ import annotations

import contextlib
import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterable, List, Optional

from milo_cost_auditor import telemetry  # reuses ensure_home() + MILO_COST_AUDITOR_HOME

_LOCK = threading.Lock()
DB_NAME = "lightning_paid.db"


def _db_path() -> Path:
    return telemetry.ensure_home() / DB_NAME


@contextlib.contextmanager
def _conn():
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            payment_hash TEXT PRIMARY KEY,
            amount_sats INTEGER NOT NULL,
            tier TEXT NOT NULL,
            memo TEXT,
            bolt11 TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            paid_at INTEGER,
            pro_key TEXT,
            days_valid INTEGER NOT NULL DEFAULT 30,
            provider TEXT NOT NULL DEFAULT 'lnbits'
        )
        """
    )


def record_invoice(
    payment_hash: str,
    *,
    amount_sats: int,
    tier: str,
    bolt11: str,
    memo: str = "",
    days_valid: int = 30,
    provider: str = "lnbits",
) -> None:
    """Insert a fresh invoice. No-op if payment_hash already exists."""
    if not payment_hash:
        raise ValueError("payment_hash required")
    now = int(time.time())
    with _LOCK, _conn() as conn:
        _init_schema(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO invoices
                (payment_hash, amount_sats, tier, memo, bolt11,
                 created_at, paid_at, pro_key, days_valid, provider)
            VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (payment_hash, amount_sats, tier, memo, bolt11, now, days_valid, provider),
        )


def mark_paid(payment_hash: str, *, pro_key: str) -> bool:
    """Mark a payment as settled and attach the issued pro_key.

    Returns True if this transition happened (paid_at was previously NULL).
    Returns False if the invoice was already paid (idempotent re-call) or
    no row exists for this payment_hash.
    """
    if not payment_hash or not pro_key:
        raise ValueError("payment_hash and pro_key required")
    now = int(time.time())
    with _LOCK, _conn() as conn:
        _init_schema(conn)
        row = conn.execute(
            "SELECT paid_at FROM invoices WHERE payment_hash = ?",
            (payment_hash,),
        ).fetchone()
        if row is None:
            return False
        if row["paid_at"] is not None:
            return False  # already paid; do not overwrite the key
        conn.execute(
            "UPDATE invoices SET paid_at = ?, pro_key = ? WHERE payment_hash = ?",
            (now, pro_key, payment_hash),
        )
        return True


def claim_paid_key(payment_hash: str) -> Optional[str]:
    """Return the pro_key for a paid invoice, or None if not paid / not found."""
    if not payment_hash:
        return None
    with _conn() as conn:
        _init_schema(conn)
        row = conn.execute(
            "SELECT pro_key, paid_at FROM invoices WHERE payment_hash = ?",
            (payment_hash,),
        ).fetchone()
    if row is None:
        return None
    if row["paid_at"] is None:
        return None
    return row["pro_key"]


def list_outstanding(*, max_age_hours: int = 24 * 7) -> List[sqlite3.Row]:
    """Return rows for invoices that are not yet paid and within max_age_hours."""
    cutoff = int(time.time()) - (max_age_hours * 3600)
    with _conn() as conn:
        _init_schema(conn)
        rows = conn.execute(
            "SELECT * FROM invoices WHERE paid_at IS NULL AND created_at >= ? "
            "ORDER BY created_at ASC",
            (cutoff,),
        ).fetchall()
    return list(rows)


def get(payment_hash: str) -> Optional[sqlite3.Row]:
    with _conn() as conn:
        _init_schema(conn)
        return conn.execute(
            "SELECT * FROM invoices WHERE payment_hash = ?",
            (payment_hash,),
        ).fetchone()


def reset_for_tests() -> None:
    """Test-only: wipe the LN ledger."""
    p = _db_path()
    if p.exists():
        p.unlink()
