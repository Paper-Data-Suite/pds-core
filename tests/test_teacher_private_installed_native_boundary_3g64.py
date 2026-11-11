"""#238 3G64: source-level native negative gates before installed-wheel CI.

These are not an installed-artifact result; the standalone D2 script and
native Windows/Linux CI jobs provide that separate evidence.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_native_preflight as native
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core.teacher_experience import get_teacher_experience_capabilities
from pds_core.workspace import inspect_workspace_root


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native platform")
def test_absent_synthetic_root_and_workspace_remain_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = "LOCALAPPDATA" if sys.platform == "win32" else "XDG_DATA_HOME"
    monkeypatch.setenv(key, str(tmp_path))
    before = tuple(tmp_path.iterdir())
    preview = inspection.inspect_private_root()
    assert preview.state is inspection.PrivateRootState.MISSING
    assert preview.owner is not None
    assert (
        native.inspect_native_private_preflight().state
        is native.NativePrivatePreflightState.MISSING
    )
    workspace = tmp_path / "synthetic-unbound-workspace"
    assert not inspect_workspace_root(workspace).exists
    assert not workspace.exists()
    assert tuple(tmp_path.iterdir()) == before


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native platform")
def test_invalid_private_root_env_is_refused_without_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if sys.platform == "win32":
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
    else:
        monkeypatch.setenv("XDG_DATA_HOME", "relative-path-must-refuse")
    assert (
        inspection.inspect_private_root().state
        is inspection.PrivateRootState.INVALID_CONFIGURATION
    )
    assert not tuple(tmp_path.iterdir())


def test_no_notes_api_or_production_write_permit() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert importlib.util.find_spec("pds_core.teacher_private_storage") is None
    result = barrier.review_private_production_write_barrier(
        None,  # type: ignore[arg-type]
        0,
        None,  # type: ignore[arg-type]
    )
    assert result.state is barrier.PrivateProductionWriteBarrierState.INVALID_REQUEST
    assert result.unqualified_requirements == tuple(
        barrier.PrivateProductionWriteRequirement
    )
    assert not any(hasattr(result, item) for item in ("permit", "execute", "write"))
