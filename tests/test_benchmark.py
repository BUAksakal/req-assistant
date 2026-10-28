import json

from reqlens.benchmark import ANSWER_KEY, reported_pairs, score

KEY = json.loads(ANSWER_KEY.read_text(encoding="utf-8"))


def test_pairs_come_from_the_other_id_in_the_claim():
    conflicts = {
        "ACC-R-020": "ACC-R-041: 2 s versus 4 s",
        "ACC-R-041": "Conflicts with ACC-R-020.",
    }

    assert reported_pairs(conflicts, KEY["requirements"]) == {
        frozenset(("ACC-R-020", "ACC-R-041"))
    }


def test_supervisor_dropping_a_decoy_raises_precision():
    agent = {
        "ACC-R-010": "ACC-R-011: 160 km/h versus 180 km/h",
        "ACC-R-014": "ACC-R-033: 5 km/h versus 1 km/h steps",
    }
    verified = {"ACC-R-010": agent["ACC-R-010"]}

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
