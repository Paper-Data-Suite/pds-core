"""Validated, process-local Core teacher menu invocation and return contract.

These values are navigation hints and receipts, not an authorization token or
persistent identity. See docs/teacher_experience_contract_v1.md section 4.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pds_core.identifiers import validate_identifier

__all__ = (
    "TeacherWorkReference",
    "TeacherContextHint",
    "SharedTeacherMenuRequest",
    "TeacherMenuExit",
    "TeacherDurability",
    "TeacherChangeScope",
    "SharedTeacherMenuResult",
)


def _line(value: str, name: str, *, maximum: int = 128) -> str:
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    if not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be nonblank and at most {maximum} characters")
    if any(
        unicodedata.category(character).startswith("C")
        or unicodedata.category(character) in ("Zl", "Zp")
        for character in value
    ):
        raise ValueError(f"{name} must be a single, control-free line")
    return value


def _id(value: str, name: str, *, lowercase: bool = False) -> str:
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    if len(value) > 128:
        raise ValueError(f"{name} is too long")
    validated = validate_identifier(value, name)
    if lowercase and validated != validated.lower():
        raise ValueError(f"{name} must be lowercase")
    return validated


@dataclass(frozen=True, slots=True)
class TeacherWorkReference:
    """A caller-supplied non-student work hint; caller owns suitability checks."""

    module_id: str
    work_kind: str
    work_id: str

    def __post_init__(self) -> None:
        _id(self.module_id, "module_id", lowercase=True)
        _id(self.work_kind, "work_kind")
        _id(self.work_id, "work_id")


@dataclass(frozen=True, slots=True)
class TeacherContextHint:
    """Ephemeral, untrusted presentation hints; never persisted by this type."""

    workspace_root: Path | None = None
    class_id: str | None = None
    work: TeacherWorkReference | None = None
    display_label: str | None = None

    def __post_init__(self) -> None:
        if self.workspace_root is not None and not isinstance(
            self.workspace_root, Path
        ):
            raise TypeError("workspace_root must be a Path or None")
        if self.class_id is not None:
            _id(self.class_id, "class_id")
        if self.work is not None and not isinstance(self.work, TeacherWorkReference):
            raise TypeError("work must be a TeacherWorkReference or None")
        if self.display_label is not None:
            _line(self.display_label, "display_label")


@dataclass(frozen=True, slots=True)
class SharedTeacherMenuRequest:
    """An in-process request; return_token is opaque to Core."""

    caller_application: str
    return_token: str
    context: TeacherContextHint = field(default_factory=TeacherContextHint)

    def __post_init__(self) -> None:
        _line(self.caller_application, "caller_application")
        _line(self.return_token, "return_token")
        if not isinstance(self.context, TeacherContextHint):
            raise TypeError("context must be a TeacherContextHint")


class TeacherMenuExit(str, Enum):
    BACK = "back"
    MAIN_MENU = "main_menu"
    QUIT = "quit"
    CANCELLED = "cancelled"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class TeacherDurability(str, Enum):
    NO_CHANGE = "no_change"
    COMMITTED = "committed"
    PARTIAL = "partial"
    INDETERMINATE = "indeterminate"


class TeacherChangeScope(str, Enum):
    WORKSPACE = "workspace"
    SCHOOL_YEAR = "school_year"
    CLASS = "class"
    ROSTER = "roster"
    STANDARDS = "standards"
    NOTES = "notes"


@dataclass(frozen=True, slots=True)
class SharedTeacherMenuResult:
    """Navigation is separate from durable state. Never infer one from the other."""

    return_token: str
    exit: TeacherMenuExit
    durability: TeacherDurability
    change_scopes: frozenset[TeacherChangeScope]
    message: str

    def __post_init__(self) -> None:
        _line(self.return_token, "return_token")
        if type(self.exit) is not TeacherMenuExit:
            raise TypeError("exit must be a TeacherMenuExit")
        if type(self.durability) is not TeacherDurability:
            raise TypeError("durability must be a TeacherDurability")
        if type(self.change_scopes) is not frozenset or any(
            type(scope) is not TeacherChangeScope for scope in self.change_scopes
        ):
            raise TypeError("change_scopes must be a frozenset of TeacherChangeScope")
        _line(self.message, "message", maximum=512)
        if self.durability is TeacherDurability.NO_CHANGE and self.change_scopes:
            raise ValueError("NO_CHANGE requires empty change_scopes")
        if (
            self.durability is not TeacherDurability.NO_CHANGE
            and not self.change_scopes
        ):
            raise ValueError("durable or uncertain work requires change_scopes")
        if (
            self.exit is TeacherMenuExit.UNAVAILABLE
            and self.durability is not TeacherDurability.NO_CHANGE
        ):
            raise ValueError("UNAVAILABLE cannot report a committed change")
