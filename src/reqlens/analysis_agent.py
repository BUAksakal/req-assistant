import asyncio
from collections.abc import Callable

from llama_index.core.agent.workflow import FunctionAgent
from pydantic import BaseModel

from reqlens.llm import MissingAnswerError, get_llm
from reqlens.models import Requirement
from reqlens.requirement_index import build_index, search

SYSTEM_PROMPT = (
    "You review the requirements of a specification for conflicts. Two "
    "requirements conflict when they demand incompatible things, for example "
    "different values for the same parameter. Use find_related to look up "
    "requirements on the same topic before you decide. Only report conflicts "
    "that involve the requirement you were asked to check. List every "
    "conflicting requirement ID with a one-sentence reason, or an empty list "
    "if there is no conflict."
)


class Conflict(BaseModel):
    with_id: str
    reason: str


class ConflictReport(BaseModel):
    conflicts: list[Conflict]


def make_conflict_checker(
    requirements: list[Requirement],
    on_search: Callable[[str, list[str]], None] | None = None,
) -> Callable[[str, str], ConflictReport]:
    """Build the index once and return a function that checks one requirement.

    on_search is called with every query the agent sends to find_related and the
    IDs it got back, so a UI can show what the agent is doing.
    """
    by_id = {req.id: req for req in requirements}
    index = build_index(requirements)

    def find_related(query: str) -> str:
        """Find the requirements most similar to the query, with their text."""
        hits = search(index, query, top_k=4)
        if on_search:
            on_search(query, [rid for rid, _ in hits])
        return "\n".join(f"{rid}: {by_id[rid].text}" for rid, _ in hits)

    def check(requirement_id: str, model: str) -> ConflictReport:
        # A typed answer instead of free text: "There is no contradiction" can no
        # longer be mistaken for a conflict.
        agent = FunctionAgent(
            tools=[find_related],
            llm=get_llm(model),
            system_prompt=SYSTEM_PROMPT,
            output_cls=ConflictReport,
        )
        target = by_id[requirement_id]

        async def run() -> ConflictReport:
            response = await agent.run(f"Check {target.id}: {target.text}")
            report = response.get_pydantic_model(ConflictReport)
            if report is None:
                # Never read a missing answer as "no conflict": that would hide
                # conflicts whenever the quota runs out.
                raise MissingAnswerError("conflict report missing")
            return report

        return asyncio.run(run())

    return check
