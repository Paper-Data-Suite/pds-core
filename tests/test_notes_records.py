"""Pure, workspace-independent Notes schema tests for Core #239."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from pds_core.notes_records import (
    NoteContext,
    NoteValidationError,
    decode_note,
    encode_note,
    new_note,
)


def test_round_trip_with_unicode_newlines_and_context() -> None:
    note = new_note(
        "task",
        "Review Marp lesson — mañana\nUpdate rubric.",
        context=NoteContext(module_id="meridian", class_id="English12_P2"),
    )
    restored = decode_note(encode_note(note))
    assert restored == note
    assert note.note_id.startswith("note_")
    assert note.revision == 1
    assert note.completed is False


def test_round_trip_without_context_and_no_io() -> None:
    note = new_note("idea", "Discussion starter")
    assert decode_note(encode_note(note)) == note
    assert '"context": null' in encode_note(note)


@pytest.mark.parametrize("value", ["", " \n", "\x00hello", "x" * 16_385])
def test_rejects_bad_note_text(value: str) -> None:
    with pytest.raises(NoteValidationError):
        new_note("reflection", value)


def test_rejects_completed_non_task_and_invalid_flags() -> None:
    note = new_note("idea", "One sentence")
    with pytest.raises(NoteValidationError):
        replace(note, completed=True)
    with pytest.raises(NoteValidationError):
        replace(note, archived=cast(bool, 1))
    with pytest.raises(NoteValidationError):
        replace(note, revision=True)


def test_no_student_id_or_unbounded_extra_json_fields() -> None:
    note = new_note("reflection", "A thought")
    obj = json.loads(encode_note(note))
    obj["student_id"] = "not-allowed"
    with pytest.raises(NoteValidationError):
        decode_note(json.dumps(obj))


def test_duplicate_keys_and_future_versions_fail_closed() -> None:
    note = new_note("task", "A task")
    content = encode_note(note)
    with pytest.raises(NoteValidationError):
        decode_note(
            content.replace(
                '"archived": false,', '"archived": true, "archived": false,'
            )
        )
    obj = json.loads(content)
    obj["schema_version"] = 2
    with pytest.raises(NoteValidationError):
        decode_note(json.dumps(obj))


def test_invalid_context_and_filename_identity() -> None:
    with pytest.raises(NoteValidationError):
        NoteContext(module_id="Meridian")
    with pytest.raises(NoteValidationError):
        NoteContext(work_id="../bad")
    note = new_note("task", "A task")
    with pytest.raises(NoteValidationError):
        replace(note, note_id="note_" + "0" * 32)


def test_rejects_timestamp_reversal_and_oversized_utf8() -> None:
    note = new_note("idea", "A thought")
    with pytest.raises(NoteValidationError):
        replace(note, updated_at="2000-01-01T00:00:00Z")
    with pytest.raises(NoteValidationError):
        encode_note(new_note("idea", "📝" * 10_000))


def test_rejects_invalid_unicode_surrogates() -> None:
    with pytest.raises(NoteValidationError):
        new_note("idea", "bad \ud800")
    with pytest.raises(NoteValidationError):
        decode_note("{bad \ud800}")
