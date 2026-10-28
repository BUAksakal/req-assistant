import json
import re
from functools import partial
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from reqlens.ambiguity import find_vague_words
from reqlens.models import Requirement
from reqlens.pdf_reader import extract_requirements


class State(TypedDict, total=False):
    pdf: str
    requirements: list[Requirement]
    extraction: str
    vague: dict[str, list[str]]
    conflicts: dict[str, str]
    approved: list[str]
    report: str


def classic_extract(state: State) -> State:
    return {"requirements": extract_requirements(state["pdf"])}


def ai_extract(state: State) -> State:
    from reqlens.ai_parser import extract_requirements_ai
    from reqlens.cache import fingerprint, lookup, store
    from reqlens.llm import call_with_fallback

    pdf = Path(state["pdf"])
    key = f"extract:{fingerprint(pdf.read_bytes())}"
    saved = lookup(key)
    if saved is None:
        found = call_with_fallback(partial(extract_requirements_ai, pdf))
        saved = json.dumps([req.model_dump() for req in found])
        store(key, saved)
    requirements = [
        Requirement(**{**item, "source": pdf.name}) for item in json.loads(saved)
    ]
    return {"requirements": requirements}


def supervise_extraction(state: State) -> State:
    """Supervisor decision 1: did the classic extractor miss requirements?"""
    from reqlens.cache import fingerprint, lookup, store
    from reqlens.llm import LLMUnavailableError, call_with_fallback
    from reqlens.pdf_reader import read_pages
    from reqlens.supervisor import (
        ExtractionDecision,
        decide_extraction,
        unextracted_shall_passages,
    )

    progress = get_stream_writer()
    found = state["requirements"]
    if not found:
        progress({"supervisor": "no requirements found, switching to the LLM"})
        return {"extraction": "use_llm"}
    missed = unextracted_shall_passages(read_pages(state["pdf"]), found)
    if not missed:
        progress({"supervisor": "every 'shall' sentence was extracted, accept"})
        return {"extraction": "accept"}

    key = f"supervise:{fingerprint(json.dumps([len(found), missed]))}"
    saved = lookup(key)
    if saved is None:
        try:
            decision = call_with_fallback(
                partial(decide_extraction, len(found), missed)
            )
        except LLMUnavailableError:
            action = "use_llm" if len(missed) > len(found) else "accept"
            progress({"supervisor": f"LLM unavailable, rule fallback: {action}"})
            return {"extraction": action}
        saved = decision.model_dump_json()
        store(key, saved)
    decision = ExtractionDecision.model_validate_json(saved)
    progress(
        {
            "supervisor": f"{len(missed)} unextracted 'shall' passage(s), "
            f"{decision.action}: {decision.reason}"
        }
    )
    return {"extraction": decision.action}


def choose_extractor(state: State) -> str:
    return "ai_extract" if state["extraction"] == "use_llm" else "check_vague"


def check_vague(state: State) -> State:
    vague = {}
    for req in state["requirements"]:
        words = find_vague_words(req.text)
        if words:
            vague[req.id] = words
    return {"vague": vague}


def check_conflicts(state: State) -> State:
    from reqlens.analysis_agent import make_conflict_checker
    from reqlens.cache import fingerprint, lookup, store
    from reqlens.llm import call_with_fallback

    progress = get_stream_writer()
    requirements = state["requirements"]
    document = fingerprint("\n".join(f"{r.id}|{r.text}" for r in requirements))
    check = None
    conflicts = {}
    for req in requirements:
        if not re.search(r"\d", req.text):
            continue
        key = f"conflict:{document}:{req.id}"
        answer = lookup(key)
        if answer is None:
            if check is None:
                check = make_conflict_checker(
                    requirements,
                    on_search=lambda q, hits: progress({"search": q, "hits": hits}),
                )
            progress({"checking": req.id})
            answer = call_with_fallback(partial(check, req.id))
            store(key, answer)
        else:
            progress({"cached": req.id})
        if "no conflict" not in answer.lower():
            conflicts[req.id] = answer
    return {"conflicts": conflicts}


def verify_findings(state: State) -> State:
    """Supervisor decision 2: keep only the conflicts that hold up a second look."""
    from reqlens.cache import fingerprint, lookup, store
    from reqlens.llm import LLMUnavailableError, call_with_fallback
    from reqlens.supervisor import Verdict, verify_conflict

    progress = get_stream_writer()
    by_id = {req.id: req for req in state["requirements"]}
    verified = {}
    for req_id, claim in state["conflicts"].items():
        others = [other for other in by_id if other != req_id and other in claim]
        if not others:
            verified[req_id] = claim
            continue
        first, second = by_id[req_id], by_id[others[0]]
        key = f"verify:{fingerprint(f'{first.text}|{second.text}|{claim}')}"
        saved = lookup(key)
        if saved is None:
            try:
                verdict = call_with_fallback(
                    partial(verify_conflict, first, second, claim)
                )
            except LLMUnavailableError:
                progress({"supervisor": "LLM unavailable, keeping every conflict"})
                return {"conflicts": state["conflicts"]}
            saved = verdict.model_dump_json()
            store(key, saved)
        verdict = Verdict.model_validate_json(saved)
        label = "confirmed" if verdict.confirmed else "rejected"
        progress({"supervisor": f"{label} {req_id} ↔ {second.id}: {verdict.reason}"})
        if verdict.confirmed:
            verified[req_id] = claim
    return {"conflicts": verified}


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
    graph.add_node("supervise_extraction", supervise_extraction)
    graph.add_node("ai_extract", ai_extract)
    graph.add_node("check_vague", check_vague)
    graph.add_node("check_conflicts", check_conflicts)
    graph.add_node("verify_findings", verify_findings)
    graph.add_node("review", review)
    graph.add_node("write_report", write_report)

    graph.add_edge(START, "classic_extract")
    graph.add_edge("classic_extract", "supervise_extraction")
    graph.add_conditional_edges("supervise_extraction", choose_extractor)
    graph.add_edge("ai_extract", "check_vague")
    graph.add_edge("check_vague", "check_conflicts")
    graph.add_edge("check_conflicts", "verify_findings")
    graph.add_edge("verify_findings", "review")
    graph.add_edge("review", "write_report")
    graph.add_edge("write_report", END)
    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[("reqlens.models", "Requirement")]
    )
    return graph.compile(checkpointer=InMemorySaver(serde=serde))
