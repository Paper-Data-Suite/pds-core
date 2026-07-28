from pathlib import Path

import pytest

from pds_core.academic_work_registrations import AcademicWorkRegistrationValidationError
from pds_core.publication_records import PublicationRecordValidationError
from pds_core.registry_paths import (
    academic_catalog_lock_path,
    academic_catalog_path,
    academic_work_registration_current_path,
    academic_work_registration_dir,
    academic_work_registration_revision_path,
    academic_work_registration_revisions_dir,
    academic_work_registrations_dir,
    publication_record_path,
    publication_withdrawal_path,
    publication_withdrawals_dir,
    publications_dir,
    registry_dir,
)
from pds_core.routing_models import ModuleWorkRef


def test_registry_paths_are_exact_normalized_and_pure(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "english10_p2", "essay")
    assert registry_dir(str(tmp_path)) == tmp_path / "registry"
    assert academic_work_registrations_dir(tmp_path) == tmp_path / "registry" / "work"
    base = tmp_path / "registry" / "work" / "english10_p2" / "quillan" / "essay"
    assert academic_work_registration_dir(tmp_path, work) == base
    assert academic_work_registration_revisions_dir(tmp_path, work) == base / "revisions"
    assert academic_work_registration_revision_path(tmp_path, work, 2) == base / "revisions" / "2.json"
    assert academic_work_registration_current_path(tmp_path, work) == base / "current.json"
    assert not (tmp_path / "registry").exists()


def test_academic_catalog_paths_are_exact_and_pure(tmp_path: Path) -> None:
    assert academic_catalog_path(tmp_path) == tmp_path / "registry" / "catalog.sqlite"
    assert academic_catalog_lock_path(tmp_path) == (
        tmp_path / "registry" / ".locks" / "catalog.lock"
    )
    assert not (tmp_path / "registry").exists()


@pytest.mark.parametrize("revision", [0, -1, True, "1"])
def test_revision_path_rejects_invalid_revision(tmp_path: Path, revision: object) -> None:
    with pytest.raises(AcademicWorkRegistrationValidationError):
        academic_work_registration_revision_path(
            tmp_path, ModuleWorkRef("quillan", "class", "work"), revision  # type: ignore[arg-type]
        )


def test_paths_require_actual_work_ref(tmp_path: Path) -> None:
    with pytest.raises(AcademicWorkRegistrationValidationError):
        academic_work_registration_dir(tmp_path, {"module_id": "quillan"})  # type: ignore[arg-type]


def test_publication_paths_are_exact_normalized_and_pure(tmp_path: Path) -> None:
    publication_id = "pub_0123456789abcdef0123456789abcdef"
    assert publications_dir(str(tmp_path)) == tmp_path / "registry" / "publications"
    assert publication_record_path(tmp_path, publication_id) == (
        tmp_path / "registry" / "publications" / f"{publication_id}.json"
    )
    assert publication_withdrawals_dir(tmp_path) == tmp_path / "registry" / "withdrawals"
    assert publication_withdrawal_path(tmp_path, publication_id) == (
        tmp_path / "registry" / "withdrawals" / f"{publication_id}.json"
    )
    assert not (tmp_path / "registry").exists()


@pytest.mark.parametrize("publication_id", ["pub_ABC", "pub_" + "A" * 32, "x"])
def test_publication_paths_reject_invalid_ids(
    tmp_path: Path, publication_id: str
) -> None:
    with pytest.raises(PublicationRecordValidationError):
        publication_record_path(tmp_path, publication_id)
