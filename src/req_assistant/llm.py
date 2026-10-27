from dotenv import load_dotenv
from llama_index.llms.google_genai import GoogleGenAI

load_dotenv()

MODEL = "gemini-3.5-flash"


def get_llm() -> GoogleGenAI:
    return GoogleGenAI(model=MODEL)
