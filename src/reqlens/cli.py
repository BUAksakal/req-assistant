from pathlib import Path
from typing import Annotated

import typer

from reqlens.pdf_reader import extract_requirements

app = typer.Typer(help="ReqLens: requirements analysis for the automotive industry.")


@app.callback()
def main() -> None:
    """ReqLens: requirements analysis for the automotive industry."""


@app.command()
def parse(
    pdf: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    ai: Annotated[bool, typer.Option("--ai", help="Use the LLM extractor.")] = False,
) -> None:
    """Extract requirements from a specification PDF."""
    if ai:
        from reqlens.ai_parser import extract_requirements_ai

        requirements = extract_requirements_ai(pdf)
    else:
        requirements = extract_requirements(pdf)
    for req in requirements:
        typer.echo(f"{req.id}  (p. {req.page})  {req.text}")
    typer.echo(f"\n{len(requirements)} requirements found in {pdf.name}")


@app.command()
def analyze(
    pdf: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
) -> None:
    """Run the full workflow and let the engineer approve each finding."""
    from langgraph.types import Command

    from reqlens.workflow import build_workflow

    workflow = build_workflow()
    config = {"configurable": {"thread_id": pdf.name}}
    result = workflow.invoke({"pdf": str(pdf)}, config)

    findings = result["__interrupt__"][0].value
    approved = [f for f in findings if typer.confirm(f"\n{f}\nReal problem?")]

    result = workflow.invoke(Command(resume=approved), config)
    typer.echo("\n" + result["report"])
