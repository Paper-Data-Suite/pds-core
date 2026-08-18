from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pds_core.grouping_signal_storage import (
    GROUPING_SIGNAL_DIGEST_ALGORITHM,
    GroupingSignalConflictError,
    GroupingSignalIntegrityError,
    GroupingSignalNotFoundError,
    GroupingSignalReadError,
    calculate_grouping_signal_digest,
    grouping_signal_class_dir,
    grouping_signal_digest_path,
    grouping_signal_path,
    grouping_signals_dir,
    list_grouping_signal_ids,
    load_grouping_signal,
    write_grouping_signal,
)
from pds_core.grouping_signals import (
    GroupingSignalDimension,
    GroupingSignalSet,
    GroupingSignalSource,
    GroupingSignalStudentBand,
    grouping_signal_set_to_json_bytes,
)

NOW = datetime(2026, 9, 1, 18, tzinfo=UTC)
DIGEST = "a" * 64


def signal(**changes: object) -> GroupingSignalSet:
    values: dict[str, object] = {
        "schema_version": "1",
        "record_type": "grouping_signal_set",
        "signal_set_id": "signal_001",
        "class_id": "english10_p2",
        "created_at": NOW,
        "source": GroupingSignalSource("module_generated", "meridian", "source_001", "sha256", DIGEST),
        "dimensions": (GroupingSignalDimension("reading_analysis", 4),),
        "student_bands": (
            GroupingSignalStudentBand("student_001", "reading_analysis", 2),
            GroupingSignalStudentBand("student_002", "reading_analysis", 4),
        ),
    }
    values.update(changes)
    return GroupingSignalSet(**values)  # type: ignore[arg-type]


def test_paths_are_exact_and_do_not_require_workspace_state(tmp_path: Path) -> None:
    assert grouping_signals_dir(tmp_path) == tmp_path / "exchange" / "grouping-signals"
    assert grouping_signal_class_dir(tmp_path, "class_1") == tmp_path / "exchange" / "grouping-signals" / "class_1"
    assert grouping_signal_path(tmp_path, "class_1", "signal_1") == tmp_path / "exchange" / "grouping-signals" / "class_1" / "signal_1.json"
    assert grouping_signal_digest_path(tmp_path, "class_1", "signal_1") == tmp_path / "exchange" / "grouping-signals" / "class_1" / "signal_1.json.sha256"


@pytest.mark.parametrize("value", ["", "../x", " x", "x/y"])
def test_paths_reject_unsafe_identifiers(tmp_path: Path, value: str) -> None:
    with pytest.raises(Exception):
        grouping_signal_path(tmp_path, value, "signal")
    with pytest.raises(Exception):
        grouping_signal_path(tmp_path, "class", value)


def test_digest_is_exact_canonical_json_sha256() -> None:
    value = signal()
    assert GROUPING_SIGNAL_DIGEST_ALGORITHM == "sha256"
    assert calculate_grouping_signal_digest(value) == hashlib.sha256(grouping_signal_set_to_json_bytes(value)).hexdigest()


def test_write_load_and_sidecar_are_exact(tmp_path: Path) -> None:
    value = signal()
    result = write_grouping_signal(tmp_path, value)
    assert result.disposition == "created"
    json_path = grouping_signal_path(tmp_path, value.class_id, value.signal_set_id)
    digest_path = grouping_signal_digest_path(tmp_path, value.class_id, value.signal_set_id)
    assert json_path.read_bytes() == grouping_signal_set_to_json_bytes(value)
    expected = hashlib.sha256(json_path.read_bytes()).hexdigest()
    assert digest_path.read_bytes() == (expected + "\n").encode("ascii")
    assert result.stored.signal == value
    assert result.stored.digest == expected
    loaded = load_grouping_signal(tmp_path, value.class_id, value.signal_set_id)
    assert loaded == result.stored


def test_exact_retry_is_existing_without_rewrite(tmp_path: Path) -> None:
    value = signal()
    first = write_grouping_signal(tmp_path, value)
    json_path = grouping_signal_path(tmp_path, value.class_id, value.signal_set_id)
    digest_path = grouping_signal_digest_path(tmp_path, value.class_id, value.signal_set_id)
    original_json = json_path.read_bytes()
    original_digest = digest_path.read_bytes()
    second = write_grouping_signal(tmp_path, value)
    assert first.disposition == "created"
    assert second.disposition == "existing"
    assert json_path.read_bytes() == original_json
    assert digest_path.read_bytes() == original_digest


@pytest.mark.parametrize(
    "changed",
    [
        signal(student_bands=(GroupingSignalStudentBand("student_001", "reading_analysis", 3), GroupingSignalStudentBand("student_002", "reading_analysis", 4))),
        signal(created_at=NOW + timedelta(seconds=1)),
        signal(source=GroupingSignalSource("module_generated", "meridian", "source_002", "sha256", "b" * 64)),
        signal(dimensions=(GroupingSignalDimension("writing", 4),), student_bands=(GroupingSignalStudentBand("student_001", "writing", 2),)),
        signal(dimensions=(GroupingSignalDimension("reading_analysis", 5),)),
        signal(student_bands=(GroupingSignalStudentBand("student_001", "reading_analysis", 2),)),
    ],
)
def test_same_identity_different_contents_conflict_without_mutation(tmp_path: Path, changed: GroupingSignalSet) -> None:
    original = signal()
    write_grouping_signal(tmp_path, original)
    json_path = grouping_signal_path(tmp_path, original.class_id, original.signal_set_id)
    digest_path = grouping_signal_digest_path(tmp_path, original.class_id, original.signal_set_id)
    before = (json_path.read_bytes(), digest_path.read_bytes())
    with pytest.raises(GroupingSignalConflictError):
        write_grouping_signal(tmp_path, changed)
    assert (json_path.read_bytes(), digest_path.read_bytes()) == before


def test_missing_pair_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(GroupingSignalNotFoundError):
        load_grouping_signal(tmp_path, "class_1", "signal_1")


@pytest.mark.parametrize("keep", ["json", "digest"])
def test_partial_pair_is_integrity_failure(tmp_path: Path, keep: str) -> None:
    value = signal()
    write_grouping_signal(tmp_path, value)
    json_path = grouping_signal_path(tmp_path, value.class_id, value.signal_set_id)
    digest_path = grouping_signal_digest_path(tmp_path, value.class_id, value.signal_set_id)
    (digest_path if keep == "json" else json_path).unlink()
    with pytest.raises(GroupingSignalIntegrityError):
        load_grouping_signal(tmp_path, value.class_id, value.signal_set_id)
    with pytest.raises(GroupingSignalIntegrityError):
        write_grouping_signal(tmp_path, value)


@pytest.mark.parametrize(
    "sidecar",
    [
        b"b" * 64 + b"\n",
        b"A" * 64 + b"\n",
        b"a" * 63 + b"\n",
        b"g" * 64 + b"\n",
        b" " + b"a" * 64 + b"\n",
        b"a" * 64 + b" \n",
        b"a" * 64,
        b"a" * 64 + b"\n\n",
        b"a" * 64 + b"\r\n",
        b"\xef\xbb\xbf" + b"a" * 64 + b"\n",
    ],
)
def test_corrupt_digest_sidecar_is_rejected(tmp_path: Path, sidecar: bytes) -> None:
    value = signal()
    write_grouping_signal(tmp_path, value)
    digest_path = grouping_signal_digest_path(tmp_path, value.class_id, value.signal_set_id)
    digest_path.write_bytes(sidecar)
    error = GroupingSignalIntegrityError if sidecar == b"b" * 64 + b"\n" else GroupingSignalReadError
    with pytest.raises(error):
        load_grouping_signal(tmp_path, value.class_id, value.signal_set_id)


def test_noncanonical_json_with_matching_digest_is_rejected(tmp_path: Path) -> None:
    value = signal()
    write_grouping_signal(tmp_path, value)
    json_path = grouping_signal_path(tmp_path, value.class_id, value.signal_set_id)
    digest_path = grouping_signal_digest_path(tmp_path, value.class_id, value.signal_set_id)
    raw = json_path.read_bytes().replace(b"\n", b"\r\n")
    json_path.write_bytes(raw)
    digest_path.write_text(hashlib.sha256(raw).hexdigest() + "\n", encoding="ascii", newline="")
    with pytest.raises(GroupingSignalReadError):
        load_grouping_signal(tmp_path, value.class_id, value.signal_set_id)


def test_digest_mismatch_is_integrity_failure(tmp_path: Path) -> None:
    value = signal()
    write_grouping_signal(tmp_path, value)
    json_path = grouping_signal_path(tmp_path, value.class_id, value.signal_set_id)
    raw = bytearray(json_path.read_bytes())
    raw[-2] = 32 if raw[-2] != 32 else 9
    json_path.write_bytes(raw)
    with pytest.raises(GroupingSignalIntegrityError):
        load_grouping_signal(tmp_path, value.class_id, value.signal_set_id)


def test_path_identity_mismatch_is_integrity_failure(tmp_path: Path) -> None:
    value = signal()
    other = replace(value, signal_set_id="signal_002")
    path = grouping_signal_path(tmp_path, value.class_id, value.signal_set_id)
    digest_path = grouping_signal_digest_path(tmp_path, value.class_id, value.signal_set_id)
    path.parent.mkdir(parents=True)
    raw = grouping_signal_set_to_json_bytes(other)
    path.write_bytes(raw)
    digest_path.write_bytes((hashlib.sha256(raw).hexdigest() + "\n").encode())
    with pytest.raises(GroupingSignalIntegrityError):
        load_grouping_signal(tmp_path, value.class_id, value.signal_set_id)


def test_listing_is_class_scoped_sorted_and_strict(tmp_path: Path) -> None:
    assert list_grouping_signal_ids(tmp_path, "class_1") == ()
    for identifier in ("z_signal", "a_signal", "m_signal"):
        write_grouping_signal(tmp_path, replace(signal(), class_id="class_1", signal_set_id=identifier))
    write_grouping_signal(tmp_path, replace(signal(), class_id="class_2", signal_set_id="other"))
    assert list_grouping_signal_ids(tmp_path, "class_1") == ("a_signal", "m_signal", "z_signal")


def test_listing_rejects_unexpected_visible_entry(tmp_path: Path) -> None:
    write_grouping_signal(tmp_path, signal())
    class_dir = grouping_signal_class_dir(tmp_path, "english10_p2")
    (class_dir / "latest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(GroupingSignalIntegrityError):
        list_grouping_signal_ids(tmp_path, "english10_p2")


def test_listing_ignores_hidden_transient_entry(tmp_path: Path) -> None:
    value = signal()
    write_grouping_signal(tmp_path, value)
    class_dir = grouping_signal_class_dir(tmp_path, value.class_id)
    (class_dir / ".write.tmp").write_text("temporary", encoding="utf-8")
    assert list_grouping_signal_ids(tmp_path, value.class_id) == (value.signal_set_id,)


def test_listing_rejects_incomplete_pair(tmp_path: Path) -> None:
    value = signal()
    write_grouping_signal(tmp_path, value)
    grouping_signal_digest_path(tmp_path, value.class_id, value.signal_set_id).unlink()
    with pytest.raises(GroupingSignalIntegrityError):
        list_grouping_signal_ids(tmp_path, value.class_id)


@pytest.mark.skipif(os.name == "nt", reason="symlink creation may require privileges on Windows")
def test_storage_directory_symlink_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    exchange = tmp_path / "exchange"
    exchange.symlink_to(outside, target_is_directory=True)
    with pytest.raises(GroupingSignalIntegrityError):
        write_grouping_signal(tmp_path, signal())


def _replace_stored_json_with_matching_digest(
    tmp_path: Path, value: GroupingSignalSet, raw: bytes
) -> None:
    json_path = grouping_signal_path(tmp_path, value.class_id, value.signal_set_id)
    digest_path = grouping_signal_digest_path(
        tmp_path, value.class_id, value.signal_set_id
    )
    json_path.write_bytes(raw)
    digest_path.write_bytes(
        (hashlib.sha256(raw).hexdigest() + "\n").encode("ascii")
    )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda raw: raw.replace(
            b'  "schema_version": "1",',
            b'  "schema_version": "1",\n  "schema_version": "1",',
            1,
        ),
        lambda raw: raw.replace(b'  "schema_version": "1",', b' "schema_version": "1",', 1),
        lambda raw: raw.replace(b'"created_at": "2026-09-01T18:00:00+00:00"', b'"created_at": "2026-09-01T18:00:00Z"', 1),
        lambda raw: raw[:-1],
        lambda raw: raw + b"\n",
    ],
)
def test_rehashed_noncanonical_json_is_still_rejected(
    tmp_path: Path, mutator: object
) -> None:
    value = signal()
    write_grouping_signal(tmp_path, value)
    raw = mutator(grouping_signal_set_to_json_bytes(value))  # type: ignore[operator]
    _replace_stored_json_with_matching_digest(tmp_path, value, raw)
    with pytest.raises(GroupingSignalReadError):
        load_grouping_signal(tmp_path, value.class_id, value.signal_set_id)


def test_invalid_utf8_json_with_matching_digest_is_rejected(tmp_path: Path) -> None:
    value = signal()
    write_grouping_signal(tmp_path, value)
    raw = b"\xff\xfe\x00"
    _replace_stored_json_with_matching_digest(tmp_path, value, raw)
    with pytest.raises(GroupingSignalReadError):
        load_grouping_signal(tmp_path, value.class_id, value.signal_set_id)


def test_class_path_identity_mismatch_is_integrity_failure(tmp_path: Path) -> None:
    requested_class = "english10_p9"
    embedded = signal()
    class_dir = grouping_signal_class_dir(tmp_path, requested_class)
    class_dir.mkdir(parents=True)
    json_path = grouping_signal_path(tmp_path, requested_class, embedded.signal_set_id)
    digest_path = grouping_signal_digest_path(
        tmp_path, requested_class, embedded.signal_set_id
    )
    raw = grouping_signal_set_to_json_bytes(embedded)
    json_path.write_bytes(raw)
    digest_path.write_bytes(
        (hashlib.sha256(raw).hexdigest() + "\n").encode("ascii")
    )
    with pytest.raises(GroupingSignalIntegrityError):
        load_grouping_signal(tmp_path, requested_class, embedded.signal_set_id)


def test_json_target_directory_is_rejected(tmp_path: Path) -> None:
    value = signal()
    path = grouping_signal_path(tmp_path, value.class_id, value.signal_set_id)
    path.mkdir(parents=True)
    with pytest.raises(GroupingSignalIntegrityError):
        write_grouping_signal(tmp_path, value)


def test_class_storage_path_file_is_rejected(tmp_path: Path) -> None:
    class_dir = grouping_signal_class_dir(tmp_path, "english10_p2")
    class_dir.parent.mkdir(parents=True)
    class_dir.write_text("not a directory", encoding="utf-8")
    with pytest.raises(GroupingSignalIntegrityError):
        write_grouping_signal(tmp_path, signal())


def test_no_current_latest_or_active_aliases_are_created(tmp_path: Path) -> None:
    value = signal()
    write_grouping_signal(tmp_path, value)
    names = {
        path.name
        for path in grouping_signal_class_dir(tmp_path, value.class_id).iterdir()
    }
    assert names == {"signal_001.json", "signal_001.json.sha256"}
    assert not {"current.json", "latest.json", "active.json", "head.json"} & names


def test_failed_second_file_write_cleans_only_new_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pds_core.grouping_signal_storage as storage

    value = signal()
    original = storage._write_bytes_exclusively

    def fail_digest(path: Path, content: bytes) -> None:
        if path.name.endswith(".sha256"):
            raise storage.GroupingSignalWriteError("synthetic sidecar failure")
        original(path, content)

    monkeypatch.setattr(storage, "_write_bytes_exclusively", fail_digest)
    with pytest.raises(storage.GroupingSignalWriteError):
        storage.write_grouping_signal(tmp_path, value)
    assert not grouping_signal_path(
        tmp_path, value.class_id, value.signal_set_id
    ).exists()
    assert not grouping_signal_digest_path(
        tmp_path, value.class_id, value.signal_set_id
    ).exists()


def test_failed_verification_does_not_delete_changed_new_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pds_core.grouping_signal_storage as storage

    value = signal()
    original_load = storage.load_grouping_signal

    def corrupt_then_fail(root: Path, class_id: str, signal_set_id: str):
        json_path = grouping_signal_path(root, class_id, signal_set_id)
        json_path.write_bytes(b"externally changed")
        raise storage.GroupingSignalIntegrityError("synthetic verification failure")

    monkeypatch.setattr(storage, "load_grouping_signal", corrupt_then_fail)
    with pytest.raises(storage.GroupingSignalWriteError):
        storage.write_grouping_signal(tmp_path, value)
    json_path = grouping_signal_path(tmp_path, value.class_id, value.signal_set_id)
    assert json_path.read_bytes() == b"externally changed"
    monkeypatch.setattr(storage, "load_grouping_signal", original_load)


def test_teacher_authored_and_multi_dimension_digest_are_supported() -> None:
    teacher = signal(
        source=GroupingSignalSource("teacher_authored", None, None, None, None)
    )
    multi = signal(
        dimensions=(
            GroupingSignalDimension("writing", 3),
            GroupingSignalDimension("reading_analysis", 4),
        ),
        student_bands=(
            GroupingSignalStudentBand("student_002", "writing", 3),
            GroupingSignalStudentBand("student_001", "reading_analysis", 2),
        ),
    )
    for value in (teacher, multi):
        assert calculate_grouping_signal_digest(value) == hashlib.sha256(
            grouping_signal_set_to_json_bytes(value)
        ).hexdigest()


def test_csv_export_does_not_define_or_change_signal_digest() -> None:
    from pds_core.grouping_signal_csv import grouping_signal_set_to_csv

    value = signal()
    before = calculate_grouping_signal_digest(value)
    csv_text = grouping_signal_set_to_csv(value, "reading_analysis")
    assert csv_text
    assert calculate_grouping_signal_digest(value) == before
    assert before != hashlib.sha256(csv_text.encode("utf-8")).hexdigest()


def test_equivalent_in_memory_order_produces_same_digest_and_existing_write(
    tmp_path: Path,
) -> None:
    dimensions = (
        GroupingSignalDimension("writing", 3),
        GroupingSignalDimension("reading_analysis", 4),
    )
    bands = (
        GroupingSignalStudentBand("student_002", "writing", 3),
        GroupingSignalStudentBand("student_001", "reading_analysis", 2),
    )
    first = signal(dimensions=dimensions, student_bands=bands)
    second = signal(
        dimensions=tuple(reversed(dimensions)),
        student_bands=tuple(reversed(bands)),
    )
    assert calculate_grouping_signal_digest(first) == calculate_grouping_signal_digest(
        second
    )
    assert write_grouping_signal(tmp_path, first).disposition == "created"
    assert write_grouping_signal(tmp_path, second).disposition == "existing"
