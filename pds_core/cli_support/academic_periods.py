"""Non-interactive Academic Period CLI handlers."""

from __future__ import annotations

import argparse
from typing import TextIO, cast

from pds_core.academic_period_storage import academic_periods_dir
from pds_core.academic_periods import AcademicPeriodCalendar
from pds_core.cli_support.academic_registry import (
    _emit_changed_command,
    _emit_report,
    _emit_rows,
    _exit,
    _NamespaceChangedError,
    _namespace_changed,
    _namespace_guard,
    emit_academic_command_error,
)
from pds_core.registry_audit import (
    RegistryAuditOptions,
    _audit_academic_registry_observation,
    audit_academic_registry,
)
from pds_core.standards import StandardsLibrary


def handle_periods_list(args: argparse.Namespace, _library: StandardsLibrary, stdout: TextIO, stderr: TextIO) -> int:
    try:
        guarded = _namespace_guard(academic_periods_dir(args.workspace_root), 3)
        report, state = _audit_academic_registry_observation(
            args.workspace_root,
            options=RegistryAuditOptions(
                scopes=("academic_periods",), school_year=args.school_year
            ),
            producer_profiles=(),
        )
        if not report.ok:
            _emit_report(
                "academic periods list",
                report,
                args.format,
                stdout,
                ok=False,
            )
            return 1
        rows: list[dict[str, object]] = []
        grouped: dict[str, list[AcademicPeriodCalendar]] = {}
        for calendar in state.calendars:
            grouped.setdefault(calendar.school_year, []).append(calendar)
        if args.calendar_revision is not None and not grouped:
            raise FileNotFoundError("Academic Period revision does not exist.")
        for year, calendars in grouped.items():
            calendars.sort(key=lambda value: value.calendar_revision)
            current = calendars[-1].calendar_revision
            if args.calendar_revision is not None:
                selected = [
                    calendar for calendar in calendars
                    if calendar.calendar_revision == args.calendar_revision
                ]
                if not selected:
                    raise FileNotFoundError("Academic Period revision does not exist.")
            elif args.all_revisions:
                selected = calendars
            else:
                selected = calendars[-1:]
            for calendar in selected:
                revision = calendar.calendar_revision
                for period in calendar.periods:
                    if args.period_type not in (None, period.period_type) or args.lifecycle not in (None, period.lifecycle):
                        continue
                    if args.active_on is not None and not (period.start_date <= args.active_on <= period.end_date):
                        continue
                    rows.append({"school_year": year, "calendar_revision": revision, "current": revision == current, "sequence": period.sequence, "period_id": period.period_id, "period_type": period.period_type, "lifecycle": period.lifecycle, "start_date": period.start_date, "end_date": period.end_date, "parent_period_id": period.parent_period_id, "label": period.label})
        rows.sort(
            key=lambda row: (
                cast(str, row["school_year"]),
                cast(int, row["calendar_revision"]),
                cast(int, row["sequence"]),
                cast(str, row["period_id"]),
            )
        )
        rows = rows[args.offset:] if args.limit is None else rows[args.offset:args.offset + args.limit]
        if _namespace_changed(guarded, 3):
            return _emit_changed_command(
                args, "academic periods list", "academic_periods",
                "academic_periods.changed_during_audit", stdout, stderr,
            )
        _emit_rows("academic periods list", args.workspace_root, rows, args.format, stdout)
        return 0
    except _NamespaceChangedError:
        return _emit_changed_command(
            args, "academic periods list", "academic_periods",
            "academic_periods.changed_during_audit", stdout, stderr,
        )
    except Exception as error:
        return emit_academic_command_error(
            args,
            "academic periods list",
            error,
            stdout,
            stderr,
            domain="academic_periods",
            code=(
                "academic_periods.not_found"
                if isinstance(error, FileNotFoundError)
                else "academic_periods.read_failed"
            ),
        )


def handle_periods_validate(args: argparse.Namespace, _library: StandardsLibrary, stdout: TextIO, stderr: TextIO) -> int:
    try:
        report = audit_academic_registry(args.workspace_root, options=RegistryAuditOptions(scopes=("academic_periods",), school_year=args.school_year))
        exit_code = _exit(report, args.strict)
        _emit_report(
            "academic periods validate",
            report,
            args.format,
            stdout,
            ok=exit_code == 0,
        )
        return exit_code
    except Exception as error:
        return emit_academic_command_error(
            args,
            "academic periods validate",
            error,
            stdout,
            stderr,
            domain="academic_periods",
            code="academic_periods.read_failed",
        )
