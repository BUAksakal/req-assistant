"""GAIA-style benchmark: one specification, a known answer key, three levels.

Level 1 conflicts sit next to each other, level 2 conflicts are pages apart and
level 3 conflicts only show after a unit conversion. Decoys look like conflicts
but are not, so reporting everything as a conflict costs precision.
"""

import contextlib
import json
import re
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH_PDF = ROOT / "bench" / "acc_benchmark.pdf"
ANSWER_KEY = ROOT / "bench" / "acc_answer_key.json"
LEVELS = (1, 2, 3)


def reported_pairs(conflicts: dict[str, str], ids: list[str]) -> set[frozenset]:
    """Turn {requirement: claim} into pairs, using the other ID named in the claim."""
    pairs = set()
    for req_id, claim in conflicts.items():
        for other in re.findall(r"[A-Z]+-[A-Z]-\d{3}|[A-Z]+-\d{3}", claim):
            if other != req_id and other in ids:
                pairs.add(frozenset((req_id, other)))
    return pairs


def _ratio(hit: int, total: int) -> str:
    return f"{hit}/{total}"


def score(
    key: dict,
    extracted: list[str],
    vague: list[str],
    agent: dict[str, str],
    verified: dict[str, str],
) -> dict:
    """Compare one run with the answer key.

    agent holds the conflicts the LlamaIndex agent reported, verified the ones
    the supervisor kept. Scoring both shows what the supervisor adds.
    """
    ids = key["requirements"]
    truth = {frozenset(c["pair"]): c["level"] for c in key["conflicts"]}
    decoys = {frozenset(d["pair"]) for d in key["decoys"]}
    stages = {
        "agent": reported_pairs(agent, ids),
        "supervisor": reported_pairs(verified, ids),
    }

    result = {
        "extraction": _ratio(len(set(extracted) & set(ids)), len(ids)),
        "levels": {},
    }
    for level in LEVELS:
        pairs = [p for p, lv in truth.items() if lv == level]
        vague_ids = [v["id"] for v in key["vague"] if v["level"] == level]
        result["levels"][level] = {
            "conflicts_agent": _ratio(len(stages["agent"] & set(pairs)), len(pairs)),
            "conflicts_supervisor": _ratio(
                len(stages["supervisor"] & set(pairs)), len(pairs)
            ),
            "vague": _ratio(len(set(vague) & set(vague_ids)), len(vague_ids)),
        }
    for stage, pairs in stages.items():
        correct = len(pairs & truth.keys())
        result[f"precision_{stage}"] = _ratio(correct, len(pairs))
        result[f"recall_{stage}"] = _ratio(correct, len(truth))
        result[f"decoys_{stage}"] = _ratio(len(pairs & decoys), len(decoys))
    return result


def supervisor_rejects_decoys(key: dict, requirements: dict) -> str:
    """Hand every decoy to the supervisor as if the agent had reported it.

    The agent may never report a decoy, so this is the only way to see whether
    the supervisor still drops false alarms.
    """
    from functools import partial

    from reqlens.cache import fingerprint, lookup, store
    from reqlens.llm import call_with_fallback
    from reqlens.supervisor import VERIFY_PROMPT, Verdict, verify_conflict

    rejected = 0
    for decoy in key["decoys"]:
        first, second = (requirements[req_id] for req_id in decoy["pair"])
        claim = f"{second.id}: these requirements give different values."
        cache_key = (
            f"decoy:{fingerprint(VERIFY_PROMPT.template + first.text + second.text)}"
        )
        saved = lookup(cache_key)
        if saved is None:
            verdict = call_with_fallback(partial(verify_conflict, first, second, claim))
            saved = verdict.model_dump_json()
            store(cache_key, saved)
        rejected += not Verdict.model_validate_json(saved).keep
    return _ratio(rejected, len(key["decoys"]))


def run(pdf: Path = BENCH_PDF, fresh: bool = False) -> dict:
    """Run the workflow up to the engineer review and score it.

    With fresh=True the run uses an empty cache, so every LLM answer is asked
    again. That is how run-to-run variation can be measured.
    """
    from reqlens.workflow import build_workflow

    key = json.loads(ANSWER_KEY.read_text(encoding="utf-8"))
    pdf = Path(pdf).resolve()
    place = tempfile.TemporaryDirectory() if fresh else contextlib.nullcontext()
    with place as folder, contextlib.chdir(folder or Path.cwd()):
        workflow = build_workflow()
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        agent = {}
        start = time.perf_counter()
        for update in workflow.stream({"pdf": str(pdf)}, config, stream_mode="updates"):
            if "check_conflicts" in update:
                agent = update["check_conflicts"]["conflicts"]
        seconds = time.perf_counter() - start
        state = workflow.get_state(config).values
        by_id = {req.id: req for req in state["requirements"]}
        decoys_rejected = supervisor_rejects_decoys(key, by_id)

    result = score(
        key,
        [req.id for req in state["requirements"]],
        list(state["vague"]),
        agent,
        state["conflicts"],
    )
    result["decoys_rejected_by_supervisor"] = decoys_rejected
    result["seconds"] = round(seconds, 1)
    return result


def as_markdown(result: dict) -> str:
    rows = [
        "| Level | Conflicts found by the agent | Kept by the supervisor | Vague wording found |",
        "|---|:---:|:---:|:---:|",
    ]
    names = {1: "1: next to each other", 2: "2: pages apart", 3: "3: unit conversion"}
    for level, values in result["levels"].items():
        rows.append(
            f"| {names[int(level)]} | {values['conflicts_agent']} | "
            f"{values['conflicts_supervisor']} | {values['vague']} |"
        )
    rows += [
        "",
        f"- Extraction: {result['extraction']} requirements",
        (
            f"- Conflict precision: agent {result['precision_agent']}, "
            f"after supervisor {result['precision_supervisor']}"
        ),
        (
            f"- Decoys reported as conflicts: agent {result['decoys_agent']}, "
            f"after supervisor {result['decoys_supervisor']}"
        ),
        (
            "- Decoys handed to the supervisor as conflicts and rejected: "
            f"{result['decoys_rejected_by_supervisor']}"
        ),
        f"- Time until the engineer review: {result['seconds']} s",
    ]
    return "\n".join(rows)
