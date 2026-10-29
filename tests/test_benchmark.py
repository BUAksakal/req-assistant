from reqlens import requirement_index
from reqlens.benchmark import (
    answer_key,
    reported_pairs,
    retrieval_hits,
    score,
    summarize,
)

KEY = answer_key("dev")


def test_both_directions_are_one_pair_and_unknown_ids_are_ignored():
    conflicts = [
        {"first": "ACC-R-020", "second": "ACC-R-041", "reason": "2 s versus 4 s"},
        {"first": "ACC-R-041", "second": "ACC-R-020", "reason": "same pair"},
        {"first": "ACC-R-020", "second": "ACC-R-999", "reason": "invented ID"},
    ]

    assert reported_pairs(conflicts, KEY["requirements"]) == {
        frozenset(("ACC-R-020", "ACC-R-041"))
    }


def test_supervisor_dropping_a_decoy_raises_precision():
    agent = [
        {"first": "ACC-R-010", "second": "ACC-R-011", "reason": "160 vs 180 km/h"},
        {"first": "ACC-R-014", "second": "ACC-R-033", "reason": "5 vs 1 km/h steps"},
    ]
    verified = agent[:1]

    result = score(KEY, KEY["requirements"], ["ACC-R-015"], agent, verified)

    assert result["precision_agent"] == "1/2"
    assert result["precision_supervisor"] == "1/1"
    assert result["decoys_agent"] == "1/2"
    assert result["decoys_supervisor"] == "0/2"
    assert result["levels"][1]["conflicts_supervisor"] == "1/2"
    assert result["levels"][1]["vague"] == "1/2"
    assert result["extraction"] == "25/25"


def test_answer_key_has_two_conflicts_per_level():
    levels = [c["level"] for c in KEY["conflicts"]]

    assert sorted(levels) == [1, 1, 2, 2, 3, 3]


def test_both_sets_have_two_conflicts_per_level_and_two_decoys():
    for name in ("dev", "test"):
        key = answer_key(name)
        assert sorted(c["level"] for c in key["conflicts"]) == [1, 1, 2, 2, 3, 3]
        assert len(key["decoys"]) == 2


def test_summary_shows_mean_and_worst_run():
    def fake(found: int, decoys: int) -> dict:
        result = score(KEY, KEY["requirements"], [], [], [])
        result.update(
            recall_supervisor=f"{found}/6",
            decoys_supervisor=f"{decoys}/2",
            decoys_rejected_by_supervisor="2/2",
            seconds=10.0,
        )
        return result

    table = summarize([fake(5, 0), fake(3, 1)])

    assert "| Conflicts kept after the supervisor | 4.0/6 | 3/6 |" in table
    assert "| Decoys reported as conflicts | 0.5/2 | 1/2 |" in table


def test_hit_at_k_counts_the_partner_and_skips_the_query_itself(monkeypatch):
    key = answer_key("test")
    partner = {}
    for c in key["conflicts"]:
        a, b = c["pair"]
        partner[a], partner[b] = (b, c["level"]), (a, c["level"])
    text_to_id = {text: rid for rid, text in key["texts"].items()}

    def fake_search(index, query, top_k):
        # The query itself comes first. Level 1 partners come second, the
        # others are not retrieved at all.
        rid = text_to_id[query]
        other, level = partner[rid]
        ranked = [rid] + ([other] if level == 1 else [])
        return [(r, 1.0) for r in ranked][:top_k]

    monkeypatch.setattr(requirement_index, "build_index", lambda reqs: None)
    monkeypatch.setattr(requirement_index, "search", fake_search)

    result = retrieval_hits("test")

    assert result["levels"][1][1] == "4/4"
    assert result["levels"][2][5] == "0/4"
    assert result["all"][1] == "4/12"
