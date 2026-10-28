import pytest
from google.genai import errors

from reqlens import llm

BUSY = errors.ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE"}}, None)


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(llm, "_last_working", 0)


def test_falls_back_and_remembers_the_working_model():
    calls = []

    def fn(model):
        calls.append(model)
        if model == llm.MODELS[0]:
            raise BUSY
        return "ok"

    llm.call_with_fallback(fn)
    llm.call_with_fallback(fn)

    assert calls == [llm.MODELS[0], llm.MODELS[0], llm.MODELS[1], llm.MODELS[1]]


def test_all_models_busy_raises_a_clear_error():
    def fn(model):
        raise BUSY

    with pytest.raises(llm.LLMUnavailableError):
        llm.call_with_fallback(fn)
