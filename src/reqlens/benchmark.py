"""GAIA-style benchmark: specifications with a known answer key, three levels.

There are two sets. "dev" (ACC) was used to tune the prompts, so its scores are
optimistic. "test" (EPB) was written afterwards and is only reported, never
used to change prompts or code.

Level 1 conflicts sit next to each other, level 2 conflicts are pages apart and
level 3 conflicts only show after a unit conversion. Decoys look like conflicts
but are not, so reporting everything as a conflict costs precision.
"""

import contextlib
import json
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "bench"
SETS = {"dev": "acc", "test": "epb"}
LEVELS = (1, 2, 3)


def answer_key(name: str) -> dict:
    return json.loads((BENCH / f"{SETS[name]}_answer_key.json").read_text("utf-8"))


def reported_pairs(conflicts: list[dict[str, str]], ids: list[str]) -> set[frozenset]:
    """The requirement pairs a run reported, ignoring unknown IDs."""
    return {
        frozenset((c["first"], c["second"]))
        for c in conflicts
        if c["first"] in ids and c["second"] in ids
    }


def _ratio(hit: int, total: int) -> str:
    return f"{hit}/{total}"


def score(
    key: dict,
    extracted: list[str],
    vague: list[str],
    agent: list[dict[str, str]],
    verified: list[dict[str, str]],
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


def run(name: str = "dev", fresh: bool = False) -> dict:
    """Run the workflow up to the engineer review and score it.

    With fresh=True the run uses an empty cache, so every LLM answer is asked
    again. That is how run-to-run variation can be measured.
    """
    from reqlens.workflow import build_workflow

    key = answer_key(name)
    pdf = BENCH / f"{SETS[name]}_benchmark.pdf"
    place = tempfile.TemporaryDirectory() if fresh else contextlib.nullcontext()
    with place as folder, contextlib.chdir(folder or Path.cwd()):
        workflow = build_workflow()
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        agent = []
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
    result["set"] = name
    return result


def retrieval_hits(name: str, ks: tuple[int, ...] = (1, 3, 5)) -> dict:
    """How often the conflicting partner is among the top k search results.

    The conflict agent only sees what find_related returns, so a partner that
    is not retrieved cannot be found. The query is the requirement text, close
    to the queries the agent writes. Only embeddings are used, no LLM answers.
    """
    from reqlens.models import Requirement
    from reqlens.requirement_index import build_index, search

    key = answer_key(name)
    requirements = [
        Requirement(id=rid, text=text, source=name, page=1)
        for rid, text in key["texts"].items()
    ]
    index = build_index(requirements)
    hits = {lv: dict.fromkeys(ks, 0) for lv in LEVELS}
    totals = dict.fromkeys(LEVELS, 0)
    for conflict in key["conflicts"]:
        for query_id, partner in (conflict["pair"], conflict["pair"][::-1]):
            found = [
                rid
                for rid, _ in search(index, key["texts"][query_id], top_k=max(ks) + 1)
                if rid != query_id
            ]
            totals[conflict["level"]] += 1
            for k in ks:
                hits[conflict["level"]][k] += partner in found[:k]
    result = {
        "levels": {
            lv: {k: _ratio(hits[lv][k], totals[lv]) for k in ks} for lv in LEVELS
        },
        "all": {
            k: _ratio(sum(hits[lv][k] for lv in LEVELS), sum(totals.values()))
            for k in ks
        },
    }
    return result


def retrieval_markdown(result: dict) -> str:
    ks = list(result["all"])
    rows = [
        "| Level | " + " | ".join(f"hit@{k}" for k in ks) + " |",
        "|---|" + ":---:|" * len(ks),
    ]
    names = {1: "1: next to each other", 2: "2: pages apart", 3: "3: unit conversion"}
    for lv, values in result["levels"].items():
        rows.append(f"| {names[lv]} | " + " | ".join(values[k] for k in ks) + " |")
    rows.append(
        "| **all** | " + " | ".join(f"**{result['all'][k]}**" for k in ks) + " |"
    )
    return "\n".join(rows)


def save(result: dict) -> Path:
    """Keep every run, so a summary can be checked and survives a quota stop."""
    folder = BENCH / "results" / result["set"]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"run-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return path


def _hits(ratio: str) -> tuple[int, int]:
    hit, total = ratio.split("/")
    return int(hit), int(total)


def summarize(results: list[dict]) -> str:
    """Mean and worst result over several runs, as a markdown table."""
    metrics = [
        ("Requirements extracted", lambda r: r["extraction"], max),
        ("Conflicts found by the agent", lambda r: r["recall_agent"], max),
        ("Conflicts kept after the supervisor", lambda r: r["recall_supervisor"], max),
        *(
            (
                f"  level {lv}",
                lambda r, lv=lv: r["levels"][lv]["conflicts_supervisor"],
                max,
            )
            for lv in LEVELS
        ),
        ("Precision after the supervisor", lambda r: r["precision_supervisor"], max),
        ("Decoys reported as conflicts", lambda r: r["decoys_supervisor"], min),
        (
            "Decoys rejected when handed to the supervisor",
            lambda r: r["decoys_rejected_by_supervisor"],
            max,
        ),
        ("Vague wording found", lambda r: _sum_vague(r), max),
    ]
    # Results read back from JSON have "1" instead of 1 as level keys.
    results = [
        {**r, "levels": {int(k): v for k, v in r["levels"].items()}} for r in results
    ]
    rows = [
        f"| Metric | Mean over {len(results)} runs | Worst run |",
        "|---|:---:|:---:|",
    ]
    for label, get, better in metrics:
        pairs = [_hits(get(r)) for r in results]
        pairs = [(hit, total) for hit, total in pairs if total]
        if not pairs:
            rows.append(f"| {label} | n/a | n/a |")
            continue
        total = pairs[0][1]
        mean = sum(hit for hit, _ in pairs) / len(pairs)
        worst = (
            min(pairs, key=lambda p: p[0] / p[1])
            if better is max
            else max(pairs, key=lambda p: p[0] / p[1])
        )
        rows.append(f"| {label} | {mean:.1f}/{total} | {worst[0]}/{worst[1]} |")
    seconds = [r["seconds"] for r in results]
    rows.append(
        f"| Seconds until review | {sum(seconds) / len(seconds):.0f} | {max(seconds):.0f} |"
    )
    return "\n".join(rows)


def _sum_vague(result: dict) -> str:
    hits = [_hits(v["vague"]) for v in result["levels"].values()]
    return f"{sum(h for h, _ in hits)}/{sum(t for _, t in hits)}"


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
