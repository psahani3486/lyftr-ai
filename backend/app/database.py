from __future__ import annotations

import json
import os
from typing import List, Optional, Tuple

import aiosqlite

_db_conn: Optional[aiosqlite.Connection] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata    TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
"""


async def init_db(db_path: str) -> None:
    global _db_conn
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    _db_conn = await aiosqlite.connect(db_path)
    _db_conn.row_factory = aiosqlite.Row
    await _db_conn.executescript(SCHEMA)
    await _db_conn.commit()


async def close_db() -> None:
    global _db_conn
    if _db_conn:
        await _db_conn.close()
        _db_conn = None


def get_db() -> aiosqlite.Connection:
    if _db_conn is None:
        raise RuntimeError("Database not initialised")
    return _db_conn


async def save_message(
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[dict] = None,
) -> None:
    db = get_db()
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(metadata) if metadata else None
    await db.execute(
        "INSERT INTO messages (session_id, role, content, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, meta_json, now),
    )
    await db.commit()


async def get_session_messages(session_id: str) -> List[dict]:
    db = get_db()
    cursor = await db.execute(
        "SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    )
    rows = await cursor.fetchall()
    results: List[dict] = []
    for row in rows:
        entry: dict = {"role": row[0], "content": row[1]}
        if row[2]:
            entry["metadata"] = json.loads(row[2])
        results.append(entry)
    return results


async def session_exists(session_id: str) -> bool:
    db = get_db()
    cursor = await db.execute(
        "SELECT 1 FROM messages WHERE session_id = ? LIMIT 1",
        (session_id,),
    )
    row = await cursor.fetchone()
    return row is not None


async def get_history_for_llm(session_id: str) -> List[dict]:
    """Return history as list of {role, content} for LLM context (no metadata)."""
    db = get_db()
    cursor = await db.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    )
    rows = await cursor.fetchall()
    return [{"role": row[0], "content": row[1]} for row in rows]
