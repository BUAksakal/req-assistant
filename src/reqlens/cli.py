from pathlib import Path
from typing import Annotated

import typer

from reqlens.pdf_reader import extract_requirements
from reqlens.storage import connect, save_run

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
        from reqlens.ai_parser import DocumentTooLargeError, extract_with_cache
        from reqlens.llm import LLMUnavailableError

        try:
            requirements = extract_with_cache(pdf)
        except DocumentTooLargeError as error:
            typer.echo(f"\n{error}")
            raise typer.Exit(1)
        except LLMUnavailableError as error:
            typer.echo(
                f"\n{error} Finished pages are cached and will not be asked again."
            )
            raise typer.Exit(1)
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

    from reqlens.llm import LLMUnavailableError
    from reqlens.workflow import build_workflow

    workflow = build_workflow()
    config = {"configurable": {"thread_id": pdf.name}}
    try:
        result = workflow.invoke({"pdf": str(pdf)}, config)
    except LLMUnavailableError as error:
        typer.echo(f"\n{error}")
        raise typer.Exit(1)

    findings = result["__interrupt__"][0].value
    approved = [f for f in findings if typer.confirm(f"\n{f}\nReal problem?")]

    result = workflow.invoke(Command(resume=approved), config)
    typer.echo("\n" + result["report"])

    run_id = save_run(
        connect(), pdf.name, len(result["requirements"]), findings, approved
    )
    typer.echo(f"Saved as run #{run_id} in reqlens.db")


@app.command()
def bench(
    name: Annotated[
        str, typer.Option("--set", help="dev (used for tuning) or test (held out).")
    ] = "dev",
    runs: Annotated[int, typer.Option(help="Repeat with an empty cache.")] = 1,
    fresh: Annotated[
        bool, typer.Option("--fresh", help="Ask every LLM answer again.")
    ] = False,
) -> None:
    """Score ReqLens on a benchmark specification with its answer key."""
    from reqlens.benchmark import SETS, as_markdown, run, save, summarize
    from reqlens.llm import LLMUnavailableError

    if name not in SETS:
        raise typer.BadParameter(f"--set must be one of {', '.join(SETS)}")
    results = []
    for i in range(1, runs + 1):
        try:
            # Repeated runs only make sense with an empty cache.
            result = run(name, fresh=fresh or runs > 1)
        except LLMUnavailableError as error:
            typer.echo(f"\nRun {i} stopped: {error}")
            break
        results.append(result)
        typer.echo(f"\nRun {i}/{runs} saved as {save(result).name}")
        typer.echo(as_markdown(result))
    if len(results) > 1:
        typer.echo("\n" + summarize(results))
    if not results:
        raise typer.Exit(1)


@app.command()
def history(
    db: Annotated[Path, typer.Option(help="Database file.")] = Path("reqlens.db"),
) -> None:
    """Show past analyses and how many findings engineers approved."""
    from reqlens.storage import approval_rate, connect, list_runs

    conn = connect(db)
    for run_id, created, pdf_name, reqs, total, approved in list_runs(conn):
        typer.echo(
            f"#{run_id}  {created}  {pdf_name}  {reqs} requirements  "
            f"{approved}/{total} findings approved"
        )
    typer.echo(f"\nOverall approval rate: {approval_rate(conn):.0%}")
