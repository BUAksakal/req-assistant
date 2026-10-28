from reqlens.models import Requirement
from reqlens.workflow import pick_conflict_candidates


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
