"""3G91 Windows native delete-sharing exclusivity, disposable scratch only."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import cast

import pytest

from pds_core import _teacher_private_production_readiness as readiness
from pds_core import _teacher_private_scratch_windows_delete_sharing as probe
from pds_core.teacher_experience import get_teacher_experience_capabilities


def _blocked(result: probe.PrivateWindowsDeleteShareReview) -> None:
    assert not any(
        (
            result.production_mutation_admitted,
            result.windows_production_replace_qualified,
            result.noncooperating_writer_exclusion_qualified,
            result.atomic_content_compare_and_swap_qualified,
            result.automatic_replay_allowed,
            result.journal_retirement_allowed,
            result.notes_records_available,
            result.directory_crash_durability_qualified,
            result.multi_document_atomic_commit_qualified,
        )
    )
    assert repr(result) == (
        "PrivateWindowsDeleteShareReview(disposable_only=True, non_authorizing=True)"
    )


@pytest.mark.parametrize(
    "bad", [None, "live_handle_deny_delete", True, 0, Path("relative")]
)
def test_invalid_scenarios_fail_before_scratch_setup(bad: object) -> None:
    result = probe.probe_windows_disposable_delete_sharing(
        cast(probe.PrivateWindowsDeleteShareScenario, bad)
    )
    assert result.state is probe.PrivateWindowsDeleteShareState.INVALID_REQUEST_REFUSED
    assert not result.native_windows_handle_retained
    _blocked(result)


@pytest.mark.parametrize("scenario", list(probe.PrivateWindowsDeleteShareScenario))
@pytest.mark.skipif(sys.platform != "win32", reason="native Windows only")
def test_windows_open_handle_denies_delete_then_releases(
    scenario: probe.PrivateWindowsDeleteShareScenario,
) -> None:
    result = probe.probe_windows_disposable_delete_sharing(scenario)
    assert (
        result.state
        is probe.PrivateWindowsDeleteShareState.DELETE_SHARE_DENIED_THEN_RELEASED
    )
    assert result.native_windows_handle_retained
    assert result.native_directory_handle_retained
    assert result.cooperating_lock_held
    assert result.independent_writer_refused_while_handle_held
    assert result.before_images_preserved_while_handle_held
    assert result.same_writer_succeeded_after_close
    assert result.synthetic_afterimage_verified
    assert result.pending_synthetic_journal_preserved
    _blocked(result)


@pytest.mark.parametrize("scenario", list(probe.PrivateWindowsDeleteShareScenario))
@pytest.mark.skipif(sys.platform != "linux", reason="Linux refusal only")
def test_linux_refuses_windows_native_protocol(
    scenario: probe.PrivateWindowsDeleteShareScenario,
) -> None:
    result = probe.probe_windows_disposable_delete_sharing(scenario)
    assert (
        result.state
        is probe.PrivateWindowsDeleteShareState.LINUX_WINDOWS_PROTOCOL_UNQUALIFIED
    )
    assert not result.native_windows_handle_retained
    _blocked(result)


def test_requirement_taxonomy_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if sys.platform == "linux":
        # Linux must refuse earlier, without consulting Windows requirements.
        return
    monkeypatch.setattr(readiness, "_REQUIRED", readiness._REQUIRED[:-1])
    result = probe.probe_windows_disposable_delete_sharing(
        probe.PrivateWindowsDeleteShareScenario.LIVE_HANDLE_DENY_DELETE
    )
    assert (
        result.state is probe.PrivateWindowsDeleteShareState.REQUIREMENT_DRIFT_REFUSED
    )
    _blocked(result)


def test_no_public_paths_handle_callback_payload_or_notes_activation() -> None:
    path = probe.__file__
    assert path is not None
    source = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "probe_windows_disposable_delete_sharing"
    )
    assert [arg.arg for arg in fn.args.args] == ["scenario"]
    assert not fn.args.vararg and not fn.args.kwarg
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    for forbidden in (
        "commit_private_workspace_binding(",
        "retire_private_journal(",
        "activate_notes(",
        "ensure_workspace_root(",
        "review_private_production_write_barrier(",
    ):
        assert forbidden not in source
