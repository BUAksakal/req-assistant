"""Supervisor agent: the LLM decisions that steer the LangGraph workflow.

It makes two decisions. After the classic extraction it checks whether
requirements were missed, and after the conflict agent it double-checks every
conflict before the engineer sees it.
"""

import re
from typing import Literal

from llama_index.core.prompts import PromptTemplate
from pydantic import BaseModel

from reqlens.llm import get_llm
from reqlens.models import Requirement

EXTRACTION_PROMPT = PromptTemplate(
    "You supervise a requirements extraction pipeline. A rule-based extractor "
    "found {found} requirements in a specification. These passages contain "
    "'shall' but were not extracted:\n{missed}\n\n"
    "If they are real requirements that the extractor missed, answer use_llm so "
    "an LLM extractor reads the whole document. If they are introductions, notes, "
    "legal text or instructions to the supplier, answer accept."
)

VERIFY_PROMPT = PromptTemplate(
    "Another agent claims that these two requirements conflict.\n"
    "{first}\n{second}\nClaim: {claim}\n\n"
    "Your job is to catch false alarms before an engineer reviews the claim. "
    "In a specification, two different values or limits for the same property "
    "under the same conditions are a real conflict, even if a design could meet "
    "the stricter one. Convert units before you compare values.\n"
    "Answer false_alarm only if the claim is clearly wrong: it misreads a value, "
    "or the requirements are about different things (different sensors, inputs, "
    "modes or conditions). Answer real if the claim holds, and unsure if you "
    "cannot tell. Give a one-sentence reason."
)


class ExtractionDecision(BaseModel):
    action: Literal["accept", "use_llm"]
    reason: str


class Verdict(BaseModel):
    verdict: Literal["real", "false_alarm", "unsure"]
    reason: str

    @property
    def keep(self) -> bool:
        """Only a clear false alarm is dropped. Missing a conflict costs more
        than showing the engineer one extra finding."""
        return self.verdict != "false_alarm"


def unextracted_shall_passages(
    pages: list[str], requirements: list[Requirement]
) -> list[str]:
    """Return passages with 'shall' that no extracted requirement contains."""
    text = re.sub(r"\s+", " ", " ".join(pages))
    covered = re.sub(r"\s+", " ", " ".join(req.text for req in requirements))
    passages = []
    for match in re.finditer(r"\S+ shall(?: [^ .]+){0,4}", text):
        if match.group() not in covered:
            start = max(match.start() - 80, 0)
            passages.append(text[start : match.end() + 80].strip())
    return passages


def decide_extraction(found: int, missed: list[str], model: str) -> ExtractionDecision:
    passages = "\n".join(f"- {passage}" for passage in missed[:5])
    return get_llm(model).structured_predict(
        ExtractionDecision, EXTRACTION_PROMPT, found=str(found), missed=passages
    )


def verify_conflict(
    first: Requirement, second: Requirement, claim: str, model: str
) -> Verdict:
    return get_llm(model).structured_predict(
        Verdict,
        VERIFY_PROMPT,
        first=f"{first.id}: {first.text}",
        second=f"{second.id}: {second.text}",
        claim=claim,
    )
