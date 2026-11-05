"""Enable `python -m mediavault` (see §7 packaging rules)."""

from mediavault.cli.main import app

if __name__ == "__main__":
    app()
