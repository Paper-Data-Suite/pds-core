"""#238 Slice 1: negative guards before private-store implementation.

No test here claims to qualify native OS isolation, Notes records, or creation.
"""

from __future__ import annotations

import json
from pathlib import Path

from pds_core.teacher_experience import get_teacher_experience_capabilities
from pds_core.workspace import (
    ensure_workspace_root,
    inspect_workspace_root,
    resolve_workspace_root,
)


_SIDECAR = "teacher-private-association.json"


def test_private_storage_is_not_advertised_by_terminal_contract() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )


def test_readonly_workspace_resolution_does_not_create_association(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "unbound-workspace"
    assert resolve_workspace_root(workspace) == workspace.resolve()
    inspection = inspect_workspace_root(workspace)
    assert inspection.exists is False
    assert not workspace.exists()
    assert not (workspace / ".pds" / _SIDECAR).exists()


def test_existing_workspace_initializer_only_creates_generic_marker(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "fresh-workspace"
    ensure_workspace_root(workspace, create=True)

    generic_marker = workspace / ".pds" / "workspace.json"
    assert json.loads(generic_marker.read_text(encoding="utf-8")) == {
        "created_by": "pds-core",
        "workspace_version": 1,
    }
    assert not (workspace / ".pds" / _SIDECAR).exists()

    before = generic_marker.read_bytes()
    inspection = inspect_workspace_root(workspace)
    assert inspection.exists and inspection.is_dir
    assert generic_marker.read_bytes() == before
    assert not (workspace / ".pds" / _SIDECAR).exists()


def test_generic_markers_are_not_unique_workspace_identities(
    tmp_path: Path,
) -> None:
    first = tmp_path / "synthetic-workspace-a"
    second = tmp_path / "synthetic-workspace-b"
    ensure_workspace_root(first, create=True)
    ensure_workspace_root(second, create=True)

    first_marker = (first / ".pds" / "workspace.json").read_bytes()
    second_marker = (second / ".pds" / "workspace.json").read_bytes()
    assert first_marker == second_marker
    assert not (first / ".pds" / _SIDECAR).exists()
    assert not (second / ".pds" / _SIDECAR).exists()
