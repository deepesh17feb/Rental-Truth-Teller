# agents/persistence.py
"""
agents/persistence.py
──────────────────────
SQLite-backed storage for verification results, so past verdicts can be
revisited instead of discarded after each request. Every function opens
and closes its own connection — no shared global connection object —
since this is called both from LangGraph's own parallel node execution
and from FastAPI's concurrent request threads.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel

from config.settings import config as global_config

log = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS verdicts (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    listing_input TEXT NOT NULL,
    locality TEXT,
    rent_amount REAL,
    overpriced_percentage REAL,
    neighbourhood_score REAL,
    address_resolved_json TEXT,
    pricing_data_json TEXT,
    vibe_data_json TEXT,
    neighbourhood_data_json TEXT,
    final_verdict_json TEXT
)
"""


class VerdictSummary(BaseModel):
    id: str
    created_at: str
    locality: str
    rent_amount: float
    overpriced_percentage: float
    neighbourhood_score: float


class VerdictDetail(BaseModel):
    id: str
    created_at: str
    listing_input: str
    address_resolved: Optional[dict] = None
    pricing_data: Optional[dict] = None
    vibe_data: Optional[dict] = None
    neighbourhood_data: Optional[dict] = None
    final_verdict: Optional[dict] = None


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(global_config.VERDICT_DB_PATH)
    conn.execute(_CREATE_TABLE_SQL)
    conn.commit()
    return conn


def save_verdict(listing_input: str, final_state: dict) -> str:
    """Persists one verification's full result. Returns the generated verdict id."""
    verdict_id = uuid.uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat()

    address_resolved = final_state.get("address_resolved")
    pricing_data = final_state.get("pricing_data")
    vibe_data = final_state.get("vibe_data")
    neighbourhood_data = final_state.get("neighbourhood_data")
    final_verdict = final_state.get("final_verdict")

    locality = address_resolved.locality if address_resolved else None
    rent_amount = pricing_data.rent_amount if pricing_data else None
    overpriced_percentage = final_verdict.overpriced_percentage if final_verdict else None
    neighbourhood_score = final_verdict.neighbourhood_score if final_verdict else None

    conn = _get_connection()
    try:
        conn.execute(
            """
            INSERT INTO verdicts (
                id, created_at, listing_input, locality, rent_amount,
                overpriced_percentage, neighbourhood_score,
                address_resolved_json, pricing_data_json, vibe_data_json,
                neighbourhood_data_json, final_verdict_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                verdict_id,
                created_at,
                listing_input,
                locality,
                rent_amount,
                overpriced_percentage,
                neighbourhood_score,
                address_resolved.model_dump_json() if address_resolved else None,
                pricing_data.model_dump_json() if pricing_data else None,
                vibe_data.model_dump_json() if vibe_data else None,
                neighbourhood_data.model_dump_json() if neighbourhood_data else None,
                final_verdict.model_dump_json() if final_verdict else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    log.info(f"[persistence] Saved verdict {verdict_id} for locality={locality!r}.")
    return verdict_id


def list_verdicts(limit: int = 20) -> list[VerdictSummary]:
    """Returns the most recent verdicts, newest first."""
    conn = _get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, created_at, locality, rent_amount, overpriced_percentage, neighbourhood_score
            FROM verdicts
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    return [
        VerdictSummary(
            id=row[0],
            created_at=row[1],
            locality=row[2] or "",
            rent_amount=row[3] or 0.0,
            overpriced_percentage=row[4] or 0.0,
            neighbourhood_score=row[5] or 0.0,
        )
        for row in rows
    ]


def get_verdict(verdict_id: str) -> Optional[VerdictDetail]:
    """Returns the full persisted record for one verdict id, or None if not found."""
    conn = _get_connection()
    try:
        row = conn.execute(
            """
            SELECT id, created_at, listing_input, address_resolved_json,
                   pricing_data_json, vibe_data_json, neighbourhood_data_json,
                   final_verdict_json
            FROM verdicts
            WHERE id = ?
            """,
            (verdict_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    return VerdictDetail(
        id=row[0],
        created_at=row[1],
        listing_input=row[2],
        address_resolved=json.loads(row[3]) if row[3] else None,
        pricing_data=json.loads(row[4]) if row[4] else None,
        vibe_data=json.loads(row[5]) if row[5] else None,
        neighbourhood_data=json.loads(row[6]) if row[6] else None,
        final_verdict=json.loads(row[7]) if row[7] else None,
    )
