import time
from collections.abc import Callable

from dotenv import load_dotenv
from google.genai import errors
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.llms.google_genai import GoogleGenAI

load_dotenv()

# Every model has its own free-tier quota, so more models mean more free capacity.
MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
]
EMBED_MODEL = "gemini-embedding-001"
RETRY_CODES = {429, 503}
SKIP_CODES = {404}


class LLMUnavailableError(RuntimeError):
    """Every model was busy or out of quota."""


def get_llm(model: str = MODELS[0]) -> GoogleGenAI:
    return GoogleGenAI(model=model)


def get_embed_model() -> GoogleGenAIEmbedding:
    return GoogleGenAIEmbedding(model_name=EMBED_MODEL)


_last_working = 0


def call_with_fallback[T](fn: Callable[[str], T], attempts: int = 2) -> T:
    """Call fn(model) and switch to the next model when one is busy (503/429).

    Starts with the model that answered last time, so a busy model is not
    retried for every single call.
    """
    global _last_working
    order = list(range(_last_working, len(MODELS))) + list(range(_last_working))
    for index in order:
        model = MODELS[index]
        for attempt in range(1, attempts + 1):
            try:
                result = fn(model)
                _last_working = index
                return result
            except (errors.ClientError, errors.ServerError) as error:
                if error.code in SKIP_CODES:
                    print(f"{model} is not available ({error.code}), skipping it")
                    break
                if error.code not in RETRY_CODES:
                    raise
                print(f"{model} busy ({error.code}), attempt {attempt}/{attempts}")
                time.sleep(10)
    raise LLMUnavailableError(
        "All Gemini models are busy right now. Please try again in a few minutes."
    )
