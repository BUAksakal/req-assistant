"""Remember LLM answers so the same document never costs Gemini requests twice."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from reqlens.storage import DB_PATH, connect


def fingerprint(data: str | bytes) -> str:
    """Short hash of a document; it changes as soon as one character changes."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:16]


def lookup(key: str, path: Path = DB_PATH) -> str | None:
    """Return the stored answer for key, or None if the LLM was never asked."""
    row = (
        connect(path)
        .execute("SELECT value FROM llm_cache WHERE key = ?", (key,))
        .fetchone()
    )
    return row[0] if row else None


def store(key: str, value: str, path: Path = DB_PATH) -> None:
    """Save an LLM answer under key."""
    conn = connect(path)
    conn.execute(
        "INSERT OR REPLACE INTO llm_cache (key, value, created_at) VALUES (?, ?, ?)",
        (key, value, datetime.now(UTC).isoformat(timespec="seconds")),
    )
    conn.commit()
