from pathlib import Path

from typer.testing import CliRunner

from reqlens.cli import app

PDF = Path(__file__).resolve().parent.parent / "examples" / "aeb_lastenheft.pdf"
runner = CliRunner()


def test_parse_lists_requirements():
    result = runner.invoke(app, ["parse", str(PDF)])
    assert result.exit_code == 0
    assert "AEB-001" in result.output
    assert "18 requirements found" in result.output


def test_parse_rejects_missing_file():
    result = runner.invoke(app, ["parse", "missing.pdf"])
    assert result.exit_code != 0
