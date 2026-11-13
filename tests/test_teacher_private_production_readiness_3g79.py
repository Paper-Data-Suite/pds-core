"""Core #238 3G79: installed readiness review is non-authorizing."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Any

import pytest

from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_native_preflight as native
from pds_core import _teacher_private_production_readiness as review
from pds_core import _teacher_private_recovery_production_write_barrier as barrier


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_issue238_installed_production_readiness.py"
)


def _probe() -> Any:
    spec = importlib.util.spec_from_file_location("core238_3g79_probe", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_requirement_list_matches_exact_production_barrier() -> None:
    assert review._REQUIRED == tuple(item.value for item in barrier._REQUIRED)
    assert len(review._REQUIRED) == 9
    assert "recovery_and_journal_retirement_protocol" in review._REQUIRED


def test_current_native_probes_cannot_grant_production_write() -> None:
    result = review.review_private_production_readiness()
    assert result.state in {
        review.PrivateProductionReadinessState.PRODUCTION_BLOCKED,
        review.PrivateProductionReadinessState.PROBE_REFUSED_PRODUCTION_BLOCKED,
    }
    assert result.unqualified_requirements == review._REQUIRED
    assert not result.production_mutation_admitted
    assert not result.automatic_replay_allowed
    assert not result.journal_retirement_allowed
    assert not result.directory_crash_durability_qualified
    assert not result.multi_document_atomic_commit_qualified
    assert not result.noncooperating_writer_exclusion_qualified
    assert "private" not in repr(result).lower() or "non_authorizing" in repr(result)
    assert "notes" not in result.__repr__().lower()


@pytest.mark.parametrize(
    "root_state,native_state",
    [
        (
            inspection.PrivateRootState.MISSING,
            native.NativePrivatePreflightState.MISSING,
        ),
        (
            inspection.PrivateRootState.PRESENT_UNVERIFIED,
            native.NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED,
        ),
        (
            inspection.PrivateRootState.UNSAFE_PATH,
            native.NativePrivatePreflightState.REFUSED_PATH,
        ),
    ],
)
def test_even_positive_native_read_only_snapshot_stays_blocked(
    monkeypatch: pytest.MonkeyPatch,
    root_state: inspection.PrivateRootState,
    native_state: native.NativePrivatePreflightState,
) -> None:
    # This intentionally injects a fake SID/UID and path: they cannot be returned.
    pretend = inspection.PrivateRootInspection(
        root_state,
        inspection.EffectiveOSOwner("posix_euid", "424242"),
        Path("/sensitive/teacher-private"),
        "untrusted synthetic owner claim",
    )
    monkeypatch.setattr(inspection, "inspect_private_root", lambda: pretend)
    monkeypatch.setattr(
        native,
        "inspect_native_private_preflight",
        lambda: native._outcome(native_state),
    )
    result = review.review_private_production_readiness()
    assert result.state is review.PrivateProductionReadinessState.PRODUCTION_BLOCKED
    assert result.owner_observed
    assert result.root_observation == root_state.value
    assert result.native_root_observation == native_state.value
    assert result.unqualified_requirements == review._REQUIRED
    assert "424242" not in repr(result)
    assert "sensitive" not in repr(result)
    probe = _probe()
    document = probe._readiness()
    assert document["production_mutation_admitted"] is False
    assert "424242" not in str(document)
    assert "sensitive" not in str(document)


def test_owner_probe_refusal_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse() -> inspection.PrivateRootInspection:
        raise PermissionError("synthetic path must not leak")

    monkeypatch.setattr(inspection, "inspect_private_root", refuse)
    result = review.review_private_production_readiness()
    assert (
        result.state
        is review.PrivateProductionReadinessState.PROBE_REFUSED_PRODUCTION_BLOCKED
    )
    assert result.root_observation == "unavailable"
    assert result.native_root_observation == "unavailable"
    assert not result.owner_observed
    assert result.unqualified_requirements == review._REQUIRED


def test_requirement_drift_fails_closed_before_probes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(barrier, "_REQUIRED", tuple(barrier._REQUIRED[:-1]))

    def forbidden() -> inspection.PrivateRootInspection:
        raise AssertionError("drift must not trigger native probe")

    monkeypatch.setattr(inspection, "inspect_private_root", forbidden)
    result = review.review_private_production_readiness()
    assert (
        result.state
        is review.PrivateProductionReadinessState.REQUIREMENT_CONTRACT_CHANGED_BLOCKED
    )
    assert result.unqualified_requirements == review._REQUIRED
    assert not result.production_mutation_admitted


def test_installed_gate_never_mints_authority_or_private_paths() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    ast.parse(source)
    for required in (
        "_installed_provenance(wheel, source, args.expected_version)",
        "review_private_production_readiness()",
        "review_private_production_write_barrier(",
        '"unqualified_requirements": list(review.unqualified_requirements)',
        '"production_mutation_admitted": False',
        '"journal_retirement_allowed": False',
        '"directory_crash_durability_qualified": False',
    ):
        assert required in source
    for forbidden in (
        "os.replace(",
        "os.mkdir(",
        "retire_private_journal(",
        "commit_private_workspace_binding(",
        "activate_notes(",
        "subprocess.shell=True",
    ):
        assert forbidden not in source
