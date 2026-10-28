from reqlens.storage import approval_rate, connect, save_run


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
