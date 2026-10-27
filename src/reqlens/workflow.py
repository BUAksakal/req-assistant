import re
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from reqlens.ambiguity import find_vague_words
from reqlens.models import Requirement
from reqlens.pdf_reader import extract_requirements


class State(TypedDict, total=False):
    pdf: str
    requirements: list[Requirement]
    vague: dict[str, list[str]]
    conflicts: dict[str, str]
    approved: list[str]
    report: str


def classic_extract(state: State) -> State:
    return {"requirements": extract_requirements(state["pdf"])}


def ai_extract(state: State) -> State:
    from reqlens.ai_parser import extract_requirements_ai
    from reqlens.llm import call_with_retry

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
    from reqlens.analysis_agent import make_conflict_checker
    from reqlens.llm import call_with_retry

    check = make_conflict_checker(state["requirements"])
    conflicts = {}
    for req in state["requirements"]:
        if not re.search(r"\d", req.text):
            continue
        answer = call_with_retry(check, req.id)
        if "no conflict" not in answer.lower():
            conflicts[req.id] = answer
    return {"conflicts": conflicts}


def review(state: State) -> State:
    findings = [f"{rid}: vague words {w}" for rid, w in state["vague"].items()]
    findings += [f"{rid}: {reason}" for rid, reason in state["conflicts"].items()]
    approved = interrupt(findings)
    return {"approved": approved}


def write_report(state: State) -> State:
    lines = [f"{len(state['requirements'])} requirements found."]
    lines += state["approved"]
    lines.append(f"{len(state['approved'])} findings approved by the engineer.")
    return {"report": "\n".join(lines)}


def build_workflow():
    graph = StateGraph(State)
    graph.add_node("classic_extract", classic_extract)
    graph.add_node("ai_extract", ai_extract)
    graph.add_node("check_vague", check_vague)
    graph.add_node("check_conflicts", check_conflicts)
    graph.add_node("review", review)
    graph.add_node("write_report", write_report)

    graph.add_edge(START, "classic_extract")
    graph.add_conditional_edges("classic_extract", choose_extractor)
    graph.add_edge("ai_extract", "check_vague")
    graph.add_edge("check_vague", "check_conflicts")
    graph.add_edge("check_conflicts", "review")
    graph.add_edge("review", "write_report")
    graph.add_edge("write_report", END)
    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[("reqlens.models", "Requirement")]
    )
    return graph.compile(checkpointer=InMemorySaver(serde=serde))
