import pytest
from pydantic import ValidationError

from reqlens.models import Requirement


def test_valid_requirement():
    req = Requirement(
        id="AEB-001", text="The system shall brake.", source="spec.pdf", page=3
    )
    assert req.id == "AEB-001"
    assert req.page == 3


def test_page_must_be_positive():
    with pytest.raises(ValidationError):
        Requirement(id="AEB-001", text="x", source="spec.pdf", page=0)


def test_id_must_not_be_empty():
    with pytest.raises(ValidationError):
        Requirement(id="", text="x", source="spec.pdf", page=1)
