"""Phase 1 smoke tests: --version, --help, python -m parity (FR-204/205)."""

from typer.testing import CliRunner

from mediavault import __version__
from mediavault.cli.main import app

runner = CliRunner()


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
    assert "mediavault-cli" in result.stdout


def test_help_flag():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "mediavault-cli" in result.stdout
    # Typer renders the app help docstring
    assert "Scan" in result.stdout or "library" in result.stdout
