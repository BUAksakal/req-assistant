from pathlib import Path

from reqlens.pdf_reader import extract_requirements, read_pages
from reqlens.supervisor import unextracted_shall_passages

PDF = Path(__file__).resolve().parent.parent / "examples" / "aeb_lastenheft.pdf"


def test_only_the_supplier_instruction_is_left_unextracted():
    passages = unextracted_shall_passages(read_pages(PDF), extract_requirements(PDF))

    assert len(passages) == 1
    assert "The supplier shall confirm each requirement" in passages[0]


def test_nothing_is_extracted_means_every_shall_is_missed():
    passages = unextracted_shall_passages(read_pages(PDF), [])

    assert len(passages) > 18
