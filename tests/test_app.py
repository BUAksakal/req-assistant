from pathlib import Path

from streamlit.testing.v1 import AppTest

from reqlens.storage import connect, record_analysis

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def start(tmp_path, monkeypatch, **state):
    monkeypatch.chdir(tmp_path)  # a fresh reqlens.db for every test
    app = AppTest.from_file(APP)
    for key, value in state.items():
        app.session_state[key] = value
    return app.run()


def page_text(app) -> str:
    return " ".join(element.proto.body for element in app.get("html"))


def test_a_new_visitor_has_three_analyses(tmp_path, monkeypatch):
    app = start(tmp_path, monkeypatch)

    assert not app.exception
    assert "3 of 3 analyses left" in page_text(app)


def test_the_session_limit_blocks_analyze(tmp_path, monkeypatch):
    app = start(tmp_path, monkeypatch, analyses_started=3)

    assert "used the 3 analyses" in page_text(app)
    assert app.button[0].disabled


def test_the_daily_limit_counts_every_visitor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    conn = connect()
    for _ in range(25):
        record_analysis(conn)

    app = start(tmp_path, monkeypatch)

    assert "today's limit of 25 analyses" in page_text(app)
    assert app.button[0].disabled
