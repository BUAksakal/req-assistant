import json
from collections.abc import Callable
from functools import partial
from pathlib import Path

from llama_index.core.prompts import PromptTemplate
from pydantic import BaseModel

from reqlens.cache import fingerprint, lookup, store
from reqlens.llm import LLMUnavailableError, call_with_fallback, get_llm
from reqlens.models import Requirement
from reqlens.pdf_reader import read_pages
from reqlens.storage import DB_PATH

CHUNK_PAGES = 8
# 60 pages are 9 chunks, so one document can never use up the free daily quota.
MAX_PAGES = 60


class DocumentTooLargeError(LLMUnavailableError):
    """The document has too many pages to send to the LLM."""


PROMPT = PromptTemplate(
    "Below are some pages of a specification document. Each page starts with a\n"
    "line like '=== PAGE 3 ==='.\n"
    "List every requirement that is DEFINED on these pages. A requirement has\n"
    "an ID or paragraph number and a statement, usually containing 'shall'.\n"
    "Requirements written inside tables count too. Ignore headers, footers,\n"
    "notes, tables of contents and tables that only reference requirement IDs.\n"
    "For each requirement give its ID, its full text on one line, copied exactly,\n"
    "and the page where its ID appears.\n"
    "Use the ID or paragraph number exactly as printed and never invent one.\n"
    "A sentence without a number of its own, such as a table footnote or a\n"
    "follow-up sentence, belongs to the numbered paragraph above it: add it to\n"
    "that paragraph's text instead of listing it separately. Inside an annex,\n"
    "write the annex in front of the number, for example 'Annex 3 3.1'.\n\n"
    "{document}"
)


class FoundRequirement(BaseModel):
    id: str
    text: str
    page: int


class DocumentResult(BaseModel):
    requirements: list[FoundRequirement]


def page_chunks(
    pages: list[str], size: int = CHUNK_PAGES
) -> list[tuple[int, list[str]]]:
    """Split pages into chunks that overlap by one page.

    The overlap makes sure a requirement that starts at the bottom of one chunk
    is seen in full by the next one. Each chunk is returned with the number of
    its first page.
    """
    if not pages:
        return []
    step = max(size - 1, 1)
    return [
        (start + 1, pages[start : start + size])
        for start in range(0, max(len(pages) - 1, 1), step)
    ]


def extract_chunk(
    first_page: int, pages: list[str], model: str
) -> list[FoundRequirement]:
    """Ask the LLM for the requirements defined on a few pages."""
    document = "\n".join(
        f"=== PAGE {first_page + i} ===\n{text}" for i, text in enumerate(pages)
    )
    result = get_llm(model).structured_predict(
        DocumentResult, PROMPT, document=document
    )
    return result.requirements


def normalize_id(raw: str) -> str:
    """Make '5.5.2.' and '5.5.2' the same ID, as different chunks write either."""
    return " ".join(raw.split()).rstrip(".")


def extract_with_cache(
    path: Path,
    on_chunk: Callable[[int, int], None] | None = None,
    db: Path = DB_PATH,
) -> list[Requirement]:
    """LLM extraction, a few pages at a time, each chunk asked only once.

    Short chunks keep the LLM attentive: on a 38-page regulation one request for
    the whole text stopped after page 20. When the same ID shows up in two
    overlapping chunks, the longer text wins.
    """
    path = Path(path)
    all_pages = read_pages(path)
    if len(all_pages) > MAX_PAGES:
        raise DocumentTooLargeError(
            f"{path.name} has {len(all_pages)} pages. The LLM reads at most "
            f"{MAX_PAGES} pages per document, please split it."
        )
    found: dict[str, Requirement] = {}
    for first, pages in page_chunks(all_pages):
        if on_chunk:
            on_chunk(first, first + len(pages) - 1)
        # The prompt is part of the key: new instructions must not reuse old answers.
        key = f"extract-chunk:{fingerprint(PROMPT.template + ''.join(pages))}:{first}"
        saved = lookup(key, db)
        if saved is None:
            items = call_with_fallback(partial(extract_chunk, first, pages))
            saved = json.dumps([item.model_dump() for item in items])
            store(key, saved, db)
        for item in json.loads(saved):
            req = Requirement(
                **{**item, "id": normalize_id(item["id"])}, source=path.name
            )
            if req.id not in found or len(req.text) > len(found[req.id].text):
                found[req.id] = req
    return sorted(found.values(), key=lambda req: req.page)
