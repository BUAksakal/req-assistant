from reqlens.analysis_agent import Conflict, ConflictReport
from reqlens.models import Requirement
from reqlens.workflow import conflict_pairs, pick_conflict_candidates


def req(req_id: str, text: str) -> Requirement:
    return Requirement(id=req_id, text=text, source="spec.pdf", page=1)


def test_small_documents_check_every_numeric_requirement():
    numeric = [req("R1", "Warn within 5 s."), req("R2", "Brake at 10 km/h.")]

    assert pick_conflict_candidates(numeric, limit=12) == numeric


def test_budget_prefers_similar_requirements_with_the_same_unit():
    numeric = [
        req("R1", "The failure warning shall be displayed within 10 s."),
        req("R2", "The radar shall detect vehicles at 150 m."),
        req("R3", "The failure warning shall be displayed within 5 s."),
        req("R4", "The tyre pressure shall be at least 2 bar."),
    ]

    picked = {r.id for r in pick_conflict_candidates(numeric, limit=2)}

    assert picked == {"R1", "R3"}


def test_conflict_partners_are_matched_exactly():
    report = ConflictReport(
        conflicts=[
            Conflict(with_id="5.1.4", reason="real partner"),
            Conflict(with_id="5.1", reason="the requirement itself"),
            Conflict(with_id="9.9.9", reason="invented ID"),
        ]
    )

    pairs = conflict_pairs("5.1", report, {"5.1", "5.1.4"})

    assert pairs == [{"first": "5.1", "second": "5.1.4", "reason": "real partner"}]
