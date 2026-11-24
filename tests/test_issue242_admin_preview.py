"""Core #242 C3B1 synthetic acceptance for read-only administration plans."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import pds_core.classroom_admin_preview as admin
from pds_core.classroom_admin_preview import (
    ClassCreationChange,
    ClassroomAdministrationPreviewError,
    SchoolYearChange,
    plan_class_creation,
    plan_school_year_change,
)
from pds_core.classes import ensure_class_folder
from pds_core.routes import class_metadata_path, class_roster_path
from pds_core.school_years import (
    close_school_year,
    open_school_year,
    school_year_state_path,
)

OPENED = datetime(2026, 9, 1, tzinfo=timezone.utc)
CLOSED = datetime(2027, 6, 30, tzinfo=timezone.utc)
YEAR = "2026-2027"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    location = tmp_path / "synthetic-workspace"
    location.mkdir()
    return location


def _open(root: Path) -> None:
    open_school_year(root, YEAR, opened_at=OPENED)


def test_initial_open_only_previews_and_does_not_initialize_files(root: Path) -> None:
    state_path = school_year_state_path(root)
    preview = plan_school_year_change(root, SchoolYearChange("open", YEAR))
    assert preview.workspace_root == root.resolve()
    assert preview.previous_record_status == "missing"
    assert preview.previous_school_year is None
    assert preview.proposed_active_year == YEAR
    assert not preview.no_change
    assert len(preview.state_token) == 64
    assert len(preview.candidate_token) == 64
    assert preview.state_token != preview.candidate_token
    assert not state_path.exists()
    assert not (root / "settings").exists()


def test_same_open_year_previews_a_noop_without_rewriting_state(root: Path) -> None:
    _open(root)
    path = school_year_state_path(root)
    before = path.read_bytes()
    preview = plan_school_year_change(root, SchoolYearChange("open", YEAR))
    assert preview.no_change
    assert preview.previous_record_status == "open"
    assert preview.previous_school_year == YEAR
    assert preview.proposed_active_year == YEAR
    assert path.read_bytes() == before


def test_close_preview_keeps_year_active_and_bytes_unchanged(root: Path) -> None:
    _open(root)
    path = school_year_state_path(root)
    before = path.read_bytes()
    preview = plan_school_year_change(root, SchoolYearChange("close"))
    assert preview.action == "close"
    assert preview.previous_record_status == "open"
    assert preview.previous_school_year == YEAR
    assert preview.proposed_active_year is None
    assert not preview.no_change
    assert path.read_bytes() == before


def test_close_without_active_year_fails_safely(root: Path) -> None:
    with pytest.raises(ClassroomAdministrationPreviewError) as raised:
        plan_school_year_change(root, SchoolYearChange("close"))
    assert raised.value.reason == "no_open_year"
    assert not school_year_state_path(root).exists()


def test_different_active_year_is_never_silently_overwritten(root: Path) -> None:
    _open(root)
    path = school_year_state_path(root)
    before = path.read_bytes()
    with pytest.raises(ClassroomAdministrationPreviewError) as raised:
        plan_school_year_change(root, SchoolYearChange("open", "2027-2028"))
    assert raised.value.reason == "active_year_conflict"
    assert path.read_bytes() == before


def test_closed_year_history_cannot_be_replaced_by_default(root: Path) -> None:
    _open(root)
    close_school_year(root, closed_at=CLOSED)
    path = school_year_state_path(root)
    before = path.read_bytes()
    with pytest.raises(ClassroomAdministrationPreviewError) as raised:
        plan_school_year_change(root, SchoolYearChange("open", "2027-2028"))
    assert raised.value.reason == "year_history_policy_required"
    assert path.read_bytes() == before


def test_existing_closed_year_cannot_be_closed_again(root: Path) -> None:
    _open(root)
    close_school_year(root, closed_at=CLOSED)
    with pytest.raises(ClassroomAdministrationPreviewError) as raised:
        plan_school_year_change(root, SchoolYearChange("close"))
    assert raised.value.reason == "no_open_year"


def test_year_change_rejects_invalid_shapes() -> None:
    with pytest.raises(ValueError):
        SchoolYearChange("open")
    with pytest.raises(ValueError):
        SchoolYearChange("open", "2026-2028")
    with pytest.raises(ValueError):
        SchoolYearChange("close", YEAR)
    with pytest.raises(ValueError):
        SchoolYearChange("invalid")  # type: ignore[arg-type]


def test_class_creation_preview_never_creates_folder_metadata_or_roster(
    root: Path,
) -> None:
    _open(root)
    path = school_year_state_path(root)
    before = path.read_bytes()
    preview = plan_class_creation(root, ClassCreationChange("english10_p2", YEAR))
    assert preview.workspace_root == root.resolve()
    assert preview.active_school_year == YEAR
    assert preview.target_class_directory == root / "classes" / "english10_p2"
    assert preview.metadata_would_be_created
    assert not preview.roster_would_be_created
    assert len(preview.state_token) == 64
    assert len(preview.candidate_token) == 64
    assert not preview.target_class_directory.exists()
    assert not class_metadata_path(root, "english10_p2").exists()
    assert not class_roster_path(root, "english10_p2").exists()
    assert path.read_bytes() == before


def test_distinct_class_candidates_produce_distinct_tokens(root: Path) -> None:
    _open(root)
    one = plan_class_creation(root, ClassCreationChange("english10_p2", YEAR))
    two = plan_class_creation(root, ClassCreationChange("english10_p3", YEAR))
    assert one.state_token == two.state_token
    assert one.candidate_token != two.candidate_token


def test_class_creation_refuses_missing_active_year(root: Path) -> None:
    with pytest.raises(ClassroomAdministrationPreviewError) as raised:
        plan_class_creation(root, ClassCreationChange("english10_p2", YEAR))
    assert raised.value.reason == "no_open_year"
    assert not (root / "classes").exists()


def test_class_creation_refuses_mismatched_active_year(root: Path) -> None:
    _open(root)
    with pytest.raises(ClassroomAdministrationPreviewError) as raised:
        plan_class_creation(
            root, ClassCreationChange("english10_p2", "2027-2028")
        )
    assert raised.value.reason == "year_mismatch"
    assert not (root / "classes").exists()


def test_class_creation_refuses_existing_class_without_touching_folder(
    root: Path,
) -> None:
    _open(root)
    folder = ensure_class_folder(root, "english10_p2")
    sentinel = folder.class_dir / "protected.txt"
    sentinel.write_text("existing", encoding="utf-8")
    with pytest.raises(ClassroomAdministrationPreviewError) as raised:
        plan_class_creation(root, ClassCreationChange("english10_p2", YEAR))
    assert raised.value.reason == "class_exists"
    assert sentinel.read_text(encoding="utf-8") == "existing"


def test_malformed_school_year_fails_without_replacement(root: Path) -> None:
    target = school_year_state_path(root)
    target.parent.mkdir()
    target.write_text("{invalid JSON", encoding="utf-8")
    before = target.read_bytes()
    with pytest.raises(ClassroomAdministrationPreviewError) as raised:
        plan_school_year_change(root, SchoolYearChange("open", YEAR))
    assert raised.value.reason == "invalid_school_year"
    assert str(root) not in str(raised.value)
    assert target.read_bytes() == before


def test_oversized_school_year_state_is_refused_before_json_loading(root: Path) -> None:
    path = school_year_state_path(root)
    path.parent.mkdir()
    path.write_bytes(b"z" * (64 * 1024 + 1))
    with pytest.raises(ClassroomAdministrationPreviewError) as raised:
        plan_school_year_change(root, SchoolYearChange("open", YEAR))
    assert raised.value.reason == "oversized_year_state"
    assert path.stat().st_size == 64 * 1024 + 1


def test_missing_workspace_refuses_without_creating_it(tmp_path: Path) -> None:
    location = tmp_path / "missing-workspace"
    with pytest.raises(ClassroomAdministrationPreviewError) as raised:
        plan_school_year_change(location, SchoolYearChange("open", YEAR))
    assert raised.value.reason == "missing_workspace"
    assert not location.exists()


def test_redirected_school_year_state_path_fails_closed(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = school_year_state_path(root)
    original = Path.is_symlink

    def redirected(candidate: Path) -> bool:
        return candidate == path or original(candidate)

    monkeypatch.setattr(Path, "is_symlink", redirected)
    with pytest.raises(ClassroomAdministrationPreviewError) as raised:
        plan_school_year_change(root, SchoolYearChange("open", YEAR))
    assert raised.value.reason == "unsafe_path"
    assert not path.exists()


def test_state_snapshot_rejects_mid_read_change(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = admin._state_fingerprint
    calls = 0

    def changed(path: Path) -> str:
        nonlocal calls
        calls += 1
        return original(path) if calls <= 2 else "f" * 64

    monkeypatch.setattr(admin, "_state_fingerprint", changed)
    with pytest.raises(ClassroomAdministrationPreviewError) as raised:
        plan_school_year_change(root, SchoolYearChange("open", YEAR))
    assert raised.value.reason == "stale_year_state"
    assert calls == 3


def test_invalid_class_identifier_rejected_by_existing_core_validator() -> None:
    with pytest.raises(ValueError):
        ClassCreationChange("not a valid id!", YEAR)
    with pytest.raises(ValueError):
        ClassCreationChange("english10_p2", "2026-2028")
