"""Core #238 3G80: retained OS-private directory custody is never write authority."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_retained_root_custody as custody
from pds_core import _teacher_private_recovery_production_write_barrier as barrier

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_issue238_installed_retained_private_root.py"
)


def _restricted_tree(tmp_path: Path) -> Path:
    path = tmp_path / "paper-data-suite" / "private" / "notes" / "v1"
    path.mkdir(parents=True)
    for item in (path, path.parent, path.parent.parent):
        item.chmod(0o700)
    return path


def test_current_review_cannot_grant_authority() -> None:
    result = custody.review_existing_private_root_native_custody()
    assert isinstance(result.state, custody.PrivateRetainedRootState)
    assert not any(
        (
            result.production_mutation_admitted,
            result.automatic_replay_allowed,
            result.journal_retirement_allowed,
            result.notes_records_available,
            result.directory_crash_durability_qualified,
            result.noncooperating_writer_exclusion_qualified,
        )
    )
    assert "PrivateRetainedRootReview(non_authorizing=True)" == repr(result)
    assert len(barrier._REQUIRED) == 9


def test_missing_root_creates_nothing(tmp_path: Path) -> None:
    missing = tmp_path / "no-root" / "private" / "notes" / "v1"
    owner = (
        inspection._effective_owner(sys.platform)
        if sys.platform in {"linux", "win32"}
        else None
    )
    if owner is None:
        pytest.skip("Native platform only")
    observed = custody._probe_existing(missing, owner)
    assert observed is custody.PrivateRetainedRootState.MISSING
    assert not (tmp_path / "no-root").exists()


@pytest.mark.skipif(sys.platform != "linux", reason="Native POSIX FD custody")
def test_linux_real_private_dirfd_chain_retained_without_mutation(
    tmp_path: Path,
) -> None:
    path = _restricted_tree(tmp_path)
    before = tuple(
        sorted(str(item.relative_to(tmp_path)) for item in tmp_path.rglob("*"))
    )
    owner = inspection._effective_owner("linux")
    result = custody._probe_existing(path, owner)
    if result is custody.PrivateRetainedRootState.NATIVE_PROTECTION_REFUSED:
        pytest.skip("Native POSIX ACL capability unavailable on test filesystem")
    assert (
        result
        is custody.PrivateRetainedRootState.RETAINED_PRIVATE_ROOT_OBSERVED_UNQUALIFIED
    )
    assert before == tuple(
        sorted(str(item.relative_to(tmp_path)) for item in tmp_path.rglob("*"))
    )
    assert not list(path.iterdir())


@pytest.mark.skipif(sys.platform != "linux", reason="Native POSIX FD custody")
def test_linux_rejects_permissive_private_leaf(tmp_path: Path) -> None:
    path = _restricted_tree(tmp_path)
    path.chmod(0o755)
    owner = inspection._effective_owner("linux")
    assert (
        custody._probe_existing(path, owner)
        is custody.PrivateRetainedRootState.NATIVE_PROTECTION_REFUSED
    )


@pytest.mark.skipif(sys.platform != "linux", reason="Native POSIX FD custody")
def test_linux_rejects_symlinked_private_component(tmp_path: Path) -> None:
    path = _restricted_tree(tmp_path)
    link = path.parent / "alias"
    try:
        link.symlink_to(path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable")
    owner = inspection._effective_owner("linux")
    assert (
        custody._probe_existing(link, owner)
        is custody.PrivateRetainedRootState.NATIVE_PROTECTION_REFUSED
    )
    assert link.is_symlink()


@pytest.mark.skipif(sys.platform != "linux", reason="Native POSIX FD custody")
def test_linux_fake_owner_is_not_accepted(tmp_path: Path) -> None:
    path = _restricted_tree(tmp_path)
    actual = inspection._effective_owner("linux")
    fake = inspection.EffectiveOSOwner("posix_euid", str(int(actual.value) + 1000))
    assert (
        custody._probe_existing(path, fake)
        is custody.PrivateRetainedRootState.OWNER_UNAVAILABLE
    )


def test_missing_preliminary_root_does_not_enter_native_custody(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: object) -> None:
        pytest.fail("Missing private root unexpectedly entered native custody")

    monkeypatch.setattr(
        inspection,
        "inspect_private_root",
        lambda: inspection.PrivateRootInspection(
            inspection.PrivateRootState.MISSING, None, None, "synthetic absent"
        ),
    )
    monkeypatch.setattr(custody, "_probe_existing", forbidden)
    assert (
        custody.review_existing_private_root_native_custody().state
        is custody.PrivateRetainedRootState.MISSING
    )


def test_owner_probe_refusal_never_returns_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse() -> inspection.PrivateRootInspection:
        raise PermissionError("injected native permission refusal")

    monkeypatch.setattr(inspection, "inspect_private_root", refuse)
    result = custody.review_existing_private_root_native_custody()
    assert result.state is custody.PrivateRetainedRootState.ROOT_UNQUALIFIED
    assert not result.production_mutation_admitted


def test_installed_gate_static_safety_contract() -> None:
    data = SCRIPT.read_text(encoding="utf-8")
    ast.parse(data)
    for required in (
        "review_existing_private_root_native_custody()",
        "review_private_production_readiness()",
        '"production_mutation_admitted": False',
        '"journal_retirement_allowed": False',
        '"directory_crash_durability_qualified": False',
        '"noncooperating_writer_exclusion_qualified": False',
    ):
        assert required in data
    for forbidden in (
        "os.replace(",
        "os.mkdir(",
        "activate_notes(",
        "retire_private_journal(",
        "commit_private_workspace_binding(",
    ):
        assert forbidden not in data
