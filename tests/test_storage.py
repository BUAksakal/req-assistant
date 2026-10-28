from typer.testing import CliRunner

from reqlens.cli import app
from reqlens.storage import (
    analyses_today,
    approval_rate,
    connect,
    record_analysis,
    save_run,
)


def test_save_run_and_approval_rate(tmp_path):
    conn = connect(tmp_path / "test.db")
    save_run(
        conn, "spec.pdf", 18, ["AEB-003 vague", "AEB-004 conflict"], ["AEB-003 vague"]
    )

    assert conn.execute("SELECT pdf, requirement_count FROM runs").fetchone() == (
        "spec.pdf",
        18,
    )
    assert approval_rate(conn) == 0.5


def test_empty_database_has_zero_rate(tmp_path):
    assert approval_rate(connect(tmp_path / "test.db")) == 0.0


def test_history_command_shows_runs(tmp_path):
    db = tmp_path / "test.db"
    save_run(connect(db), "spec.pdf", 18, ["AEB-003 vague"], ["AEB-003 vague"])

    result = CliRunner().invoke(app, ["history", "--db", str(db)])
    assert "#1" in result.output
    assert "1/1 findings approved" in result.output
    assert "100%" in result.output


def test_started_analyses_are_counted_for_today(tmp_path):
    conn = connect(tmp_path / "test.db")
    conn.execute("INSERT INTO analyses (started_at) VALUES ('2020-01-01T10:00:00')")
    record_analysis(conn)
    record_analysis(conn)

    assert analyses_today(conn) == 2
