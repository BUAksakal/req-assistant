import time
from collections.abc import Callable

from dotenv import load_dotenv
from google.genai import errors
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.llms.google_genai import GoogleGenAI

load_dotenv()

MODELS = ["gemini-3.1-flash-lite", "gemini-2.5-flash"]
EMBED_MODEL = "gemini-embedding-001"
RETRY_CODES = {429, 503}


class LLMUnavailableError(RuntimeError):
    """Every model was busy or out of quota."""


def get_llm(model: str = MODELS[0]) -> GoogleGenAI:
    return GoogleGenAI(model=model)


def get_embed_model() -> GoogleGenAIEmbedding:
    return GoogleGenAIEmbedding(model_name=EMBED_MODEL)


def call_with_fallback[T](fn: Callable[[str], T], attempts: int = 2) -> T:
    """Call fn(model) and switch to the next model when one is busy (503/429)."""
    for model in MODELS:
        for attempt in range(1, attempts + 1):
            try:
                return fn(model)
            except (errors.ClientError, errors.ServerError) as error:
                if error.code not in RETRY_CODES:
                    raise
                print(f"{model} busy ({error.code}), attempt {attempt}/{attempts}")
                time.sleep(10)
    raise LLMUnavailableError(
        "All Gemini models are busy right now. Please try again in a few minutes."
    )
