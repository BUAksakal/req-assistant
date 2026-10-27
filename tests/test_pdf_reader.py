import json
from pathlib import Path

from reqlens.pdf_reader import extract_requirements

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "examples" / "aeb_lastenheft.pdf"
TRUTH = ROOT / "eval" / "extraction_truth.jsonl"


def load_truth() -> list[dict]:
    with TRUTH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def test_extracts_all_requirements_from_example_pdf():
    found = [req.model_dump() for req in extract_requirements(PDF)]
    assert found == load_truth()


def test_ignores_non_requirement_text():
    texts = [req.text for req in extract_requirements(PDF)]
    assert not any("Note:" in t or "Musterwerk" in t for t in texts)
