import asyncio

from llama_index.core.agent.workflow import FunctionAgent

from req_assistant.llm import get_llm
from req_assistant.models import Requirement
from req_assistant.requirement_index import build_index, search

SYSTEM_PROMPT = (
    "You review the requirements of a specification for conflicts. Two "
    "requirements conflict when they demand incompatible things, for example "
    "different values for the same parameter. Use find_related to look up "
    "requirements on the same topic before you decide. Answer with the "
    "conflicting requirement IDs and a one-sentence reason, or 'no conflict'."
)


def check_conflicts(requirement_id: str, requirements: list[Requirement]) -> str:
    """Ask the agent whether one requirement conflicts with any other."""
    by_id = {req.id: req for req in requirements}
    index = build_index(requirements)

    def find_related(query: str) -> str:
        """Find the requirements most similar to the query, with their text."""
        hits = search(index, query, top_k=4)
        return "\n".join(f"{rid}: {by_id[rid].text}" for rid, _ in hits)

    agent = FunctionAgent(
        tools=[find_related], llm=get_llm(), system_prompt=SYSTEM_PROMPT
    )
    target = by_id[requirement_id]

    async def run() -> str:
        return str(await agent.run(f"Check {target.id}: {target.text}"))

    return asyncio.run(run())
