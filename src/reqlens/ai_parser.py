from pathlib import Path

from llama_index.core.prompts import PromptTemplate
from pydantic import BaseModel

from reqlens.llm import MODELS, get_llm
from reqlens.models import Requirement
from reqlens.pdf_reader import read_pages

PROMPT = PromptTemplate(
    "Below is the text of a specification document. Each page starts with a\n"
    "line like '=== PAGE 3 ==='.\n"
    "List every requirement that is DEFINED in the document. A requirement has\n"
    "an ID and a statement, usually containing 'shall'. Ignore headers, footers,\n"
    "notes, tables of contents and tables that only reference requirement IDs.\n"
    "For each requirement give its ID, its full text on one line, copied exactly,\n"
    "and the page where its ID appears.\n\n"
    "{document}"
)


class FoundRequirement(BaseModel):
    id: str
    text: str
    page: int


class DocumentResult(BaseModel):
    requirements: list[FoundRequirement]


def extract_requirements_ai(path: Path, model: str = MODELS[0]) -> list[Requirement]:
    """Send the whole PDF text to the LLM and let it find the requirements."""
    pages = read_pages(path)
    document = "\n".join(
        f"=== PAGE {number} ===\n{text}" for number, text in enumerate(pages, start=1)
    )
    result = get_llm(model).structured_predict(
        DocumentResult, PROMPT, document=document
    )
    source = Path(path).name
    return [
        Requirement(id=r.id, text=r.text, source=source, page=r.page)
        for r in result.requirements
    ]
