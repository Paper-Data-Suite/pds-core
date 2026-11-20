"""Small, versioned records for workspace-native Notes & Tasks (Core #239).

This module is pure: no filesystem access, user configuration or menu behavior.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Literal, NoReturn, cast
from uuid import UUID, uuid4

from pds_core.identifiers import IdentifierValidationError, validate_identifier

NoteCategory = Literal["idea", "task", "reflection"]
SCHEMA_VERSION = 1
MAX_NOTE_TEXT_LENGTH = 16_384
MAX_SERIALIZED_BYTES = 32_768
_NOTE_ID = re.compile(r"^note_[0-9a-f]{32}$")
_UTC_SECOND = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
_FIELDS = frozenset(
    {
        "schema_version",
        "note_id",
        "category",
        "text",
        "revision",
        "created_at",
        "updated_at",
        "completed",
        "archived",
        "context",
    }
)
_CONTEXT_FIELDS = frozenset({"module_id", "class_id", "work_id"})


class NoteValidationError(ValueError):
    """A note record or serialized representation is malformed/unsupported."""


@dataclass(frozen=True, slots=True)
class NoteContext:
    """Optional non-student module/class/work identifiers, for display only."""

    module_id: str | None = None
    class_id: str | None = None
    work_id: str | None = None

    def __post_init__(self) -> None:
        for field in ("module_id", "class_id", "work_id"):
            value = getattr(self, field)
            if value is None:
                continue
            if type(value) is not str or len(value) > 128:
                raise NoteValidationError(f"Invalid Notes context {field}.")
            try:
                validate_identifier(value, field)
            except IdentifierValidationError as exc:
                raise NoteValidationError(f"Invalid Notes context {field}.") from exc
            if field == "module_id" and value != value.lower():
                raise NoteValidationError("Notes module_id must be lowercase.")


@dataclass(frozen=True, slots=True)
class NoteRecord:
    """One standalone record stored in the selected shared PDS workspace."""

    note_id: str
    category: NoteCategory
    text: str
    revision: int
    created_at: str
    updated_at: str
    completed: bool = False
    archived: bool = False
    context: NoteContext | None = None

    def __post_init__(self) -> None:
        validate_note(self)


def _timestamp(value: object, field: str) -> datetime:
    if type(value) is not str or _UTC_SECOND.fullmatch(value) is None:
        raise NoteValidationError(f"{field} must be a UTC timestamp with seconds.")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise NoteValidationError(f"{field} is not a valid timestamp.") from exc
    return result


def _validate_id(value: object) -> str:
    if type(value) is not str or _NOTE_ID.fullmatch(value) is None:
        raise NoteValidationError("note_id must be note_<32 lowercase hex digits>.")
    try:
        parsed = UUID(hex=value[5:])
    except ValueError as exc:
        raise NoteValidationError("Invalid note_id UUID.") from exc
    if parsed.version != 4 or parsed.hex != value[5:]:
        raise NoteValidationError("note_id must contain a canonical UUIDv4.")
    return value


def validate_note(note: NoteRecord) -> NoteRecord:
    """Validate a record without changing fields or touching the workspace."""
    if not isinstance(note, NoteRecord):
        raise NoteValidationError("Expected a NoteRecord.")
    _validate_id(note.note_id)
    if type(note.category) is not str or note.category not in (
        "idea",
        "task",
        "reflection",
    ):
        raise NoteValidationError("Invalid Notes category.")
    if type(note.text) is not str or not note.text.strip():
        raise NoteValidationError("Notes text must not be blank.")
    if len(note.text) > MAX_NOTE_TEXT_LENGTH or "\x00" in note.text:
        raise NoteValidationError("Notes text exceeds its limit or contains NUL.")
    try:
        note.text.encode("utf-8")
    except UnicodeError as exc:
        raise NoteValidationError("Notes text must be valid UTF-8.") from exc
    if type(note.revision) is not int or note.revision < 1:
        raise NoteValidationError("revision must be a positive integer.")
    if type(note.completed) is not bool or type(note.archived) is not bool:
        raise NoteValidationError("Notes flags must be booleans.")
    if note.category != "task" and note.completed:
        raise NoteValidationError("Only Tasks can be completed.")
    if note.context is not None and not isinstance(note.context, NoteContext):
        raise NoteValidationError("Invalid Notes context.")
    if _timestamp(note.updated_at, "updated_at") < _timestamp(
        note.created_at, "created_at"
    ):
        raise NoteValidationError("updated_at precedes created_at.")
    return note


def new_note(
    category: NoteCategory,
    text: str,
    *,
    context: NoteContext | None = None,
) -> NoteRecord:
    """Prepare an unsaved note. Persistence is owned by a separate service."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return NoteRecord(
        note_id=f"note_{uuid4().hex}",
        category=category,
        text=text,
        revision=1,
        created_at=stamp,
        updated_at=stamp,
        context=context,
    )


def encode_note(note: NoteRecord) -> str:
    """Produce deterministic UTF-8 JSON text with a trailing LF."""
    validate_note(note)
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "note_id": note.note_id,
        "category": note.category,
        "text": note.text,
        "revision": note.revision,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
        "completed": note.completed,
        "archived": note.archived,
        "context": asdict(note.context) if note.context is not None else None,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if len(raw.encode("utf-8")) > MAX_SERIALIZED_BYTES:
        raise NoteValidationError("Serialized note exceeds its file-size limit.")
    return raw


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            raise NoteValidationError("Duplicate Notes JSON key.")
        output[key] = value
    return output


def _invalid_constant(value: str) -> NoReturn:
    raise NoteValidationError("Non-finite Notes JSON value is not supported.")


def decode_note(raw: str) -> NoteRecord:
    """Strictly decode one JSON document; never infer absent/unknown fields."""
    if type(raw) is not str:
        raise NoteValidationError("Invalid Notes JSON input.")
    try:
        byte_length = len(raw.encode("utf-8"))
    except UnicodeError as exc:
        raise NoteValidationError("Notes JSON must be valid UTF-8.") from exc
    if byte_length > MAX_SERIALIZED_BYTES:
        raise NoteValidationError("Oversized Notes JSON.")
    try:
        data: object = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
    except (ValueError, UnicodeError) as exc:
        raise NoteValidationError("Invalid Notes JSON document.") from exc
    if not isinstance(data, dict) or set(data) != _FIELDS:
        raise NoteValidationError("Notes JSON fields do not match schema v1.")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise NoteValidationError("Unsupported Notes schema version.")
    item = cast(dict[str, object], data)
    context_data = item["context"]
    context: NoteContext | None = None
    if context_data is not None:
        if not isinstance(context_data, dict) or set(context_data) != _CONTEXT_FIELDS:
            raise NoteValidationError("Invalid Notes context fields.")
        context = NoteContext(
            module_id=cast(str | None, context_data["module_id"]),
            class_id=cast(str | None, context_data["class_id"]),
            work_id=cast(str | None, context_data["work_id"]),
        )
    return NoteRecord(
        note_id=cast(str, item["note_id"]),
        category=cast(NoteCategory, item["category"]),
        text=cast(str, item["text"]),
        revision=cast(int, item["revision"]),
        created_at=cast(str, item["created_at"]),
        updated_at=cast(str, item["updated_at"]),
        completed=cast(bool, item["completed"]),
        archived=cast(bool, item["archived"]),
        context=context,
    )
