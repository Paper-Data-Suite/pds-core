"""Shared standalone adapters for Core #242; no independent mutation authority."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO
from uuid import uuid4

from pds_core.standards import StandardsLibrary
from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    SharedTeacherMenuResult,
    TeacherContextHint,
    TeacherDurability,
    TeacherMenuExit,
)
from pds_core.teacher_menus import run_workspace_classroom_menu


def run_classroom_entry(
    workspace: str | None,
    *, stdin: TextIO, stdout: TextIO, stderr: TextIO, interactive: bool,
) -> SharedTeacherMenuResult:
    """Invoke the public callable with only an ephemeral standalone hint."""
    token = uuid4().hex
    receipt = run_workspace_classroom_menu(
        SharedTeacherMenuRequest(
            caller_application="PDS Core",
            return_token=token,
            context=TeacherContextHint(
                workspace_root=None if workspace is None else Path(workspace)
            ),
        ),
        read_line=stdin.readline,
        output=stdout,
        error_output=stderr,
        interactive=interactive,
    )
    # This standalone caller has no active student or work revision to restore.
    # Never resume a cached selection; the next action resolves fresh context.
    if receipt.return_token != token:
        raise RuntimeError("Classroom menu returned an invalid session receipt.")
    return receipt


def _interactive(stdin: TextIO, stdout: TextIO) -> bool:
    try:
        return stdin.isatty() and stdout.isatty()
    except (OSError, ValueError):
        return False


def handle_classroom_menu(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Explicit interactive CLI route; refuse redirected sessions before reads."""
    stdin = sys.stdin
    receipt = run_classroom_entry(
        args.workspace,
        stdin=stdin, stdout=stdout, stderr=stderr,
        interactive=_interactive(stdin, stdout),
    )
    if receipt.exit is TeacherMenuExit.UNAVAILABLE:
        print(receipt.message, file=stderr)
        return 5
    if receipt.durability in (TeacherDurability.PARTIAL, TeacherDurability.INDETERMINATE):
        print(receipt.message, file=stderr)
        return 7
    if receipt.exit is TeacherMenuExit.FAILED:
        print(receipt.message, file=stderr)
        return 1
    print(receipt.message, file=stdout)
    return 0
