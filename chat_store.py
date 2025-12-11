"""SQLite helper for storing YouTube live chat messages."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_LIMIT = 50

_db: Optional[sqlite3.Connection] = None
_db_path: Optional[str] = None

_INSERT_SQL = """
INSERT OR IGNORE INTO comments
  (id, video_id, timestamp_ms, timestamp, author, text, kind, amount, amount_text, icon, parts_json, colors_json)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _ensure_colors_column(conn: sqlite3.Connection) -> None:
    """Add colors_json if it does not exist (backward compatibility)."""
    cur = conn.execute("PRAGMA table_info(comments)")
    columns = [row[1] for row in cur.fetchall()]
    if "colors_json" in columns:
        return
    conn.execute("ALTER TABLE comments ADD COLUMN colors_json TEXT")
    conn.commit()


def init_chat_store(base_dir: Optional[str] = None) -> str:
    """Initialize the SQLite database under base_dir (defaults to CWD)."""
    global _db, _db_path
    directory = Path(base_dir or os.getcwd())
    directory.mkdir(parents=True, exist_ok=True)

    _db_path = str(directory / "comments.db")
    _db = sqlite3.connect(_db_path, check_same_thread=False)
    _db.execute(
        """
        CREATE TABLE IF NOT EXISTS comments (
          id TEXT PRIMARY KEY,
          video_id TEXT,
          timestamp_ms INTEGER,
          timestamp TEXT,
          author TEXT,
          text TEXT,
          kind TEXT,
          amount INTEGER,
          amount_text TEXT,
          icon TEXT,
          parts_json TEXT,
          colors_json TEXT
        )
        """
    )
    _ensure_colors_column(_db)
    _db.commit()
    return _db_path


def save_comment(msg: Dict[str, Any]) -> None:
    """Persist a single chat message."""
    if _db is None or not msg or "id" not in msg:
        return

    parts_json = json.dumps(msg.get("parts") or [])
    colors_json = json.dumps(msg.get("colors")) if "colors" in msg else json.dumps(None)

    try:
        _db.execute(
            _INSERT_SQL,
            (
                msg.get("id"),
                msg.get("video_id"),
                msg.get("timestamp_ms"),
                msg.get("timestamp"),
                msg.get("author"),
                msg.get("text"),
                msg.get("kind"),
                msg.get("amount"),
                msg.get("amount_text"),
                msg.get("icon"),
                parts_json,
                colors_json,
            ),
        )
        _db.commit()
    except sqlite3.DatabaseError as exc:
        print(f"save_comment sqlite error: {exc}")


def get_recent_comments(limit: int = DEFAULT_LIMIT) -> List[Dict[str, Any]]:
    """Fetch most recent comments (oldest first in the returned list)."""
    if _db is None:
        return []
    lim = limit if 1 <= limit <= 500 else DEFAULT_LIMIT
    sql = """
      SELECT id, video_id, timestamp_ms, timestamp, author, text, kind, amount, amount_text, icon, parts_json, colors_json
      FROM comments
      ORDER BY timestamp_ms DESC, rowid DESC
      LIMIT ?
    """
    try:
        cur = _db.execute(sql, (lim,))
        rows = cur.fetchall()
    except sqlite3.DatabaseError as exc:
        print(f"get_recent_comments sqlite error: {exc}")
        return []

    result: List[Dict[str, Any]] = []
    for row in reversed(rows):
        try:
            parts = json.loads(row[10]) if row[10] else []
        except json.JSONDecodeError:
            parts = []
        try:
            colors = json.loads(row[11]) if row[11] else None
        except json.JSONDecodeError:
            colors = None
        result.append(
            {
                "id": row[0],
                "video_id": row[1],
                "timestamp_ms": row[2],
                "timestamp": row[3],
                "author": row[4],
                "text": row[5],
                "kind": row[6],
                "amount": row[7],
                "amount_text": row[8],
                "icon": row[9],
                "parts": parts,
                "colors": colors,
            }
        )
    return result


def close_chat_store() -> None:
    """Close the database."""
    global _db
    if _db is not None:
        _db.close()
    _db = None


def get_db_path() -> Optional[str]:
    return _db_path


__all__ = [
    "init_chat_store",
    "save_comment",
    "get_recent_comments",
    "close_chat_store",
    "get_db_path",
]
