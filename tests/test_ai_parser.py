from reqlens import ai_parser
from reqlens.ai_parser import (
    FoundRequirement,
    extract_with_cache,
    normalize_id,
    page_chunks,
)


def test_chunks_overlap_by_one_page_and_cover_everything():
    pages = [f"page {n}" for n in range(1, 20)]

    chunks = page_chunks(pages, size=8)

    assert [first for first, _ in chunks] == [1, 8, 15]
    assert chunks[1][1][0] == "page 8"
    assert chunks[-1][1][-1] == "page 19"


def test_ids_written_differently_become_one():
    assert normalize_id("5.5.2.") == normalize_id(" 5.5.2 ") == "5.5.2"
    assert normalize_id("Annex  3 3.1.") == "Annex 3 3.1"


def test_small_documents_are_one_chunk():
    assert page_chunks(["only page"], size=8) == [(1, ["only page"])]


def test_overlapping_chunks_keep_the_longer_text(tmp_path, monkeypatch):
    pdf = tmp_path / "spec.pdf"
    pdf.write_bytes(b"pdf")
    monkeypatch.setattr(
        ai_parser, "read_pages", lambda path: [f"p{n}" for n in range(9)]
    )
    monkeypatch.setattr(ai_parser, "call_with_fallback", lambda fn: fn("fake"))
    answers = {
        1: [FoundRequirement(id="5.1", text="The system shall", page=8)],
        8: [FoundRequirement(id="5.1", text="The system shall brake.", page=8)],
    }
    calls = []

    def fake_chunk(first, pages, model):
        calls.append(first)
        return answers[first]

    monkeypatch.setattr(ai_parser, "extract_chunk", fake_chunk)

    found = extract_with_cache(pdf, db=tmp_path / "test.db")
    extract_with_cache(pdf, db=tmp_path / "test.db")

    assert [(r.id, r.text) for r in found] == [("5.1", "The system shall brake.")]
    assert calls == [1, 8]
