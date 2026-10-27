import re
from pathlib import Path

import pymupdf

from req_assistant.models import Requirement

REQ_ID = re.compile(r"^AEB-\d{3}\b")
SECTION_HEADING = re.compile(r"^\d+ [A-Z]")
NOTE = "Note:"


def read_pages(path: Path) -> list[str]:
    """Return the text of each page in a PDF, in order."""
    with pymupdf.open(path) as doc:
        return [page.get_text() for page in doc]


def _to_requirement(
    req_id: str, lines: list[str], source: str, page: int
) -> Requirement:
    return Requirement(id=req_id, text=" ".join(lines), source=source, page=page)


def extract_requirements(path: Path) -> list[Requirement]:
    """Find requirements by their ID line and collect the text below it."""
    requirements = []
    source = Path(path).name

    for page_number, page_text in enumerate(read_pages(path), start=1):
        current_id = None
        text_lines = []

        for line in page_text.splitlines():
            line = line.strip()
            id_match = REQ_ID.match(line)
            is_boundary = (
                id_match or SECTION_HEADING.match(line) or line.startswith(NOTE)
            )

            if is_boundary:
                if current_id:
                    requirements.append(
                        _to_requirement(current_id, text_lines, source, page_number)
                    )
                current_id = id_match.group() if id_match else None
                text_lines = []
            elif current_id:
                text_lines.append(line)

        if current_id:
            requirements.append(
                _to_requirement(current_id, text_lines, source, page_number)
            )

    return requirements
