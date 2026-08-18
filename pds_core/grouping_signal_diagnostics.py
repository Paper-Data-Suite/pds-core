"""Workspace-aware identity diagnostics for neutral grouping-signal snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, TypeAlias

from pds_core.classes import list_class_folders, load_class_roster
from pds_core.grouping_signals import (
    GroupingSignalSet,
    GroupingSignalValidationError,
    validate_grouping_signal_set,
)
from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.rosters import Roster, RosterError

GroupingSignalDiagnosticCode: TypeAlias = Literal[
    "class_mismatch",
    "wrong_class_student",
    "unknown_student",
    "missing_student_signal",
]
GroupingSignalDiagnosticSeverity: TypeAlias = Literal["error", "warning"]

GROUPING_SIGNAL_DIAGNOSTIC_CODES: Final[frozenset[str]] = frozenset(
    {
        "class_mismatch",
        "wrong_class_student",
        "unknown_student",
        "missing_student_signal",
    }
)
GROUPING_SIGNAL_DIAGNOSTIC_SEVERITIES: Final[frozenset[str]] = frozenset(
    {"error", "warning"}
)


class GroupingSignalDiagnosticsError(RuntimeError):
    """Base error for workspace-aware grouping-signal diagnostics."""


class GroupingSignalDiagnosticsInputError(GroupingSignalDiagnosticsError):
    """Raised when the signal or explicit diagnostic context is invalid."""


class GroupingSignalDiagnosticsRosterError(GroupingSignalDiagnosticsError):
    """Raised when canonical roster state cannot support exact diagnostics."""


@dataclass(frozen=True, slots=True)
class GroupingSignalDiagnostic:
    """One structured workspace-aware grouping-signal finding."""

    code: GroupingSignalDiagnosticCode
    severity: GroupingSignalDiagnosticSeverity
    message: str
    student_id: str | None = None
    dimension_id: str | None = None
    other_class_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.code not in GROUPING_SIGNAL_DIAGNOSTIC_CODES:
            raise GroupingSignalDiagnosticsError(
                "diagnostic code must be one of: "
                + ", ".join(sorted(GROUPING_SIGNAL_DIAGNOSTIC_CODES))
                + "."
            )
        if self.severity not in GROUPING_SIGNAL_DIAGNOSTIC_SEVERITIES:
            raise GroupingSignalDiagnosticsError(
                "diagnostic severity must be one of: "
                + ", ".join(sorted(GROUPING_SIGNAL_DIAGNOSTIC_SEVERITIES))
                + "."
            )
        if not isinstance(self.message, str) or not self.message.strip():
            raise GroupingSignalDiagnosticsError(
                "diagnostic message must be a non-empty string."
            )

        student_id = self.student_id
        if student_id is not None:
            student_id = _diagnostic_identifier(student_id, "student_id")
            object.__setattr__(self, "student_id", student_id)
        dimension_id = self.dimension_id
        if dimension_id is not None:
            dimension_id = _diagnostic_identifier(dimension_id, "dimension_id")
            object.__setattr__(self, "dimension_id", dimension_id)

        other_class_ids = tuple(
            sorted(
                {
                    _diagnostic_identifier(class_id, "other_class_id")
                    for class_id in self.other_class_ids
                }
            )
        )
        object.__setattr__(self, "other_class_ids", other_class_ids)

        if self.code == "class_mismatch":
            if self.severity != "error":
                raise GroupingSignalDiagnosticsError(
                    "class_mismatch severity must be error."
                )
            if student_id is not None or dimension_id is not None or other_class_ids:
                raise GroupingSignalDiagnosticsError(
                    "class_mismatch must not carry student/dimension identity."
                )
            return

        if student_id is None or dimension_id is None:
            raise GroupingSignalDiagnosticsError(
                f"{self.code} requires student_id and dimension_id."
            )
        if self.code == "wrong_class_student":
            if self.severity != "error" or not other_class_ids:
                raise GroupingSignalDiagnosticsError(
                    "wrong_class_student requires error severity and other_class_ids."
                )
            return
        if other_class_ids:
            raise GroupingSignalDiagnosticsError(
                f"{self.code} must not carry other_class_ids."
            )
        expected_severity = (
            "warning" if self.code == "missing_student_signal" else "error"
        )
        if self.severity != expected_severity:
            raise GroupingSignalDiagnosticsError(
                f"{self.code} severity must be {expected_severity}."
            )


@dataclass(frozen=True, slots=True)
class GroupingSignalDimensionDiagnostics:
    """Neutral roster-coverage and matched-band counts for one signal dimension."""

    dimension_id: str
    band_count: int
    roster_student_count: int
    signal_entry_count: int
    matched_student_count: int
    missing_student_count: int
    unknown_student_count: int
    wrong_class_student_count: int
    band_counts: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "dimension_id",
            _diagnostic_identifier(self.dimension_id, "dimension_id"),
        )
        if isinstance(self.band_count, bool) or not isinstance(self.band_count, int):
            raise GroupingSignalDiagnosticsError("band_count must be an integer.")
        if self.band_count < 2:
            raise GroupingSignalDiagnosticsError("band_count must be at least 2.")

        count_fields = (
            "roster_student_count",
            "signal_entry_count",
            "matched_student_count",
            "missing_student_count",
            "unknown_student_count",
            "wrong_class_student_count",
        )
        for field_name in count_fields:
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise GroupingSignalDiagnosticsError(
                    f"{field_name} must be a non-negative integer."
                )

        if (
            self.matched_student_count + self.missing_student_count
            != self.roster_student_count
        ):
            raise GroupingSignalDiagnosticsError(
                "matched and missing counts must partition the target roster."
            )
        if (
            self.matched_student_count
            + self.unknown_student_count
            + self.wrong_class_student_count
            != self.signal_entry_count
        ):
            raise GroupingSignalDiagnosticsError(
                "matched, unknown, and wrong-class counts must partition "
                "signal entries."
            )

        band_counts = tuple(self.band_counts)
        expected_bands = tuple(range(1, self.band_count + 1))
        actual_bands = tuple(item[0] for item in band_counts)
        if actual_bands != expected_bands:
            raise GroupingSignalDiagnosticsError(
                "band_counts must contain each band from 1 through band_count in order."
            )
        total = 0
        for band, count in band_counts:
            if isinstance(band, bool) or not isinstance(band, int):
                raise GroupingSignalDiagnosticsError(
                    "band_counts band must be an integer."
                )
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise GroupingSignalDiagnosticsError(
                    "band_counts count must be a non-negative integer."
                )
            total += count
        if total != self.matched_student_count:
            raise GroupingSignalDiagnosticsError(
                "band_counts must total matched_student_count."
            )
        object.__setattr__(self, "band_counts", band_counts)


@dataclass(frozen=True, slots=True)
class GroupingSignalDiagnosticReport:
    """Deterministic read-only diagnostic report for one signal and target roster."""

    signal_set_id: str
    signal_class_id: str
    target_class_id: str
    roster_student_count: int
    findings: tuple[GroupingSignalDiagnostic, ...]
    dimensions: tuple[GroupingSignalDimensionDiagnostics, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "signal_set_id",
            _diagnostic_identifier(self.signal_set_id, "signal_set_id"),
        )
        object.__setattr__(
            self,
            "signal_class_id",
            _diagnostic_identifier(self.signal_class_id, "signal_class_id"),
        )
        object.__setattr__(
            self,
            "target_class_id",
            _diagnostic_identifier(self.target_class_id, "target_class_id"),
        )
        if (
            isinstance(self.roster_student_count, bool)
            or not isinstance(self.roster_student_count, int)
            or self.roster_student_count < 0
        ):
            raise GroupingSignalDiagnosticsError(
                "roster_student_count must be a non-negative integer."
            )
        findings = tuple(self.findings)
        dimensions = tuple(self.dimensions)
        if any(not isinstance(item, GroupingSignalDiagnostic) for item in findings):
            raise GroupingSignalDiagnosticsError(
                "findings must contain GroupingSignalDiagnostic values."
            )
        if any(
            not isinstance(item, GroupingSignalDimensionDiagnostics)
            for item in dimensions
        ):
            raise GroupingSignalDiagnosticsError(
                "dimensions must contain GroupingSignalDimensionDiagnostics values."
            )
        dimension_ids = tuple(item.dimension_id for item in dimensions)
        if (
            dimension_ids != tuple(sorted(dimension_ids))
            or len(set(dimension_ids)) != len(dimension_ids)
        ):
            raise GroupingSignalDiagnosticsError(
                "dimensions must be unique and ordered by dimension_id."
            )
        for dimension in dimensions:
            if dimension.roster_student_count != self.roster_student_count:
                raise GroupingSignalDiagnosticsError(
                    "dimension roster_student_count must match report "
                    "roster_student_count."
                )
        object.__setattr__(self, "findings", findings)
        object.__setattr__(self, "dimensions", dimensions)

    @property
    def has_errors(self) -> bool:
        """Return whether any diagnostic finding has error severity."""
        return any(item.severity == "error" for item in self.findings)

    @property
    def has_warnings(self) -> bool:
        """Return whether any diagnostic finding has warning severity."""
        return any(item.severity == "warning" for item in self.findings)

    @property
    def is_clean(self) -> bool:
        """Return whether the report contains no findings."""
        return not self.findings


def diagnose_grouping_signal(
    workspace_root: str | Path,
    signal: GroupingSignalSet | Mapping[str, object],
    *,
    expected_class_id: str | None = None,
) -> GroupingSignalDiagnosticReport:
    """Compare one structurally valid signal against exact canonical Core rosters."""
    try:
        candidate = validate_grouping_signal_set(signal)
    except GroupingSignalValidationError as error:
        raise GroupingSignalDiagnosticsInputError(
            f"grouping signal is structurally invalid: {error}"
        ) from error

    target_class_id = candidate.class_id
    if expected_class_id is not None:
        try:
            target_class_id = validate_identifier(
                expected_class_id, "expected_class_id"
            )
        except IdentifierValidationError as error:
            raise GroupingSignalDiagnosticsInputError(str(error)) from error

    target_roster = _load_diagnostic_roster(
        workspace_root,
        target_class_id,
        role="target",
    )
    target_student_ids = frozenset(
        student.student_id for student in target_roster.students
    )

    unmatched_ids = frozenset(
        entry.student_id
        for entry in candidate.student_bands
        if entry.student_id not in target_student_ids
    )
    other_class_ids_by_student = _find_other_class_memberships(
        workspace_root,
        target_class_id,
        unmatched_ids,
    )

    findings: list[GroupingSignalDiagnostic] = []
    if candidate.class_id != target_class_id:
        findings.append(
            GroupingSignalDiagnostic(
                code="class_mismatch",
                severity="error",
                message=(
                    f"signal class_id {candidate.class_id!r} does not match target "
                    f"class_id {target_class_id!r}."
                ),
            )
        )

    entries_by_dimension = {
        dimension.dimension_id: tuple(
            entry
            for entry in candidate.student_bands
            if entry.dimension_id == dimension.dimension_id
        )
        for dimension in candidate.dimensions
    }
    dimension_reports: list[GroupingSignalDimensionDiagnostics] = []

    for dimension in candidate.dimensions:
        entries = entries_by_dimension[dimension.dimension_id]
        matched_entries = tuple(
            entry for entry in entries if entry.student_id in target_student_ids
        )
        unmatched_entries = tuple(
            entry for entry in entries if entry.student_id not in target_student_ids
        )
        wrong_entries = tuple(
            entry
            for entry in unmatched_entries
            if other_class_ids_by_student.get(entry.student_id)
        )
        unknown_entries = tuple(
            entry
            for entry in unmatched_entries
            if not other_class_ids_by_student.get(entry.student_id)
        )
        matched_ids = frozenset(entry.student_id for entry in matched_entries)
        missing_ids = tuple(sorted(target_student_ids - matched_ids))

        for entry in sorted(wrong_entries, key=lambda item: item.student_id):
            other_class_ids = other_class_ids_by_student[entry.student_id]
            findings.append(
                GroupingSignalDiagnostic(
                    code="wrong_class_student",
                    severity="error",
                    message=(
                        f"student_id {entry.student_id!r} is absent from target class "
                        f"{target_class_id!r} but is present in other canonical class "
                        "roster(s): "
                        + ", ".join(other_class_ids)
                        + "."
                    ),
                    student_id=entry.student_id,
                    dimension_id=dimension.dimension_id,
                    other_class_ids=other_class_ids,
                )
            )
        for entry in sorted(unknown_entries, key=lambda item: item.student_id):
            findings.append(
                GroupingSignalDiagnostic(
                    code="unknown_student",
                    severity="error",
                    message=(
                        f"student_id {entry.student_id!r} is absent from target class "
                        f"{target_class_id!r} and every other canonical loaded roster."
                    ),
                    student_id=entry.student_id,
                    dimension_id=dimension.dimension_id,
                )
            )
        for student_id in missing_ids:
            findings.append(
                GroupingSignalDiagnostic(
                    code="missing_student_signal",
                    severity="warning",
                    message=(
                        f"student_id {student_id!r} has no signal entry for dimension "
                        f"{dimension.dimension_id!r} in target class "
                        f"{target_class_id!r}."
                    ),
                    student_id=student_id,
                    dimension_id=dimension.dimension_id,
                )
            )

        band_counts = tuple(
            (
                band,
                sum(1 for entry in matched_entries if entry.band == band),
            )
            for band in range(1, dimension.band_count + 1)
        )
        dimension_reports.append(
            GroupingSignalDimensionDiagnostics(
                dimension_id=dimension.dimension_id,
                band_count=dimension.band_count,
                roster_student_count=len(target_student_ids),
                signal_entry_count=len(entries),
                matched_student_count=len(matched_entries),
                missing_student_count=len(missing_ids),
                unknown_student_count=len(unknown_entries),
                wrong_class_student_count=len(wrong_entries),
                band_counts=band_counts,
            )
        )

    return GroupingSignalDiagnosticReport(
        signal_set_id=candidate.signal_set_id,
        signal_class_id=candidate.class_id,
        target_class_id=target_class_id,
        roster_student_count=len(target_student_ids),
        findings=tuple(findings),
        dimensions=tuple(dimension_reports),
    )


def _load_diagnostic_roster(
    workspace_root: str | Path,
    class_id: str,
    *,
    role: str,
) -> Roster:
    try:
        return load_class_roster(workspace_root, class_id)
    except RosterError as error:
        raise GroupingSignalDiagnosticsRosterError(
            f"Could not load {role} canonical roster for class_id {class_id!r}: {error}"
        ) from error
    except OSError as error:
        raise GroupingSignalDiagnosticsRosterError(
            f"Could not access {role} canonical roster for class_id "
            f"{class_id!r}: {error}"
        ) from error


def _find_other_class_memberships(
    workspace_root: str | Path,
    target_class_id: str,
    student_ids: frozenset[str],
) -> dict[str, tuple[str, ...]]:
    if not student_ids:
        return {}
    try:
        folders = list_class_folders(workspace_root, require_roster=True)
    except OSError as error:
        raise GroupingSignalDiagnosticsRosterError(
            f"Could not discover canonical class rosters: {error}"
        ) from error

    matches: dict[str, set[str]] = {student_id: set() for student_id in student_ids}
    for folder in folders:
        if folder.class_id == target_class_id:
            continue
        roster = _load_diagnostic_roster(
            workspace_root,
            folder.class_id,
            role="other-class",
        )
        roster_ids = frozenset(student.student_id for student in roster.students)
        for student_id in student_ids & roster_ids:
            matches[student_id].add(folder.class_id)
    return {
        student_id: tuple(sorted(class_ids))
        for student_id, class_ids in matches.items()
    }


def _diagnostic_identifier(value: str, field_name: str) -> str:
    try:
        return validate_identifier(value, field_name)
    except IdentifierValidationError as error:
        raise GroupingSignalDiagnosticsError(str(error)) from error
