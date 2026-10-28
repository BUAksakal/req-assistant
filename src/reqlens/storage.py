import sqlite3
from datetime import UTC, datetime
from pathlib import Path

DB_PATH = Path("reqlens.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pdf TEXT NOT NULL,
    created_at TEXT NOT NULL,
    requirement_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    description TEXT NOT NULL,
    approved INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    """Open the database and create the tables if they do not exist yet."""
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def save_run(
    conn: sqlite3.Connection,
    pdf: str,
    requirement_count: int,
    findings: list[str],
    approved: list[str],
) -> int:
    """Store one analysis and every finding with the engineer's decision."""
    created_at = datetime.now(UTC).isoformat(timespec="seconds")
    cursor = conn.execute(
        "INSERT INTO runs (pdf, created_at, requirement_count) VALUES (?, ?, ?)",
        (pdf, created_at, requirement_count),
    )
    run_id = cursor.lastrowid
    conn.executemany(
        "INSERT INTO findings (run_id, description, approved) VALUES (?, ?, ?)",
        [(run_id, finding, int(finding in approved)) for finding in findings],
    )
    conn.commit()
    return run_id


def approval_rate(conn: sqlite3.Connection) -> float:
    """Share of all findings that engineers confirmed as real problems."""
    approved, total = conn.execute(
        "SELECT SUM(approved), COUNT(*) FROM findings"
    ).fetchone()
    return approved / total if total else 0.0


def list_runs(conn: sqlite3.Connection) -> list[tuple]:
    """One row per analysis: id, date, pdf, requirements, findings, approved."""
    return conn.execute(
        """
        SELECT r.id, r.created_at, r.pdf, r.requirement_count,
               COUNT(f.id), COALESCE(SUM(f.approved), 0)
        FROM runs r LEFT JOIN findings f ON f.run_id = r.id
        GROUP BY r.id
        ORDER BY r.id
        """
    ).fetchall()
