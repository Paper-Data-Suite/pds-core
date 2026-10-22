"""Contract-level tests for Core teacher-experience version and capabilities."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import get_type_hints

import pytest

from pds_core import teacher_experience
from pds_core.teacher_experience import (
    TEACHER_EXPERIENCE_CONTRACT_VERSION,
    get_teacher_experience_capabilities,
)


def test_contract_version_is_exact_and_independent_of_package_release() -> None:
    assert TEACHER_EXPERIENCE_CONTRACT_VERSION == "1"
    assert teacher_experience.TEACHER_EXPERIENCE_CONTRACT_VERSION == "1"


def test_public_function_has_accepted_immutable_return_type() -> None:
    assert (
        get_type_hints(get_teacher_experience_capabilities)["return"] == frozenset[str]
    )
    capabilities = get_teacher_experience_capabilities()
    assert isinstance(capabilities, frozenset)
    assert capabilities == get_teacher_experience_capabilities()
    with pytest.raises(AttributeError):
        capabilities.add("terminal.header.v1")  # type: ignore[attr-defined]


def test_initial_slice_advertises_no_incomplete_core_facility() -> None:
    # The header printer and prompt-scoped parser do not exist until later slices.
    assert get_teacher_experience_capabilities() == frozenset()


@pytest.mark.parametrize(
    "unqualified",
    [
        "terminal.header.v1",
        "terminal.notes_command.v1",
        "notes.records.v1",
        "notes.menu.v1",
        "notes.cli.v1",
        "classroom.roster_edits.v1",
        "classroom.menu.v1",
        "notes.portability.v1",
    ],
)
def test_unqualified_capabilities_are_not_advertised(unqualified: str) -> None:
    assert unqualified not in get_teacher_experience_capabilities()


def test_module_exports_only_accepted_public_symbols() -> None:
    assert set(teacher_experience.__all__) == {
        "TEACHER_EXPERIENCE_CONTRACT_VERSION",
        "get_teacher_experience_capabilities",
    }


def test_clean_process_import_does_not_prompt_print_or_write(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(project_root), environment.get("PYTHONPATH", ""))
    )
    probe = (
        "from pds_core.teacher_experience import "
        "TEACHER_EXPERIENCE_CONTRACT_VERSION, "
        "get_teacher_experience_capabilities; "
        "assert TEACHER_EXPERIENCE_CONTRACT_VERSION == '1'; "
        "assert get_teacher_experience_capabilities() == frozenset()"
    )
    result = subprocess.run(  # noqa: S603 - constant interpreter + fixed code
        [sys.executable, "-B", "-c", probe],
        cwd=tmp_path,
        env=environment,
        input="",
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    assert list(tmp_path.iterdir()) == []
