from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from req_assistant.ambiguity import find_vague_words
from req_assistant.models import Requirement
from req_assistant.pdf_reader import extract_requirements


class State(TypedDict, total=False):
    pdf: str
    requirements: list[Requirement]
    vague: dict[str, list[str]]
    report: str


def classic_extract(state: State) -> State:
    return {"requirements": extract_requirements(state["pdf"])}


def ai_extract(state: State) -> State:
    from req_assistant.ai_parser import extract_requirements_ai

    return {"requirements": extract_requirements_ai(state["pdf"])}


def choose_extractor(state: State) -> str:
    return "ai_extract" if not state["requirements"] else "check_vague"


def check_vague(state: State) -> State:
    vague = {}
    for req in state["requirements"]:
        words = find_vague_words(req.text)
        if words:
            vague[req.id] = words
    return {"vague": vague}


def write_report(state: State) -> State:
    lines = [f"{len(state['requirements'])} requirements found."]
    for req_id, words in state["vague"].items():
        lines.append(f"{req_id}: vague words {words}")
    return {"report": "\n".join(lines)}


def build_workflow():
    graph = StateGraph(State)
    graph.add_node("classic_extract", classic_extract)
    graph.add_node("ai_extract", ai_extract)
    graph.add_node("check_vague", check_vague)
    graph.add_node("write_report", write_report)

    graph.add_edge(START, "classic_extract")
    graph.add_conditional_edges("classic_extract", choose_extractor)
    graph.add_edge("ai_extract", "check_vague")
    graph.add_edge("check_vague", "write_report")
    graph.add_edge("write_report", END)
    return graph.compile()
