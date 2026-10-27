import asyncio
from collections.abc import Callable

from llama_index.core.agent.workflow import FunctionAgent

from reqlens.llm import get_llm
from reqlens.models import Requirement
from reqlens.requirement_index import build_index, search

SYSTEM_PROMPT = (
    "You review the requirements of a specification for conflicts. Two "
    "requirements conflict when they demand incompatible things, for example "
    "different values for the same parameter. Use find_related to look up "
    "requirements on the same topic before you decide. Only report conflicts "
    "that involve the requirement you were asked to check. Answer with the "
    "conflicting requirement ID and a one-sentence reason, or 'no conflict'."
)


def make_conflict_checker(requirements: list[Requirement]) -> Callable[[str], str]:
    """Build the index once and return a function that checks one requirement."""
    by_id = {req.id: req for req in requirements}
    index = build_index(requirements)

    def find_related(query: str) -> str:
        """Find the requirements most similar to the query, with their text."""
        hits = search(index, query, top_k=4)
        return "\n".join(f"{rid}: {by_id[rid].text}" for rid, _ in hits)

    agent = FunctionAgent(
        tools=[find_related], llm=get_llm(), system_prompt=SYSTEM_PROMPT
    )

    def check(requirement_id: str) -> str:
        target = by_id[requirement_id]

        async def run() -> str:
            return str(await agent.run(f"Check {target.id}: {target.text}"))

        return asyncio.run(run())

    return check
