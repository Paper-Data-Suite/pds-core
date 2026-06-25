"""Shared CLI parser types and lightweight context objects."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import NoReturn, TextIO

from pds_core.standards import StandardsLibrary


Handler = Callable[[argparse.Namespace, StandardsLibrary, TextIO, TextIO], int]


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        raise SystemExit(f"{self.prog}: error: {message}")


@dataclass(frozen=True, slots=True)
class StandardFilters:
    source: str | None = None
    subject: str | None = None
    course: str | None = None
    domain: str | None = None
    category_path_prefix: tuple[str, ...] = ()
    available_module: str | None = None
    active: bool | None = True
