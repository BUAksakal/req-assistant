from dotenv import load_dotenv
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.llms.google_genai import GoogleGenAI

load_dotenv()

MODEL = "gemini-2.5-flash"
EMBED_MODEL = "gemini-embedding-001"


def get_llm() -> GoogleGenAI:
    return GoogleGenAI(model=MODEL)


def get_embed_model() -> GoogleGenAIEmbedding:
    return GoogleGenAIEmbedding(model_name=EMBED_MODEL)
