"""Compatibility helpers for split CLI tests.

CLI test coverage lives under tests/cli/.
"""

from tests.cli.conftest import make_cli_library, run_cli

__all__ = ["make_cli_library", "run_cli"]
