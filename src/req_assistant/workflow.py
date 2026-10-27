import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from req_assistant.ambiguity import find_vague_words
from req_assistant.models import Requirement
from req_assistant.pdf_reader import extract_requirements


class State(TypedDict, total=False):
    pdf: str
    requirements: list[Requirement]
    vague: dict[str, list[str]]
    conflicts: dict[str, str]
    report: str


def classic_extract(state: State) -> State:
    return {"requirements": extract_requirements(state["pdf"])}


def ai_extract(state: State) -> State:
    from req_assistant.ai_parser import extract_requirements_ai
    from req_assistant.llm import call_with_retry

    return {"requirements": call_with_retry(extract_requirements_ai, state["pdf"])}


def choose_extractor(state: State) -> str:
    return "ai_extract" if not state["requirements"] else "check_vague"


def check_vague(state: State) -> State:
    vague = {}
    for req in state["requirements"]:
        words = find_vague_words(req.text)
        if words:
            vague[req.id] = words
    return {"vague": vague}


def check_conflicts(state: State) -> State:
    from req_assistant.analysis_agent import make_conflict_checker
    from req_assistant.llm import call_with_retry

    check = make_conflict_checker(state["requirements"])
    conflicts = {}
    for req in state["requirements"]:
        if not re.search(r"\d", req.text):
            continue
        answer = call_with_retry(check, req.id)
        if "no conflict" not in answer.lower():
            conflicts[req.id] = answer
    return {"conflicts": conflicts}


def write_report(state: State) -> State:
    lines = [f"{len(state['requirements'])} requirements found."]
    for req_id, words in state["vague"].items():
        lines.append(f"{req_id}: vague words {words}")
    for req_id, reason in state["conflicts"].items():
        lines.append(f"{req_id}: {reason}")
    return {"report": "\n".join(lines)}


def build_workflow():
    graph = StateGraph(State)
    graph.add_node("classic_extract", classic_extract)
    graph.add_node("ai_extract", ai_extract)
    graph.add_node("check_vague", check_vague)
    graph.add_node("check_conflicts", check_conflicts)
    graph.add_node("write_report", write_report)

    graph.add_edge(START, "classic_extract")
    graph.add_conditional_edges("classic_extract", choose_extractor)
    graph.add_edge("ai_extract", "check_vague")
    graph.add_edge("check_vague", "check_conflicts")
    graph.add_edge("check_conflicts", "write_report")
    graph.add_edge("write_report", END)
    return graph.compile()
