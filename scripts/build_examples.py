import json
from pathlib import Path

import yaml
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "examples" / "aeb_requirements.yaml"
OUTPUT = ROOT / "examples" / "aeb_lastenheft.pdf"
EVAL_DIR = ROOT / "eval"

BRAND = colors.HexColor("#003366")
STYLES = getSampleStyleSheet()


class SpecDocTemplate(SimpleDocTemplate):
    """Remembers the page on which each requirement heading is drawn."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.req_pages = {}

    def afterFlowable(self, flowable):
        req_id = getattr(flowable, "req_id", None)
        if req_id:
            self.req_pages[req_id] = self.page


def load_spec(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def cover_page(info: dict) -> list:
    rows = [
        ["Document ID", info["doc_id"]],
        ["Version", info["version"]],
        ["Date", info["date"]],
        ["Status", info["status"]],
        ["Confidentiality", info["confidentiality"]],
    ]
    table = Table(rows, colWidths=[5 * cm, 9 * cm])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
            ]
        )
    )
    return [
        Spacer(1, 4 * cm),
        Paragraph(info["company"], STYLES["Heading1"]),
        Spacer(1, 1 * cm),
        Paragraph(info["title"], STYLES["Title"]),
        Spacer(1, 2 * cm),
        table,
        PageBreak(),
    ]


def revision_table(revisions: list) -> list:
    rows = [["Version", "Date", "Author", "Change"]]
    rows += [[r["version"], r["date"], r["author"], r["change"]] for r in revisions]
    table = Table(rows, colWidths=[2.5 * cm, 3 * cm, 4 * cm, 6.5 * cm])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), BRAND),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ]
        )
    )
    return [Paragraph("Revision History", STYLES["Heading2"]), table, PageBreak()]


def section(sec: dict) -> list:
    parts = [Paragraph(f"{sec['number']} {sec['title']}", STYLES["Heading1"])]
    if "text" in sec:
        parts.append(Paragraph(sec["text"], STYLES["Normal"]))
    for req in sec.get("requirements", []):
        heading = Paragraph(f"{req['id']} {req['title']}", STYLES["Heading3"])
        heading.req_id = req["id"]
        parts.append(heading)
        parts.append(Paragraph(req["text"], STYLES["Normal"]))
    if "note" in sec:
        parts.append(Spacer(1, 6))
        parts.append(Paragraph(f"<i>Note: {sec['note']}</i>", STYLES["Normal"]))
    parts.append(Spacer(1, 12))
    return parts


def header_footer(info: dict):
    def draw(canvas, doc):
        width, height = A4
        canvas.saveState()
        canvas.setFillColor(BRAND)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(2 * cm, height - 1.5 * cm, info["company"])
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(width - 2 * cm, height - 1.5 * cm, info["doc_id"])
        canvas.setFillColor(colors.grey)
        canvas.drawString(2 * cm, 1.5 * cm, info["confidentiality"])
        canvas.drawRightString(width - 2 * cm, 1.5 * cm, f"Page {doc.page}")
        canvas.restoreState()

    return draw


def build_pdf(spec: dict, output: Path) -> dict:
    info = spec["document"]
    story = cover_page(info) + revision_table(info["revisions"])
    for sec in spec["sections"]:
        story += section(sec)

    doc = SpecDocTemplate(
        str(output), pagesize=A4, topMargin=2.5 * cm, bottomMargin=2.5 * cm
    )
    doc.build(story, onFirstPage=lambda c, d: None, onLaterPages=header_footer(info))
    return doc.req_pages


def write_jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def write_answer_keys(spec: dict, pages: dict) -> None:
    extraction, errors = [], []
    for sec in spec["sections"]:
        for req in sec.get("requirements", []):
            extraction.append(
                {
                    "id": req["id"],
                    "text": req["text"],
                    "source": OUTPUT.name,
                    "page": pages[req["id"]],
                }
            )
            if "error" in req:
                errors.append(
                    {
                        "id": req["id"],
                        "error": req["error"],
                        "conflicts_with": req.get("conflicts_with"),
                    }
                )
    write_jsonl(EVAL_DIR / "extraction_truth.jsonl", extraction)
    write_jsonl(EVAL_DIR / "ground_truth.jsonl", errors)


if __name__ == "__main__":
    spec = load_spec(SOURCE)
    pages = build_pdf(spec, OUTPUT)
    write_answer_keys(spec, pages)
    print(f"Wrote {OUTPUT} and answer keys in {EVAL_DIR}")
