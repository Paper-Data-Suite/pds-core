"""3G81: native Windows protected scratch ACL fixture, not production authority."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_issue238_installed_windows_protected_fixture.py"
)


def _probe() -> Any:
    spec = importlib.util.spec_from_file_location("core238_fixture_3g81", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixture_uses_real_sid_explicit_protected_dacl_and_native_custody() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    ast.parse(text)
    for required in (
        'inspection._effective_owner("win32")',
        "provision._known_fixed_local_volume(kernel, scratch)",
        "provision._create_directory_explicit_dacl(",
        "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)",
        "(A;OICI;GR;;;WD)",
        "custody._probe_existing(secure, owner)",
        "custody._probe_existing(unprotected, owner)",
        "custody._probe_existing(secure, spoofed_owner)",
        '"production_mutation_admitted": False',
        '"journal_retirement_allowed": False',
        '"directory_crash_durability_qualified": False',
    ):
        assert required in text
    for forbidden in (
        "commit_private_workspace_binding(",
        "retire_private_journal(",
        "activate_notes(",
        "os.replace(",
        "shutil.rmtree(",
        "os.chmod(",
        "os.chown(",
        "subprocess.shell=True",
    ):
        assert forbidden not in text


def test_windows_fixture_refuses_nonwindows_before_native_creation(
    tmp_path: Path,
) -> None:
    if sys.platform == "win32":
        pytest.skip("actual native Windows fixture tested below")
    probe = _probe()
    before = tuple(tmp_path.iterdir())
    with pytest.raises(RuntimeError, match="windows_fixture_on_unsupported_platform"):
        probe._windows_fixture(tmp_path)
    assert tuple(tmp_path.iterdir()) == before


@pytest.mark.skipif(sys.platform != "win32", reason="Real Windows token/DACL only")
def test_real_windows_protected_dacl_and_refusals(tmp_path: Path) -> None:
    probe = _probe()
    report = probe._windows_fixture(tmp_path)
    assert report == {
        "protected_owner_dacl_fixture": "retained_private_root_observed_unqualified",
        "missing_protected_leaf": "missing",
        "forged_effective_owner": "owner_unavailable",
        "everyone_read_dacl_fixture": "native_protection_refused",
        "native_identity_rechecked_with_retained_handles": True,
        "fixed_local_ntfs_or_refs_qualified_for_fixture": True,
    }
    # Native HANDLEs must close so TemporaryDirectory can remove all own paths.
    assert not tuple(tmp_path.glob("core238_3g81_*"))


@pytest.mark.skipif(sys.platform != "linux", reason="Linux-only negative fixture")
def test_linux_leg_does_not_create_a_windows_fixture(tmp_path: Path) -> None:
    probe = _probe()
    report = probe._linux_negative_fixture(tmp_path)
    assert report == {
        "windows_native_fixture": "not_applicable_linux",
        "linux_no_fixture_writes": True,
    }
    assert not tuple(tmp_path.iterdir())


def test_unsupported_fixture_volume_never_relaxes_backing_requirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = _probe()

    class RefuseAllBacking:
        def _known_fixed_local_volume(self, _kernel: object, _path: Path) -> bool:
            return False

    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    with pytest.raises(RuntimeError, match="no_qualified_local_fixture_volume"):
        probe._qualified_windows_fixture_parent(tmp_path, object(), RefuseAllBacking())
    assert not tuple(tmp_path.iterdir())


def test_fallback_guard_explicitly_refuses_unverified_user_root() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    ast.parse(text)
    for guard in (
        'os.environ.get("LOCALAPPDATA")',
        'candidate = local / "Temp"',
        "candidate.is_relative_to(home)",
        "segment.is_symlink()",
        'getattr(info, "st_file_attributes", 0) & 0x400',
        "provision._known_fixed_local_volume(kernel, candidate)",
    ):
        assert guard in text
    assert any(
        isinstance(node, ast.Compare)
        and ast.unparse(node)
        == "base.parent.resolve(strict=True) != selected.resolve(strict=True)"
        for node in ast.walk(ast.parse(text))
    )
    for forbidden in (
        "os.mkdir(",
        "os.makedirs(",
        "os.chmod(",
        "os.chown(",
        "shutil.rmtree(",
        "retire_private_journal(",
    ):
        assert forbidden not in text


def test_no_permissive_windows_acl_acceptance_or_production_handle() -> None:
    probe = _probe()
    assert probe._EXPECTED == "retained_private_root_observed_unqualified"
    assert probe._REJECTED == "native_protection_refused"
    assert probe._NOT_OWNER == "owner_unavailable"
    assert probe._MISSING == "missing"
    from pds_core import _teacher_private_production_readiness as readiness

    review = readiness.review_private_production_readiness()
    assert len(review.unqualified_requirements) == 9
    assert review.production_mutation_admitted is False
    assert review.journal_retirement_allowed is False
