import json
import re
from functools import partial
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from reqlens.ambiguity import find_vague_words
from reqlens.analysis_agent import ConflictReport
from reqlens.models import Requirement
from reqlens.pdf_reader import extract_requirements

MAX_CONFLICT_CHECKS = 12
UNIT = re.compile(r"\d\s*(km/h|m/s²|m/s2|m/s|ms|s|m|%)(?![\w/])")
WORD = re.compile(r"[a-z]{4,}")


class State(TypedDict, total=False):
    pdf: str
    requirements: list[Requirement]
    extraction: str
    vague: dict[str, list[str]]
    conflicts: list[dict[str, str]]
    approved: list[str]
    report: str


def classic_extract(state: State) -> State:
    return {"requirements": extract_requirements(state["pdf"])}


def ai_extract(state: State) -> State:
    from reqlens.ai_parser import extract_with_cache

    progress = get_stream_writer()
    requirements = extract_with_cache(
        state["pdf"],
        on_chunk=lambda first, last: progress(
            {"note": f"LLM reads pages {first}-{last}"}
        ),
    )
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


def pick_conflict_candidates(
    numeric: list[Requirement], limit: int = MAX_CONFLICT_CHECKS
) -> list[Requirement]:
    """Pick the requirements most likely to contradict another one.

    A requirement ranks high when another requirement uses the same unit and
    shares many words with it, for example two failure warning times in seconds.
    """
    if len(numeric) <= limit:
        return numeric
    units = {req.id: set(UNIT.findall(req.text)) for req in numeric}
    words = {req.id: set(WORD.findall(req.text.lower())) for req in numeric}

    def similarity(req: Requirement) -> float:
        best = 0.0
        for other in numeric:
            if other.id == req.id or not units[req.id] & units[other.id]:
                continue
            shared = words[req.id] & words[other.id]
            best = max(best, len(shared) / len(words[req.id] | words[other.id]))
        return best

    return sorted(numeric, key=similarity, reverse=True)[:limit]


def conflict_pairs(
    req_id: str, report: ConflictReport, known: set[str]
) -> list[dict[str, str]]:
    """Keep the reported conflicts whose partner is a real, different requirement.

    IDs are matched exactly, so 5.1 is never mistaken for 5.1.4.
    """
    return [
        {"first": req_id, "second": c.with_id.strip(), "reason": c.reason}
        for c in report.conflicts
        if c.with_id.strip() in known and c.with_id.strip() != req_id
    ]


def check_conflicts(state: State) -> State:
    from reqlens.analysis_agent import make_conflict_checker
    from reqlens.cache import fingerprint, lookup, store
    from reqlens.llm import call_with_fallback

    progress = get_stream_writer()
    requirements = state["requirements"]
    document = fingerprint("\n".join(f"{r.id}|{r.text}" for r in requirements))
    numeric = [req for req in requirements if re.search(r"\d", req.text)]
    candidates = pick_conflict_candidates(numeric)
    if len(candidates) < len(numeric):
        progress(
            {
                "note": f"budget: checking the {len(candidates)} most similar of "
                f"{len(numeric)} requirements with values"
            }
        )
    check = None
    conflicts, seen = [], set()
    known = {req.id for req in requirements}
    for req in candidates:
        key = f"conflict-report:{document}:{req.id}"
        saved = lookup(key)
        if saved is None:
            if check is None:
                check = make_conflict_checker(
                    requirements,
                    on_search=lambda q, hits: progress({"search": q, "hits": hits}),
                )
            progress({"checking": req.id})
            saved = call_with_fallback(partial(check, req.id)).model_dump_json()
            store(key, saved)
        else:
            progress({"cached": req.id})
        for conflict in conflict_pairs(
            req.id, ConflictReport.model_validate_json(saved), known
        ):
            pair = frozenset((conflict["first"], conflict["second"]))
            if pair not in seen:
                seen.add(pair)
                conflicts.append(conflict)
    return {"conflicts": conflicts}


def verify_findings(state: State) -> State:
    """Supervisor decision 2: keep only the conflicts that hold up a second look."""
    from reqlens.cache import fingerprint, lookup, store
    from reqlens.llm import LLMUnavailableError, call_with_fallback
    from reqlens.supervisor import VERIFY_PROMPT, Verdict, verify_conflict

    progress = get_stream_writer()
    by_id = {req.id: req for req in state["requirements"]}
    verified = []
    for conflict in state["conflicts"]:
        first, second = by_id[conflict["first"]], by_id[conflict["second"]]
        claim = conflict["reason"]
        # The prompt is part of the key: a changed prompt must not reuse old verdicts.
        pair = f"{VERIFY_PROMPT.template}|{first.text}|{second.text}|{claim}"
        key = f"verify:{fingerprint(pair)}"
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
        label = {
            "real": "confirmed",
            "false_alarm": "rejected",
            "unsure": "unsure, kept",
        }
        progress(
            {
                "supervisor": f"{label[verdict.verdict]} {first.id} ↔ {second.id}: "
                f"{verdict.reason}"
            }
        )
        if verdict.keep:
            verified.append(conflict)
    return {"conflicts": verified}


def review(state: State) -> State:
    findings = [f"{rid}: vague words {w}" for rid, w in state["vague"].items()]
    findings += [
        f"{c['first']}: {c['second']}: {c['reason']}" for c in state["conflicts"]
    ]
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
