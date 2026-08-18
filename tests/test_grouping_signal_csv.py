from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from pds_core.grouping_signal_csv import (
    GROUPING_SIGNAL_CSV_CONTRACT_NAME,
    GroupingSignalCsvDocument,
    GroupingSignalCsvError,
    GroupingSignalCsvRow,
    grouping_signal_csv_to_signal_set,
    grouping_signal_set_from_csv,
    grouping_signal_set_to_csv,
    grouping_signal_set_to_csv_bytes,
    parse_grouping_signal_csv,
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


def teacher_source(bound: bool = False) -> GroupingSignalSource:
    if not bound:
        return GroupingSignalSource("teacher_authored", None, None, None, None)
    return GroupingSignalSource("teacher_authored", None, "teacher_source_001", "sha256", DIGEST)


def module_source() -> GroupingSignalSource:
    return GroupingSignalSource("module_generated", "meridian", "snapshot_001", "sha256", DIGEST)


def signal(*, source: GroupingSignalSource | None = None, multi: bool = False) -> GroupingSignalSet:
    dimensions = [GroupingSignalDimension("reading_analysis", 4)]
    rows = [
        GroupingSignalStudentBand("student_002", "reading_analysis", 4),
        GroupingSignalStudentBand("student_001", "reading_analysis", 2),
    ]
    if multi:
        dimensions.append(GroupingSignalDimension("writing_claim_evidence", 3))
        rows.extend(
            [
                GroupingSignalStudentBand("student_002", "writing_claim_evidence", 1),
                GroupingSignalStudentBand("student_001", "writing_claim_evidence", 3),
            ]
        )
    return GroupingSignalSet(
        "1",
        "grouping_signal_set",
        "signal_001",
        "english10_p2",
        NOW,
        source or teacher_source(),
        tuple(dimensions),
        tuple(rows),
    )


def expected_complete_csv() -> str:
    return """# csv_contract=grouping_signal_csv_v1
# schema_version=1
# record_type=grouping_signal_set
# representation_scope=complete_signal
# signal_set_id=signal_001
# class_id=english10_p2
# created_at=2026-09-01T18:00:00+00:00
# source.kind=teacher_authored
# source.module_id=
# source.snapshot_id=
# source.snapshot_digest_algorithm=
# source.snapshot_digest=
# dimension_id=reading_analysis
# band_count=4
student_id,band
student_001,2
student_002,4
"""


def test_contract_name_and_golden_complete_export() -> None:
    assert GROUPING_SIGNAL_CSV_CONTRACT_NAME == "grouping_signal_csv_v1"
    assert grouping_signal_set_to_csv(signal(), "reading_analysis") == expected_complete_csv()


def test_export_bytes_are_utf8_lf_no_bom_and_one_final_lf() -> None:
    data = grouping_signal_set_to_csv_bytes(signal(), "reading_analysis")
    assert data == expected_complete_csv().encode("utf-8")
    assert not data.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in data
    assert data.endswith(b"\n") and not data.endswith(b"\n\n")


def test_export_module_generated_source() -> None:
    text = grouping_signal_set_to_csv(signal(source=module_source()), "reading_analysis")
    assert "# source.kind=module_generated\n" in text
    assert "# source.module_id=meridian\n" in text
    assert "# source.snapshot_id=snapshot_001\n" in text
    assert f"# source.snapshot_digest={DIGEST}\n" in text


def test_export_bound_teacher_source() -> None:
    text = grouping_signal_set_to_csv(signal(source=teacher_source(True)), "reading_analysis")
    assert "# source.snapshot_id=teacher_source_001\n" in text
    assert "# source.snapshot_digest_algorithm=sha256\n" in text


def test_multi_export_is_projection_and_selected_only() -> None:
    text = grouping_signal_set_to_csv(signal(multi=True), "writing_claim_evidence")
    assert "# representation_scope=dimension_projection\n" in text
    assert "# dimension_id=writing_claim_evidence\n" in text
    assert "# band_count=3\n" in text
    assert "student_001,3\nstudent_002,1\n" in text
    assert "student_001,2" not in text


def test_export_requires_declared_dimension() -> None:
    with pytest.raises(GroupingSignalCsvError, match="not declared"):
        grouping_signal_set_to_csv(signal(), "missing_dimension")


@pytest.mark.parametrize("dimension", ["", " bad", "bad/id"])
def test_export_rejects_invalid_selected_dimension(dimension: str) -> None:
    with pytest.raises(GroupingSignalCsvError):
        grouping_signal_set_to_csv(signal(), dimension)


def test_complete_round_trip_preserves_model_and_canonical_json() -> None:
    original = signal()
    restored = grouping_signal_set_from_csv(
        grouping_signal_set_to_csv(original, "reading_analysis")
    )
    assert restored == original
    assert grouping_signal_set_to_json_bytes(restored) == grouping_signal_set_to_json_bytes(original)


@pytest.mark.parametrize("source", [teacher_source(), teacher_source(True), module_source()])
def test_complete_round_trip_all_provenance(source: GroupingSignalSource) -> None:
    original = signal(source=source)
    assert grouping_signal_set_from_csv(
        grouping_signal_set_to_csv(original, "reading_analysis")
    ) == original


def test_parse_returns_typed_preview_and_requires_new_identity_flag() -> None:
    complete = parse_grouping_signal_csv(expected_complete_csv())
    assert isinstance(complete, GroupingSignalCsvDocument)
    assert complete.dimension.dimension_id == "reading_analysis"
    assert [row.student_id for row in complete.rows] == ["student_001", "student_002"]
    assert not complete.requires_new_identity
    projected = parse_grouping_signal_csv(
        grouping_signal_set_to_csv(signal(multi=True), "reading_analysis")
    )
    assert projected.requires_new_identity
    assert projected.signal_set_id == "signal_001"
    assert projected.created_at == NOW


def test_preview_dataclasses_are_frozen() -> None:
    document = parse_grouping_signal_csv(expected_complete_csv())
    with pytest.raises(FrozenInstanceError):
        document.class_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        document.rows[0].band = 3  # type: ignore[misc]


def test_projection_requires_explicit_new_id_and_time() -> None:
    document = parse_grouping_signal_csv(
        grouping_signal_set_to_csv(signal(multi=True), "reading_analysis")
    )
    with pytest.raises(GroupingSignalCsvError, match="requires a new"):
        grouping_signal_csv_to_signal_set(document)
    with pytest.raises(GroupingSignalCsvError, match="supplied together"):
        grouping_signal_csv_to_signal_set(document, new_signal_set_id="new_signal")
    with pytest.raises(GroupingSignalCsvError, match="supplied together"):
        grouping_signal_csv_to_signal_set(document, new_created_at=NOW)


def test_projection_rejects_reusing_source_id() -> None:
    document = parse_grouping_signal_csv(
        grouping_signal_set_to_csv(signal(multi=True), "reading_analysis")
    )
    with pytest.raises(GroupingSignalCsvError, match="must differ"):
        grouping_signal_csv_to_signal_set(
            document, new_signal_set_id="signal_001", new_created_at=NOW
        )


def test_projection_conversion_creates_one_dimension_new_snapshot() -> None:
    original = signal(multi=True, source=module_source())
    document = parse_grouping_signal_csv(
        grouping_signal_set_to_csv(original, "reading_analysis")
    )
    converted = grouping_signal_csv_to_signal_set(
        document,
        new_signal_set_id="reading_projection_001",
        new_created_at=NOW + timedelta(minutes=5),
    )
    assert converted.signal_set_id == "reading_projection_001"
    assert converted.created_at == NOW + timedelta(minutes=5)
    assert converted.dimensions == (GroupingSignalDimension("reading_analysis", 4),)
    assert {r.dimension_id for r in converted.student_bands} == {"reading_analysis"}
    assert converted.source == original.source


def test_complete_can_be_explicitly_reidentified() -> None:
    document = parse_grouping_signal_csv(expected_complete_csv())
    converted = grouping_signal_csv_to_signal_set(
        document,
        new_signal_set_id="edited_signal_002",
        new_created_at=NOW + timedelta(hours=1),
    )
    assert converted.signal_set_id == "edited_signal_002"
    assert converted.created_at == NOW + timedelta(hours=1)


def test_complete_reidentify_requires_pair_and_different_id() -> None:
    document = parse_grouping_signal_csv(expected_complete_csv())
    with pytest.raises(GroupingSignalCsvError, match="supplied together"):
        grouping_signal_csv_to_signal_set(document, new_signal_set_id="different")
    with pytest.raises(GroupingSignalCsvError, match="must differ"):
        grouping_signal_csv_to_signal_set(
            document, new_signal_set_id="signal_001", new_created_at=NOW
        )


def test_new_created_at_must_be_aware() -> None:
    document = parse_grouping_signal_csv(expected_complete_csv())
    with pytest.raises(GroupingSignalCsvError, match="timezone-aware"):
        grouping_signal_csv_to_signal_set(
            document,
            new_signal_set_id="different",
            new_created_at=datetime(2026, 9, 1),
        )


def test_nonutc_import_is_normalized() -> None:
    text = expected_complete_csv().replace(
        "2026-09-01T18:00:00+00:00", "2026-09-01T14:00:00-04:00"
    )
    doc = parse_grouping_signal_csv(text)
    assert doc.created_at == NOW
    restored = grouping_signal_csv_to_signal_set(doc)
    assert restored.created_at == NOW
    assert "# created_at=2026-09-01T18:00:00+00:00\n" in grouping_signal_set_to_csv(restored, "reading_analysis")


def test_import_accepts_crlf_and_bom_and_reexports_canonically() -> None:
    edited = "\ufeff" + expected_complete_csv().replace("\n", "\r\n")
    doc = parse_grouping_signal_csv(edited)
    assert grouping_signal_set_to_csv(grouping_signal_csv_to_signal_set(doc), "reading_analysis") == expected_complete_csv()
    bytes_doc = parse_grouping_signal_csv(b"\xef\xbb\xbf" + expected_complete_csv().replace("\n", "\r\n").encode())
    assert bytes_doc == doc


def test_import_accepts_metadata_reordering_after_discriminator() -> None:
    lines = expected_complete_csv().splitlines()
    changed = "\n".join([lines[0], lines[5], lines[2], lines[1], *lines[3:5], *lines[6:]]) + "\n"
    assert parse_grouping_signal_csv(changed).class_id == "english10_p2"


def test_import_accepts_row_reordering_and_normalizes_model() -> None:
    text = expected_complete_csv().replace(
        "student_001,2\nstudent_002,4\n", "student_002,4\nstudent_001,2\n"
    )
    model = grouping_signal_set_from_csv(text)
    assert [r.student_id for r in model.student_bands] == ["student_001", "student_002"]


def test_import_accepts_standard_csv_quoting() -> None:
    text = expected_complete_csv().replace("student_001,2", '"student_001","2"')
    assert parse_grouping_signal_csv(text).rows[0] == GroupingSignalCsvRow("student_001", 2)


def mutate_metadata(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    prefix = f"# {key}="
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = prefix + value
            return "\n".join(lines) + "\n"
    raise AssertionError(key)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("csv_contract", "wrong"),
        ("schema_version", "2"),
        ("record_type", "wrong"),
        ("representation_scope", "other"),
        ("signal_set_id", ""),
        ("signal_set_id", " bad"),
        ("class_id", "bad/id"),
        ("created_at", "not-time"),
        ("created_at", "2026-09-01T18:00:00"),
        ("dimension_id", "bad/id"),
        ("band_count", "1"),
        ("band_count", "2.0"),
        ("band_count", "+2"),
        ("band_count", " 2"),
        ("source.kind", "unknown"),
    ],
)
def test_invalid_metadata_values_fail(key: str, value: str) -> None:
    with pytest.raises(GroupingSignalCsvError):
        parse_grouping_signal_csv(mutate_metadata(expected_complete_csv(), key, value))


def test_module_source_requires_complete_provenance() -> None:
    text = mutate_metadata(expected_complete_csv(), "source.kind", "module_generated")
    text = mutate_metadata(text, "source.module_id", "meridian")
    with pytest.raises(GroupingSignalCsvError, match="source"):
        parse_grouping_signal_csv(text)


def test_uppercase_module_id_fails() -> None:
    text = grouping_signal_set_to_csv(signal(source=module_source()), "reading_analysis")
    with pytest.raises(GroupingSignalCsvError, match="lowercase"):
        parse_grouping_signal_csv(mutate_metadata(text, "source.module_id", "Meridian"))


def test_malformed_digest_fails() -> None:
    text = grouping_signal_set_to_csv(signal(source=module_source()), "reading_analysis")
    with pytest.raises(GroupingSignalCsvError, match="64 lowercase"):
        parse_grouping_signal_csv(mutate_metadata(text, "source.snapshot_digest", "ABC"))


def test_missing_metadata_fails() -> None:
    text = expected_complete_csv().replace("# class_id=english10_p2\n", "")
    with pytest.raises(GroupingSignalCsvError, match="missing"):
        parse_grouping_signal_csv(text)


def test_duplicate_metadata_fails() -> None:
    text = expected_complete_csv().replace(
        "# class_id=english10_p2\n", "# class_id=english10_p2\n# class_id=other\n"
    )
    with pytest.raises(GroupingSignalCsvError, match="duplicate metadata"):
        parse_grouping_signal_csv(text)


def test_unknown_metadata_fails() -> None:
    text = expected_complete_csv().replace(
        "# band_count=4\n", "# band_count=4\n# notes=hello\n"
    )
    with pytest.raises(GroupingSignalCsvError, match="unknown metadata"):
        parse_grouping_signal_csv(text)


def test_malformed_metadata_line_fails() -> None:
    text = expected_complete_csv().replace("# class_id=english10_p2", "# class_id english10_p2")
    with pytest.raises(GroupingSignalCsvError, match="key=value"):
        parse_grouping_signal_csv(text)


def test_first_line_must_be_discriminator() -> None:
    lines = expected_complete_csv().splitlines()
    changed = "\n".join([lines[1], lines[0], *lines[2:]]) + "\n"
    with pytest.raises(GroupingSignalCsvError, match="first line"):
        parse_grouping_signal_csv(changed)


@pytest.mark.parametrize(
    "header",
    [
        "name,band",
        "student_name,band",
        "student,band",
        "student_id,score",
        "student_id,grade",
        "student_id,band,notes",
        "band,student_id",
    ],
)
def test_invalid_headers_fail(header: str) -> None:
    with pytest.raises(GroupingSignalCsvError, match="header"):
        parse_grouping_signal_csv(expected_complete_csv().replace("student_id,band", header))


@pytest.mark.parametrize(
    "replacement",
    [
        ",2",
        "bad/id,2",
        " student_001,2",
        "student_001,",
        "student_001,0",
        "student_001,-1",
        "student_001,5",
        "student_001,2.0",
        "student_001,+2",
        "student_001, 2",
        "student_001,two",
        "student_001,2,notes",
        "student_001",
    ],
)
def test_invalid_rows_fail(replacement: str) -> None:
    text = expected_complete_csv().replace("student_001,2", replacement)
    with pytest.raises(GroupingSignalCsvError):
        parse_grouping_signal_csv(text)


def test_duplicate_student_id_fails_with_rows() -> None:
    text = expected_complete_csv().replace("student_002,4", "student_001,4")
    with pytest.raises(GroupingSignalCsvError, match="first occurrence"):
        parse_grouping_signal_csv(text)


def test_blank_data_record_fails() -> None:
    text = expected_complete_csv().replace("student_001,2\nstudent_002,4", "student_001,2\n\nstudent_002,4")
    with pytest.raises(GroupingSignalCsvError, match="blank"):
        parse_grouping_signal_csv(text)


def test_no_data_rows_fails() -> None:
    text = expected_complete_csv().split("student_id,band\n")[0] + "student_id,band\n"
    with pytest.raises(GroupingSignalCsvError, match="at least one"):
        parse_grouping_signal_csv(text)


def test_extra_comment_after_header_fails() -> None:
    text = expected_complete_csv().replace("student_001,2", "# note=bad\nstudent_001,2")
    with pytest.raises(GroupingSignalCsvError):
        parse_grouping_signal_csv(text)


def test_leading_zero_integer_is_accepted_and_export_normalizes() -> None:
    text = mutate_metadata(expected_complete_csv(), "band_count", "04").replace("student_001,2", "student_001,02")
    model = grouping_signal_set_from_csv(text)
    exported = grouping_signal_set_to_csv(model, "reading_analysis")
    assert "# band_count=4\n" in exported
    assert "student_001,2\n" in exported


def test_invalid_utf8_nul_and_lone_cr_fail() -> None:
    with pytest.raises(GroupingSignalCsvError, match="UTF-8"):
        parse_grouping_signal_csv(b"\xff")
    with pytest.raises(GroupingSignalCsvError, match="NUL"):
        parse_grouping_signal_csv(expected_complete_csv() + "\x00")
    with pytest.raises(GroupingSignalCsvError, match="LF or CRLF"):
        parse_grouping_signal_csv(expected_complete_csv().replace("\n", "\r"))


def test_wrong_input_types_fail() -> None:
    with pytest.raises(GroupingSignalCsvError):
        parse_grouping_signal_csv(123)  # type: ignore[arg-type]
    with pytest.raises(GroupingSignalCsvError):
        grouping_signal_csv_to_signal_set(object())  # type: ignore[arg-type]


def test_document_programmatic_validation_and_defensive_rows() -> None:
    rows = [GroupingSignalCsvRow("student_001", 2)]
    doc = GroupingSignalCsvDocument(
        "grouping_signal_csv_v1",
        "1",
        "grouping_signal_set",
        "complete_signal",
        "signal_001",
        "english10_p2",
        NOW,
        teacher_source(),
        GroupingSignalDimension("reading_analysis", 4),
        rows,  # type: ignore[arg-type]
    )
    rows.clear()
    assert len(doc.rows) == 1


def test_document_rejects_duplicate_rows_and_band_above_count() -> None:
    def document(rows: tuple[GroupingSignalCsvRow, ...]) -> GroupingSignalCsvDocument:
        return GroupingSignalCsvDocument(
            csv_contract="grouping_signal_csv_v1",
            schema_version="1",
            record_type="grouping_signal_set",
            representation_scope="complete_signal",
            signal_set_id="signal_001",
            class_id="english10_p2",
            created_at=NOW,
            source=teacher_source(),
            dimension=GroupingSignalDimension("reading_analysis", 3),
            rows=rows,
        )

    with pytest.raises(GroupingSignalCsvError, match="duplicate"):
        document(
            (
                GroupingSignalCsvRow("student_001", 1),
                GroupingSignalCsvRow("student_001", 2),
            )
        )
    with pytest.raises(GroupingSignalCsvError, match="between"):
        document((GroupingSignalCsvRow("student_001", 4),))


def test_export_does_not_include_privacy_extension_fields() -> None:
    text = grouping_signal_set_to_csv(signal(), "reading_analysis")
    for prohibited in ("student_name", "grade", "percentage", "score", "proficiency", "group_id", "strategy", "notes", "metadata"):
        assert prohibited not in text

def test_import_accepts_missing_final_newline_and_export_restores_it() -> None:
    text = expected_complete_csv().removesuffix("\n")
    model = grouping_signal_set_from_csv(text)
    assert grouping_signal_set_to_csv(model, "reading_analysis") == expected_complete_csv()


def test_malformed_csv_quote_fails() -> None:
    text = expected_complete_csv().replace("student_001,2", 'student_001,"2')
    with pytest.raises(GroupingSignalCsvError, match="malformed"):
        parse_grouping_signal_csv(text)
