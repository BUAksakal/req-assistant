from pathlib import Path
from typing import Annotated

import typer

from req_assistant.pdf_reader import extract_requirements

app = typer.Typer(help="Automotive requirements assistant.")


@app.callback()
def main() -> None:
    """Automotive requirements assistant."""


@app.command()
def parse(
    pdf: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
) -> None:
    """Extract requirements from a specification PDF."""
    requirements = extract_requirements(pdf)
    for req in requirements:
        typer.echo(f"{req.id}  (p. {req.page})  {req.text}")
    typer.echo(f"\n{len(requirements)} requirements found in {pdf.name}")
