import time
from collections.abc import Callable

from dotenv import load_dotenv
from google.genai import errors
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.llms.google_genai import GoogleGenAI

load_dotenv()

MODEL = "gemini-3.1-flash-lite"
EMBED_MODEL = "gemini-embedding-001"
RETRY_CODES = {429, 503}


def get_llm() -> GoogleGenAI:
    return GoogleGenAI(model=MODEL)


def get_embed_model() -> GoogleGenAIEmbedding:
    return GoogleGenAIEmbedding(model_name=EMBED_MODEL)


def call_with_retry[T](fn: Callable[..., T], *args, attempts: int = 4) -> T:
    """Call fn again after a pause when the LLM is busy (503) or rate limited (429)."""
    for attempt in range(1, attempts + 1):
        try:
            return fn(*args)
        except (errors.ClientError, errors.ServerError) as error:
            if error.code not in RETRY_CODES or attempt == attempts:
                raise
            print(f"LLM busy ({error.code}), retrying in {15 * attempt} s...")
            time.sleep(15 * attempt)
