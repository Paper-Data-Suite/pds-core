"""Shared active school-year workspace state helpers."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from pds_core.workspace import _normalize_workspace_root

_SCHOOL_YEAR_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<start>\d{4})-(?P<end>\d{4})$"
)


class SchoolYearStateError(ValueError):
    """Raised when workspace school-year state is invalid or cannot be updated."""


class SchoolYearValidationError(ValueError):
    """Raised when a school-year value is invalid."""


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise SchoolYearValidationError(f"{field_name} must be a string.")

    normalized = value.strip()
    if not normalized:
        raise SchoolYearValidationError(f"{field_name} must not be blank.")
    return normalized


def validate_school_year(value: object) -> str:
    """Validate a consecutive YYYY-YYYY school year and return it."""
    match = _SCHOOL_YEAR_PATTERN.fullmatch(_required_text(value, "school_year"))
    if match is None or int(match["end"]) != int(match["start"]) + 1:
        raise SchoolYearValidationError(
            "school_year must use consecutive years in YYYY-YYYY format."
        )
    return match.group(0)


@dataclass(frozen=True, slots=True)
class SchoolYearState:
    """Active school-year state for one Paper Data Suite workspace."""

    active_school_year: str
    opened_at: datetime
    closed_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "active_school_year",
            _validate_state_school_year(self.active_school_year),
        )
        object.__setattr__(
            self,
            "opened_at",
            _validate_aware_datetime(self.opened_at, "opened_at"),
        )
        if self.closed_at is not None:
            object.__setattr__(
                self,
                "closed_at",
                _validate_aware_datetime(self.closed_at, "closed_at"),
            )
        _validate_closed_at_order(self.opened_at, self.closed_at)


_STATE_KEYS = frozenset({"active_school_year", "opened_at", "closed_at"})


def _validate_state_school_year(value: object) -> str:
    try:
        return validate_school_year(value)
    except SchoolYearValidationError as error:
        raise SchoolYearStateError(str(error)) from error


def _validate_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise SchoolYearStateError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise SchoolYearStateError(f"{field_name} must be timezone-aware.")
    return value


def _validate_closed_at_order(
    opened_at: datetime,
    closed_at: datetime | None,
) -> None:
    if closed_at is not None and closed_at < opened_at:
        raise SchoolYearStateError("closed_at must not be earlier than opened_at.")


def _datetime_from_json(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise SchoolYearStateError(f"{field_name} must be an ISO datetime string.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise SchoolYearStateError(
            f"{field_name} must be a valid ISO datetime string."
        ) from error
    return _validate_aware_datetime(parsed, field_name)


def _state_to_dict(state: SchoolYearState) -> dict[str, object]:
    return {
        "active_school_year": state.active_school_year,
        "opened_at": state.opened_at.isoformat(),
        "closed_at": (
            None if state.closed_at is None else state.closed_at.isoformat()
        ),
    }


def _state_from_dict(data: Mapping[str, object]) -> SchoolYearState:
    unknown_keys = sorted(data.keys() - _STATE_KEYS)
    if unknown_keys:
        unknown = ", ".join(unknown_keys)
        raise SchoolYearStateError(
            f"school-year state contains unknown key(s): {unknown}."
        )

    missing_keys = sorted(_STATE_KEYS - data.keys())
    if missing_keys:
        missing = ", ".join(missing_keys)
        raise SchoolYearStateError(
            f"school-year state is missing required key(s): {missing}."
        )

    closed_at_value = data["closed_at"]
    if closed_at_value is None:
        closed_at = None
    else:
        closed_at = _datetime_from_json(closed_at_value, "closed_at")

    return SchoolYearState(
        active_school_year=data["active_school_year"],  # type: ignore[arg-type]
        opened_at=_datetime_from_json(data["opened_at"], "opened_at"),
        closed_at=closed_at,
    )


def _write_state(path: Path, state: SchoolYearState) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            _state_to_dict(state),
            indent=2,
            sort_keys=True,
        ) + "\n"
    except (OSError, TypeError, ValueError) as error:
        raise SchoolYearStateError(
            f"Could not prepare school-year state for {path}: {error}"
        ) from error

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, path)
        temporary_path = None
    except (OSError, UnicodeError) as error:
        raise SchoolYearStateError(
            f"Could not write school-year state {path}: {error}"
        ) from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def school_year_state_path(workspace_root: str | Path) -> Path:
    """Return the workspace path for active school-year state."""
    return _normalize_workspace_root(workspace_root) / "settings" / "school_year.json"


def load_school_year_state(workspace_root: str | Path) -> SchoolYearState | None:
    """Load school-year state, or return None if no state file exists."""
    path = school_year_state_path(workspace_root)
    if not path.exists():
        return None

    try:
        with path.open(encoding="utf-8") as state_file:
            data = json.load(state_file)
    except json.JSONDecodeError as error:
        raise SchoolYearStateError(
            f"Could not read school-year state {path}: invalid JSON: {error}"
        ) from error
    except (OSError, UnicodeError) as error:
        raise SchoolYearStateError(
            f"Could not read school-year state {path}: {error}"
        ) from error

    if not isinstance(data, Mapping):
        raise SchoolYearStateError("school-year state must contain a JSON object.")
    if any(not isinstance(key, str) for key in data):
        raise SchoolYearStateError("school-year state keys must be strings.")

    return _state_from_dict(cast(Mapping[str, object], data))


def get_active_school_year(workspace_root: str | Path) -> str | None:
    """Return the active school year, or None if no open school year exists."""
    state = load_school_year_state(workspace_root)
    if state is None or state.closed_at is not None:
        return None
    return state.active_school_year


def open_school_year(
    workspace_root: str | Path,
    school_year: str,
    *,
    opened_at: datetime,
    overwrite: bool = False,
) -> SchoolYearState:
    """Open a school year for the workspace."""
    path = school_year_state_path(workspace_root)
    state = SchoolYearState(
        active_school_year=school_year,
        opened_at=opened_at,
        closed_at=None,
    )
    existing_state = load_school_year_state(workspace_root)

    if existing_state is not None and existing_state.closed_at is None:
        if (
            existing_state.active_school_year == state.active_school_year
            and not overwrite
        ):
            return existing_state
        if not overwrite:
            raise SchoolYearStateError(
                "A different school year is already open; use overwrite=True "
                "to replace it."
            )

    _write_state(path, state)
    return state


def close_school_year(
    workspace_root: str | Path,
    *,
    closed_at: datetime,
) -> SchoolYearState:
    """Close the currently open school year."""
    path = school_year_state_path(workspace_root)
    existing_state = load_school_year_state(workspace_root)
    if existing_state is None:
        raise SchoolYearStateError("No school year is open for this workspace.")
    if existing_state.closed_at is not None:
        raise SchoolYearStateError("The school year is already closed.")

    closed_state = SchoolYearState(
        active_school_year=existing_state.active_school_year,
        opened_at=existing_state.opened_at,
        closed_at=closed_at,
    )
    _write_state(path, closed_state)
    return closed_state
