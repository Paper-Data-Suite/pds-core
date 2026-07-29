"""Non-interactive handlers for ``pds-core academic registry``."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path
import stat
from typing import Any, TextIO, cast

from pds_core import academic_catalog
from pds_core.academic_work_registrations import academic_work_registration_to_dict
from pds_core.class_metadata import load_class_metadata_for_class
from pds_core.identifiers import validate_identifier
from pds_core.publication_records import (
    publication_record_to_dict,
    publication_withdrawal_to_dict,
    validate_publication_record_series,
    validate_publication_withdrawal_relationship,
)
from pds_core.publication_storage import resolve_publication_manifest_path
from pds_core.registry_audit import (
    AuditDomain,
    RegistryAuditError,
    RegistryAuditFinding,
    RegistryAuditOptions,
    RegistryAuditReport,
    _audit_academic_registry_observation,
    _manifest_lexical_fingerprint,
    audit_academic_registry,
    clear_registry_lock,
    get_registry_lock,
    get_academic_registry_status,
    list_registry_locks,
)
from pds_core.registry_paths import (
    academic_catalog_path,
    academic_work_registration_dir,
    academic_work_registration_revision_path,
    academic_work_registrations_dir,
    publication_record_path,
    publication_withdrawal_path,
    publication_withdrawals_dir,
    publications_dir,
)
from pds_core.routing_models import ModuleWorkRef
from pds_core.standards import StandardsLibrary


def _native(value: object) -> object:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _native(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _native(item) for key, item in value.items()}
    if isinstance(value, (frozenset, set)):
        return sorted((_native(item) for item in value), key=str)
    if isinstance(value, (tuple, list)):
        return [_native(item) for item in value]
    return value


def _emit_json(command: str, workspace: Path, ok: bool, data: object, findings: object, stdout: TextIO) -> None:
    payload = {"schema_version": "1", "command": command, "workspace": workspace.as_posix(), "ok": ok, "data": _native(data), "findings": _native(findings)}
    print(json.dumps(payload, sort_keys=True, allow_nan=False, ensure_ascii=False), file=stdout)


class AcademicCommandUsageError(ValueError):
    """A post-parse academic command usage error requiring exit 2."""


def emit_academic_command_error(
    args: argparse.Namespace,
    command: str,
    error: BaseException,
    stdout: TextIO,
    stderr: TextIO,
    *,
    domain: AuditDomain = "workspace",
    code: str = "workspace.command_failed",
) -> int:
    """Emit one stable handled-error result in the selected output format."""
    exit_code = 2 if isinstance(error, AcademicCommandUsageError) else 1
    message = " ".join(str(error).splitlines()) or "Command failed."
    finding = RegistryAuditFinding(
        severity="error",
        domain=domain,
        code=code,
        message=message,
    )
    if getattr(args, "format", "text") == "json":
        _emit_json(command, args.workspace_root, False, {}, (finding,), stdout)
    else:
        print(f"Error: {message}", file=stderr)
    return exit_code


def _status_data(status: object) -> dict[str, object]:
    value = cast(Any, status)
    return {
        "workspace_root": value.workspace_root,
        "counts": value.counts,
        "canonical_valid": value.canonical_valid,
        "manifests_valid": value.manifests_valid,
        "contracts_compatible": value.contracts_compatible,
        "catalog_path": value.catalog_path,
        "catalog_state": value.catalog_state,
        "catalog_built_at": value.catalog_built_at,
        "catalog_source_snapshot_sha256": value.catalog_source_snapshot_sha256,
        "catalog_sources_current": value.catalog_sources_current,
        "lock_count": value.lock_count,
        "temporary_artifact_count": value.temporary_artifact_count,
    }


def _emit_report(
    command: str,
    report: RegistryAuditReport,
    output_format: str,
    stdout: TextIO,
    *,
    ok: bool | None = None,
) -> None:
    command_ok = report.ok if ok is None else ok
    if output_format == "json":
        _emit_json(command, report.workspace_root, command_ok, {"canonical_valid": report.canonical_valid, "manifests_valid": report.manifests_valid, "contracts_compatible": report.contracts_compatible, "catalog_ready": report.catalog_ready, "counts": report.counts}, report.findings, stdout)
        return
    print(f"Workspace: {report.workspace_root}", file=stdout)
    print(f"Canonical valid: {'yes' if report.canonical_valid else 'no'}", file=stdout)
    print(f"Manifest valid: {_display(report.manifests_valid)}", file=stdout)
    print(f"Contracts compatible: {_display(report.contracts_compatible)}", file=stdout)
    print(f"Catalog ready: {_display(report.catalog_ready)}", file=stdout)
    print(f"Findings: {report.counts.error_findings} error, {report.counts.warning_findings} warning, {report.counts.info_findings} info", file=stdout)
    for severity in ("error", "warning", "info"):
        rows = [finding for finding in report.findings if finding.severity == severity]
        if rows:
            print(f"\n{severity.upper()}", file=stdout)
            for finding in rows:
                location = finding.path or (", ".join(f"{key}={value}" for key, value in finding.identity) or "-")
                print(f"{finding.code} | {location} | {finding.message} | repair={finding.repair}", file=stdout)


def _display(value: object) -> str:
    if value is None:
        return "not checked"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _exit(report: RegistryAuditReport, strict: bool) -> int:
    return 1 if not report.ok or (strict and report.counts.warning_findings) else 0


def handle_registry_status(args: argparse.Namespace, _library: StandardsLibrary, stdout: TextIO, stderr: TextIO) -> int:
    try:
        status = get_academic_registry_status(args.workspace_root, verify_manifests=args.verify_manifests)
        exit_code = 1 if not status.ok or (args.strict and status.counts.warning_findings) else 0
        if args.format == "json":
            _emit_json("academic registry status", status.workspace_root, exit_code == 0, _status_data(status), status.findings, stdout)
        else:
            print(f"Workspace: {status.workspace_root}", file=stdout)
            print(f"Canonical status: {'valid' if status.canonical_valid else 'invalid'}", file=stdout)
            print(f"Academic Periods: {status.counts.school_years} school years, {status.counts.calendar_revisions} revisions, {status.counts.periods} periods", file=stdout)
            print(f"Registrations: {status.counts.registration_works} works, {status.counts.registration_revisions} revisions", file=stdout)
            print(f"Publications: {status.counts.publication_records} records, {status.counts.publication_series} series", file=stdout)
            print(f"Withdrawals: {status.counts.withdrawals}", file=stdout)
            print(f"Manifest status: {_display(status.manifests_valid)}", file=stdout)
            print(f"Producer compatibility: {_display(status.contracts_compatible)}", file=stdout)
            print(f"Catalog: {status.catalog_state} ({status.catalog_path})", file=stdout)
            print(f"Catalog build time: {_display(status.catalog_built_at)}", file=stdout)
            print(f"Catalog source snapshot: {_display(status.catalog_source_snapshot_sha256)}", file=stdout)
            print(f"Catalog sources current: {_display(status.catalog_sources_current)}", file=stdout)
            print(f"Known locks: {status.lock_count}", file=stdout)
            print(f"Temporary artifacts: {status.temporary_artifact_count}", file=stdout)
            print(f"Findings: {status.counts.error_findings} error, {status.counts.warning_findings} warning, {status.counts.info_findings} info", file=stdout)
            recommendation = "Run: pds-core academic registry validate" if status.canonical_valid else "Review canonical validation findings"
            if status.catalog_state != "ready" and status.canonical_valid:
                recommendation = "Run: pds-core academic registry rebuild-catalog"
            print(f"Recommended next command: {recommendation}", file=stdout)
        return exit_code
    except RegistryAuditError as error:
        return emit_academic_command_error(
            args, "academic registry status", error, stdout, stderr
        )


def handle_registry_validate(args: argparse.Namespace, _library: StandardsLibrary, stdout: TextIO, stderr: TextIO) -> int:
    scopes = tuple(value.replace("-", "_") for value in args.scope) if args.scope else RegistryAuditOptions().scopes
    try:
        report = audit_academic_registry(args.workspace_root, options=RegistryAuditOptions(scopes=scopes, school_year=args.school_year, class_id=args.class_id, module_id=args.module_id, work_id=args.work_id, publication_id=args.publication_id, require_catalog=args.require_catalog, require_producer_profiles=args.require_producer_profiles, discover_installed_producer_profiles=not args.no_installed_producer_profiles))
        exit_code = _exit(report, args.strict)
        _emit_report(
            "academic registry validate",
            report,
            args.format,
            stdout,
            ok=exit_code == 0,
        )
        return exit_code
    except RegistryAuditError as error:
        return emit_academic_command_error(
            args, "academic registry validate", error, stdout, stderr
        )


def _slice(rows: list[dict[str, object]], args: argparse.Namespace) -> list[dict[str, object]]:
    start = args.offset
    return rows[start:] if args.limit is None else rows[start:start + args.limit]


def _class_school_year(root: Path, class_id: str) -> str | None:
    try:
        return load_class_metadata_for_class(root, class_id).school_year
    except (FileNotFoundError, ValueError):
        return None


def _bounded_registration_work_refs(root: Path) -> tuple[ModuleWorkRef, ...]:
    """Enumerate canonical work identities without requiring a valid pointer."""
    result: list[ModuleWorkRef] = []
    base = academic_work_registrations_dir(root)
    try:
        base_status = base.lstat()
    except FileNotFoundError:
        return ()
    if not stat.S_ISDIR(base_status.st_mode) or base.is_symlink():
        raise ValueError("Registration root is not a nonsymlink directory.")
    for class_dir in sorted(base.iterdir(), key=lambda value: value.name):
        if class_dir.name.startswith("."):
            continue
        class_id = validate_identifier(class_dir.name, "class_id")
        if not stat.S_ISDIR(class_dir.lstat().st_mode) or class_dir.is_symlink():
            raise ValueError("Registration class entry is not a regular directory.")
        for module_dir in sorted(class_dir.iterdir(), key=lambda value: value.name):
            if module_dir.name.startswith("."):
                continue
            module_id = validate_identifier(module_dir.name, "module_id")
            if (
                module_id != module_id.lower()
                or not stat.S_ISDIR(module_dir.lstat().st_mode)
                or module_dir.is_symlink()
            ):
                raise ValueError("Registration module entry is invalid.")
            for work_dir in sorted(module_dir.iterdir(), key=lambda value: value.name):
                if work_dir.name.startswith("."):
                    continue
                work_id = validate_identifier(work_dir.name, "work_id")
                if (
                    not stat.S_ISDIR(work_dir.lstat().st_mode)
                    or work_dir.is_symlink()
                ):
                    raise ValueError("Registration work entry is invalid.")
                result.append(ModuleWorkRef(module_id, class_id, work_id))
    return tuple(result)


def _emit_rows(command: str, root: Path, rows: list[dict[str, object]], output_format: str, stdout: TextIO) -> None:
    if output_format == "json":
        _emit_json(command, root, True, {"rows": rows, "count": len(rows)}, (), stdout)
    elif not rows:
        print("No matching records.", file=stdout)
    else:
        for row in rows:
            print(" | ".join(f"{key}={_display(value)}" for key, value in row.items()), file=stdout)


def _emit_detail_text(data: object, stdout: TextIO) -> None:
    native = _native(data)
    if not isinstance(native, dict):
        print(_display(native), file=stdout)
        return
    for key, value in native.items():
        if isinstance(value, (dict, list)):
            rendered = json.dumps(
                value, sort_keys=True, ensure_ascii=False, allow_nan=False
            )
        else:
            rendered = _display(value)
        print(f"{key}: {rendered}", file=stdout)


def handle_registry_list(args: argparse.Namespace, _library: StandardsLibrary, stdout: TextIO, stderr: TextIO) -> int:
    root = args.workspace_root
    try:
        rows: list[dict[str, object]] = []
        guarded: dict[Path, _NamespaceFingerprint] | None = None
        guard_depth = 0
        changed_domain: AuditDomain | None = None
        changed_code = ""
        if args.entity == "registrations":
            guard_depth = 5
            guarded = _namespace_guard(academic_work_registrations_dir(root), guard_depth)
            integrity, state = _audit_academic_registry_observation(
                root,
                options=RegistryAuditOptions(
                    scopes=("registrations",),
                    school_year=args.school_year,
                    class_id=args.class_id,
                    module_id=args.module_id,
                    work_id=args.work_id,
                ),
                producer_profiles=(),
            )
            if not integrity.ok:
                _emit_report(
                    "academic registry list registrations",
                    integrity,
                    args.format,
                    stdout,
                )
                return 1
            grouped: dict[ModuleWorkRef, list[Any]] = {}
            for registration in state.registrations:
                grouped.setdefault(registration.work, []).append(registration)
            for work, history in grouped.items():
                history.sort(key=lambda value: value.registration_revision)
                school_year = _class_school_year(root, work.class_id)
                selected_history = history if args.all_revisions else history[-1:]
                for record in selected_history:
                    if not _registration_matches(record, args):
                        continue
                    rows.append({"school_year": school_year, "class_id": record.work.class_id, "module_id": record.work.module_id, "work_id": record.work.work_id, "revision": record.registration_revision, "current": history[-1].registration_revision == record.registration_revision, "title": record.title, "work_kind": record.work_kind, "academic_intent": record.academic_intent, "lifecycle": record.lifecycle, "producer_contract_version": record.producer_contract_version, "updated_at": record.updated_at})
            changed_domain = "registrations"
            changed_code = "registrations.changed_during_audit"
        elif args.entity == "publications":
            guard_depth = 1
            publication_guard = _namespace_guard(publications_dir(root), guard_depth)
            withdrawal_guard = _namespace_guard(publication_withdrawals_dir(root), guard_depth)
            guarded = {**publication_guard, **withdrawal_guard}
            integrity, state = _audit_academic_registry_observation(
                root,
                options=RegistryAuditOptions(
                    scopes=("publications",), school_year=args.school_year,
                    class_id=args.class_id, module_id=args.module_id,
                    work_id=args.work_id,
                ),
                producer_profiles=(),
            )
            if not integrity.ok:
                _emit_report("academic registry list publications", integrity, args.format, stdout)
                return 1
            publication_records = list(state.publications)
            series: dict[tuple[object, ...], list[Any]] = {}
            for publication_entry in publication_records:
                series.setdefault(
                    (
                        publication_entry.work,
                        publication_entry.publication_kind,
                        publication_entry.record_set_id,
                    ),
                    [],
                ).append(publication_entry)
            for values in series.values():
                validate_publication_record_series(values)
            publication_by_id = {
                item.publication_id: item for item in publication_records
            }
            withdrawals_by_id = {}
            for item in state.withdrawals:
                publication = publication_by_id.get(item.publication_id)
                if publication is None:
                    raise ValueError(
                        f"Withdrawal {item.publication_id} has no Publication Record."
                    )
                validate_publication_withdrawal_relationship(publication, item)
                withdrawals_by_id[item.publication_id] = item
            predecessors = {item.supersedes_publication_id for item in publication_records if item.supersedes_publication_id}
            for publication_entry in publication_records:
                is_head = publication_entry.publication_id not in predecessors
                is_withdrawn = publication_entry.publication_id in withdrawals_by_id
                is_historical = not is_head
                is_current_selectable = is_head and not is_withdrawn
                school_year = _class_school_year(root, publication_entry.work.class_id)
                if not _publication_matches(
                    publication_entry,
                    is_head=is_head,
                    is_withdrawn=is_withdrawn,
                    is_historical=is_historical,
                    is_current_selectable=is_current_selectable,
                    args=args,
                ) or args.school_year not in (None, school_year):
                    continue
                rows.append({"publication_id": publication_entry.publication_id, "school_year": school_year, "class_id": publication_entry.work.class_id, "module_id": publication_entry.work.module_id, "work_id": publication_entry.work.work_id, "publication_kind": publication_entry.publication_kind, "record_set_id": publication_entry.record_set_id, "record_set_revision": publication_entry.record_set_revision, "manifest_contract_version": publication_entry.manifest_contract_version, "published_at": publication_entry.published_at, "is_series_head": is_head, "is_historical": is_historical, "is_withdrawn": is_withdrawn, "is_current_selectable": is_current_selectable, "capabilities": publication_entry.capabilities})
            changed_domain = "publications"
            changed_code = "publications.changed_during_audit"
        elif args.entity == "withdrawals":
            guard_depth = 1
            guarded = {
                **_namespace_guard(publications_dir(root), guard_depth),
                **_namespace_guard(publication_withdrawals_dir(root), guard_depth),
            }
            integrity, state = _audit_academic_registry_observation(
                root,
                options=RegistryAuditOptions(
                    scopes=("publications",), school_year=args.school_year,
                    class_id=args.class_id, module_id=args.module_id,
                    work_id=args.work_id,
                ),
                producer_profiles=(),
            )
            if not integrity.ok:
                _emit_report("academic registry list withdrawals", integrity, args.format, stdout)
                return 1
            publication_by_id = {
                item.publication_id: item for item in state.publications
            }
            for item in state.withdrawals:
                publication = publication_by_id.get(item.publication_id)
                if publication is None:
                    raise ValueError("Withdrawal has no selected Publication Record.")
                validate_publication_withdrawal_relationship(publication, item)
                school_year = _class_school_year(root, publication.work.class_id)
                if args.school_year not in (None, school_year):
                    continue
                if (args.publication_kind is None or publication.publication_kind == args.publication_kind) and _time_matches(publication.published_at, args):
                    rows.append({"publication_id": item.publication_id, "school_year": school_year, "class_id": publication.work.class_id, "module_id": publication.work.module_id, "work_id": publication.work.work_id, "publication_kind": publication.publication_kind, "published_at": publication.published_at, "withdrawn_at": item.withdrawn_at})
            changed_domain = "publications"
            changed_code = "publications.changed_during_audit"
        else:
            rows = [asdict(item) for item in list_registry_locks(root)]
        if args.entity == "registrations":
            rows.sort(
                key=lambda row: (
                    row["school_year"] is None,
                    cast(str | None, row["school_year"]) or "",
                    cast(str, row["class_id"]),
                    cast(str, row["module_id"]),
                    cast(str, row["work_id"]),
                    cast(int, row["revision"]),
                )
            )
        elif args.entity == "publications":
            rows.sort(
                key=lambda row: (
                    -cast(datetime, row["published_at"]).timestamp(),
                    cast(str, row["publication_id"]),
                )
            )
        elif args.entity == "withdrawals":
            rows.sort(
                key=lambda row: (
                    -cast(datetime, row["withdrawn_at"]).timestamp(),
                    cast(str, row["publication_id"]),
                )
            )
        else:
            rows.sort(
                key=lambda row: (
                    cast(str, row["lock_kind"]),
                    cast(str, row["lock_id"]),
                )
            )
        if hasattr(args, "offset"):
            rows = _slice(rows, args)
        if guarded is not None and _namespace_changed(guarded, guard_depth):
            assert changed_domain is not None
            return _emit_changed_command(
                args, f"academic registry list {args.entity}", changed_domain,
                changed_code, stdout, stderr,
            )
        _emit_rows(f"academic registry list {args.entity}", root, rows, args.format, stdout)
        return 0
    except _NamespaceChangedError:
        domain: AuditDomain = (
            "registrations" if args.entity == "registrations" else
            "publications" if args.entity in {"publications", "withdrawals"} else
            "locks"
        )
        return _emit_changed_command(
            args, f"academic registry list {args.entity}", domain,
            f"{domain}.changed_during_audit", stdout, stderr,
        )
    except Exception as error:
        return emit_academic_command_error(
            args,
            f"academic registry list {args.entity}",
            error,
            stdout,
            stderr,
            domain="locks" if args.entity == "locks" else (
                "registrations" if args.entity == "registrations" else "publications"
            ),
            code=(
                "locks.unreadable" if args.entity == "locks" else
                "registrations.revision_invalid" if args.entity == "registrations" else
                "publications.record_invalid"
            ),
        )


def _basic_work_matches(work: ModuleWorkRef, args: argparse.Namespace) -> bool:
    return args.class_id in (None, work.class_id) and args.module_id in (None, work.module_id) and args.work_id in (None, work.work_id)


def _show_domain(entity: str) -> AuditDomain:
    if entity == "registration":
        return "registrations"
    if entity in {"publication", "withdrawal"}:
        return "publications"
    if entity == "catalog":
        return "catalog"
    return "locks"


def _registration_matches(record: Any, args: argparse.Namespace) -> bool:
    return _basic_work_matches(record.work, args) and args.producer_contract_version in (None, record.producer_contract_version) and args.academic_intent in (None, record.academic_intent) and args.lifecycle in (None, record.lifecycle)


def _time_matches(value: datetime, args: argparse.Namespace) -> bool:
    return (args.published_at_or_after is None or value >= args.published_at_or_after) and (args.published_before is None or value < args.published_before)


def _publication_matches(
    record: Any,
    *,
    is_head: bool,
    is_withdrawn: bool,
    is_historical: bool,
    is_current_selectable: bool,
    args: argparse.Namespace,
) -> bool:
    state_matches = {
        "current": is_current_selectable,
        "series-heads": is_head,
        "historical": is_historical,
        "withdrawn": is_withdrawn,
        "all": True,
    }
    source_version = None if record.source_record is None else record.source_record.contract_version
    return _basic_work_matches(record.work, args) and args.publication_kind in (None, record.publication_kind) and args.manifest_contract_version in (None, record.manifest_contract_version) and args.source_contract_version in (None, source_version) and args.record_set_id in (None, record.record_set_id) and (args.capability is None or args.capability in record.capabilities) and state_matches[args.state] and _time_matches(record.published_at, args)


_ShowFingerprint = tuple[int, int, int, int, int, int, str] | None
_NamespaceFingerprint = tuple[str, int, int, int, int, int, int, str | None] | None


class _NamespaceChangedError(RuntimeError):
    """A canonical namespace changed while its initial guard was captured."""


def _namespace_guard(path: Path, max_depth: int) -> dict[Path, _NamespaceFingerprint]:
    """Fingerprint bounded membership without following directory symlinks."""
    result: dict[Path, _NamespaceFingerprint] = {}

    def visit(candidate: Path, depth: int, *, expected: bool = False) -> None:
        try:
            before = candidate.lstat()
        except FileNotFoundError:
            if expected:
                raise _NamespaceChangedError(
                    f"Canonical entry disappeared during guard: {candidate}"
                ) from None
            result[candidate] = None
            return
        kind = (
            "symlink"
            if candidate.is_symlink()
            else "directory"
            if stat.S_ISDIR(before.st_mode)
            else "file"
            if stat.S_ISREG(before.st_mode)
            else "other"
        )
        digest: str | None = None
        if kind == "file":
            try:
                digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            except FileNotFoundError:
                raise _NamespaceChangedError(
                    f"Canonical file disappeared while hashing: {candidate}"
                ) from None
        identity = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            0 if kind == "directory" else before.st_size,
            0 if kind == "directory" else before.st_mtime_ns,
            0 if kind == "directory" else before.st_ctime_ns,
        )
        try:
            after = candidate.lstat()
        except FileNotFoundError:
            raise _NamespaceChangedError(
                f"Canonical entry disappeared during guard: {candidate}"
            ) from None
        after_kind = (
            "symlink"
            if candidate.is_symlink()
            else "directory"
            if stat.S_ISDIR(after.st_mode)
            else "file"
            if stat.S_ISREG(after.st_mode)
            else "other"
        )
        if identity != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            0 if kind == "directory" else after.st_size,
            0 if kind == "directory" else after.st_mtime_ns,
            0 if kind == "directory" else after.st_ctime_ns,
        ) or after_kind != kind:
            raise _NamespaceChangedError(
                f"Canonical namespace changed during guard: {candidate}"
            )
        result[candidate] = (kind, *identity, digest)
        if kind == "directory" and depth > 0:
            children = tuple(
                sorted(candidate.iterdir(), key=lambda value: value.name)
            )
            for child in children:
                visit(child, depth - 1, expected=True)
            try:
                final_children = tuple(
                    sorted(candidate.iterdir(), key=lambda value: value.name)
                )
                final = candidate.lstat()
            except FileNotFoundError:
                raise _NamespaceChangedError(
                    f"Canonical directory disappeared during enumeration: {candidate}"
                ) from None
            if (
                final.st_dev,
                final.st_ino,
                final.st_mode,
            ) != (after.st_dev, after.st_ino, after.st_mode) or children != final_children:
                raise _NamespaceChangedError(
                    f"Canonical directory changed during enumeration: {candidate}"
                )

    visit(path, max_depth)
    return result


def _namespace_changed(guarded: dict[Path, _NamespaceFingerprint], max_depth: int) -> bool:
    try:
        roots = tuple(
            path
            for path in guarded
            if not any(
                other != path and other in path.parents for other in guarded
            )
        )
        current: dict[Path, _NamespaceFingerprint] = {}
        for root in roots:
            current.update(_namespace_guard(root, max_depth))
        return current != guarded
    except (OSError, ValueError, _NamespaceChangedError):
        return True


def _emit_changed_command(
    args: argparse.Namespace,
    command: str,
    domain: AuditDomain,
    code: str,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    return emit_academic_command_error(
        args,
        command,
        RuntimeError("Canonical state changed during command observation."),
        stdout,
        stderr,
        domain=domain,
        code=code,
    )


def _show_fingerprints(paths: tuple[Path, ...]) -> dict[Path, _ShowFingerprint]:
    fingerprints: dict[Path, _ShowFingerprint] = {}
    for path in paths:
        try:
            before = path.lstat()
        except FileNotFoundError:
            fingerprints[path] = None
            continue
        if not stat.S_ISREG(before.st_mode) or path.is_symlink():
            raise ValueError(f"Guarded canonical file is not a regular file: {path}")
        content = path.read_bytes()
        after = path.lstat()
        identity = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if identity != (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ):
            raise ValueError(f"Guarded canonical file changed while read: {path}")
        fingerprints[path] = (*identity, hashlib.sha256(content).hexdigest())
    return fingerprints


def _show_files_changed(guarded: dict[Path, _ShowFingerprint]) -> bool:
    try:
        return _show_fingerprints(tuple(guarded)) != guarded
    except (OSError, ValueError):
        return True


def _manifest_file_changed(
    path: Path, before: tuple[int, int, int, int, int, int]
) -> bool:
    try:
        status = path.lstat()
    except OSError:
        return True
    return path.is_symlink() or (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
    ) != before


def handle_registry_show(args: argparse.Namespace, _library: StandardsLibrary, stdout: TextIO, stderr: TextIO) -> int:
    root = args.workspace_root
    try:
        data: object
        findings: tuple[RegistryAuditFinding, ...] = ()
        ok = True
        if args.entity == "registration":
            work = ModuleWorkRef(args.module_id, args.class_id, args.work_id)
            work_guard = _namespace_guard(
                academic_work_registration_dir(root, work), 2
            )
            report, state = _audit_academic_registry_observation(
                root,
                options=RegistryAuditOptions(
                    scopes=("registrations",),
                    class_id=work.class_id,
                    module_id=work.module_id,
                    work_id=work.work_id,
                ),
                producer_profiles=(),
            )
            findings = report.findings
            if not report.ok:
                _emit_report(
                    "academic registry show registration",
                    report,
                    args.format,
                    stdout,
                )
                return 1
            history = tuple(
                sorted(
                    (
                        record
                        for record in state.registrations
                        if record.work == work
                    ),
                    key=lambda value: value.registration_revision,
                )
            )
            if not history:
                raise FileNotFoundError("Registration does not exist.")
            current = history[-1]
            record = next(
                (
                    candidate
                    for candidate in history
                    if candidate.registration_revision == args.revision
                ),
                None,
            ) if args.revision is not None else current
            if record is None:
                raise FileNotFoundError("Registration revision does not exist.")
            revisions = tuple(item.registration_revision for item in history)
            data = {"registration": academic_work_registration_to_dict(record), "canonical_path": (academic_work_registration_revision_path(root, work, record.registration_revision)).relative_to(root).as_posix(), "revision_history": revisions, "is_current": record.registration_revision == current.registration_revision, "current_revision": current.registration_revision}
            if _namespace_changed(work_guard, 2):
                return _emit_changed_command(
                    args, "academic registry show registration", "registrations",
                    "registrations.changed_during_audit", stdout, stderr,
                )
        elif args.entity == "publication":
            publication_guard = _namespace_guard(publications_dir(root), 1)
            withdrawal_guard = _namespace_guard(publication_withdrawals_dir(root), 1)
            scopes = ["publications", "contracts"]
            if args.verify_manifest:
                scopes.append("manifests")
            report, state = _audit_academic_registry_observation(
                root,
                options=RegistryAuditOptions(
                    scopes=tuple(scopes),  # type: ignore[arg-type]
                    publication_id=args.publication_id,
                ),
                producer_profiles=(),
            )
            findings = report.findings
            publication_record = next(
                (record for record in state.publications if record.publication_id == args.publication_id),
                None,
            )
            if publication_record is None:
                if args.format == "json":
                    _emit_json(
                        "academic registry show publication", root, False, {},
                        report.findings, stdout,
                    )
                else:
                    _emit_report(
                        "academic registry show publication", report,
                        args.format, stdout,
                    )
                return 1
            series = tuple(state.publications)
            withdrawal = next(
                (item for item in state.withdrawals if item.publication_id == args.publication_id),
                None,
            )
            registration_state: object = next(
                (
                    item for item in state.registrations
                    if item.work == publication_record.work
                    and item.registration_revision
                    == publication_record.academic_work_registration_revision
                ),
                None,
            )
            canonical_path = publication_record_path(
                root, publication_record.publication_id
            ).relative_to(root).as_posix()
            relationships_valid = not any(
                finding.severity == "error"
                and finding.domain == "publications"
                for finding in report.findings
            )
            if relationships_valid:
                successors = tuple(sorted(record.publication_id for record in series if record.supersedes_publication_id == publication_record.publication_id))
                is_head = not any(record.supersedes_publication_id == publication_record.publication_id for record in series)
                data = cast(dict[str, object], {"publication": publication_record_to_dict(publication_record), "canonical_path": canonical_path, "series_identity": {"class_id": publication_record.work.class_id, "module_id": publication_record.work.module_id, "work_id": publication_record.work.work_id, "publication_kind": publication_record.publication_kind, "record_set_id": publication_record.record_set_id}, "predecessor": publication_record.supersedes_publication_id, "successors": successors, "is_series_head": is_head, "is_historical": not is_head, "is_withdrawn": withdrawal is not None, "is_current_selectable": is_head and withdrawal is None, "withdrawal": None if withdrawal is None else publication_withdrawal_to_dict(withdrawal), "registration": registration_state, "school_year": _class_school_year(root, publication_record.work.class_id), "contracts_compatible": report.contracts_compatible})
            else:
                data = cast(dict[str, object], {
                    "publication": publication_record_to_dict(publication_record),
                    "canonical_path": canonical_path,
                    "derived_state": None,
                })
            if args.verify_manifest:
                data["manifest_valid"] = report.manifests_valid
            ok = report.ok
            manifest_changed = False
            if args.verify_manifest:
                for publication_candidate in state.publications:
                    initial = state.manifest_paths.get(
                        publication_candidate.publication_id
                    )
                    if initial is None:
                        continue
                    try:
                        final = resolve_publication_manifest_path(
                            root, publication_candidate
                        )
                        final_lexical = _manifest_lexical_fingerprint(
                            root, publication_candidate
                        )
                    except Exception:
                        manifest_changed = True
                        break
                    fingerprint = state.manifest_fingerprints.get(initial)
                    if (
                        final != initial
                        or final_lexical != state.manifest_lexical_fingerprints.get(
                            publication_candidate.publication_id
                        )
                        or fingerprint is None
                        or _manifest_file_changed(final, fingerprint)
                    ):
                        manifest_changed = True
                        break
            if manifest_changed:
                return _emit_changed_command(
                    args, "academic registry show publication", "manifests",
                    "manifests.changed_during_audit", stdout, stderr,
                )
            if (
                _namespace_changed(publication_guard, 1)
                or _namespace_changed(withdrawal_guard, 1)
                or any(
                    _manifest_file_changed(path, fingerprint)
                    for path, fingerprint
                    in state.relationship_fingerprints.items()
                )
            ):
                return _emit_changed_command(
                    args, "academic registry show publication", "publications",
                    "publications.changed_during_audit", stdout, stderr,
                )
        elif args.entity == "withdrawal":
            publication_guard = _namespace_guard(publications_dir(root), 1)
            withdrawal_guard = _namespace_guard(publication_withdrawals_dir(root), 1)
            report, state = _audit_academic_registry_observation(
                root,
                options=RegistryAuditOptions(
                    scopes=("publications",), publication_id=args.publication_id
                ),
                producer_profiles=(),
            )
            findings = report.findings
            if not report.ok:
                if any(
                    finding.code == "publications.not_found"
                    for finding in report.findings
                ):
                    raise FileNotFoundError("Withdrawal does not exist.")
                _emit_report("academic registry show withdrawal", report, args.format, stdout)
                return 1
            publication = next(
                (item for item in state.publications if item.publication_id == args.publication_id),
                None,
            )
            withdrawal = next(
                (item for item in state.withdrawals if item.publication_id == args.publication_id),
                None,
            )
            if publication is None or withdrawal is None:
                raise FileNotFoundError("Withdrawal does not exist.")
            validate_publication_withdrawal_relationship(publication, withdrawal)
            data = {"withdrawal": publication_withdrawal_to_dict(withdrawal), "canonical_path": publication_withdrawal_path(root, withdrawal.publication_id).relative_to(root).as_posix()}
            if (
                _namespace_changed(publication_guard, 1)
                or _namespace_changed(withdrawal_guard, 1)
                or any(
                    _manifest_file_changed(path, fingerprint)
                    for path, fingerprint
                    in state.relationship_fingerprints.items()
                )
            ):
                return _emit_changed_command(
                    args, "academic registry show withdrawal", "publications",
                    "publications.changed_during_audit", stdout, stderr,
                )
        elif args.entity == "catalog":
            catalog_path = academic_catalog_path(root)
            try:
                catalog_path.lstat()
            except FileNotFoundError:
                raise FileNotFoundError("Academic catalog does not exist.")
            catalog_guard = _namespace_guard(catalog_path, 0)
            report = audit_academic_registry(
                root,
                options=RegistryAuditOptions(
                    scopes=("catalog",), require_catalog=True
                ),
            )
            findings = report.findings
            ok = report.ok
            data = cast(dict[str, object], {"catalog_path": catalog_path.relative_to(root).as_posix(), "application_id": academic_catalog.ACADEMIC_CATALOG_APPLICATION_ID, "current": report.catalog_ready})
            metadata = None
            if not any(
                finding.code == "catalog.incompatible"
                for finding in report.findings
            ):
                try:
                    metadata = academic_catalog.load_academic_catalog_metadata(root)
                except Exception:
                    metadata = None
            if metadata is not None:
                data["metadata"] = metadata
            if args.sources and metadata is not None:
                connection = academic_catalog._read_connection(academic_catalog_path(root))
                try:
                    data["sources"] = tuple({"path": str(row[0]), "size_bytes": int(row[1]), "sha256": str(row[2])} for row in connection.execute("SELECT relative_path,size_bytes,sha256 FROM catalog_sources ORDER BY relative_path"))
                finally:
                    connection.close()
            if _namespace_changed(catalog_guard, 0):
                findings = (*findings, RegistryAuditFinding("error", "catalog", "catalog.changed_during_audit", "Guarded catalog changed before output.", "registry/catalog.sqlite", repair="rebuild_catalog"))
                ok = False
                data.pop("metadata", None)
                data.pop("sources", None)
        else:
            data = get_registry_lock(root, args.lock_id)
        if args.format == "json":
            _emit_json(f"academic registry show {args.entity}", root, ok, data, findings, stdout)
        else:
            native = _native(data)
            _emit_detail_text(native, stdout)
            for finding in findings:
                print(
                    f"{finding.severity}: {finding.code}: {finding.message}",
                    file=stdout,
                )
        return 0 if ok else 1
    except _NamespaceChangedError:
        domain = _show_domain(args.entity)
        return _emit_changed_command(
            args, f"academic registry show {args.entity}", domain,
            f"{domain}.changed_during_audit", stdout, stderr,
        )
    except Exception as error:
        domain = _show_domain(args.entity)
        return emit_academic_command_error(
            args,
            f"academic registry show {args.entity}",
            error,
            stdout,
            stderr,
            domain=domain,
            code=f"{domain}.not_found" if isinstance(error, FileNotFoundError) else f"{domain}.read_failed",
        )


def handle_registry_rebuild(args: argparse.Namespace, _library: StandardsLibrary, stdout: TextIO, stderr: TextIO) -> int:
    root = args.workspace_root
    try:
        scopes = ["academic_periods", "registrations", "publications"]
        if args.verify_manifests or args.require_manifests_valid:
            scopes.append("manifests")
        report = audit_academic_registry(
            root,
            options=RegistryAuditOptions(
                scopes=tuple(scopes)  # type: ignore[arg-type]
            ),
        )
        blocked = not report.canonical_valid or (args.require_manifests_valid and report.manifests_valid is False)
        if blocked:
            _emit_report("academic registry rebuild-catalog", report, args.format, stdout)
            return 1
        projection = academic_catalog._load_projection(root)
        if args.dry_run:
            data: object = {"dry_run": True, "source_file_count": len(projection.sources), "source_snapshot_sha256": projection.snapshot_sha256}
            reported_digest = projection.snapshot_sha256
        else:
            build_result = academic_catalog.rebuild_academic_catalog(root)
            data = build_result
            reported_digest = build_result.metadata.source_snapshot_sha256
            installed = audit_academic_registry(
                root, options=RegistryAuditOptions(scopes=("catalog",), require_catalog=True)
            )
            if installed.catalog_ready is not True:
                raise RuntimeError("Installed catalog failed post-rebuild validation.")
            installed_metadata = academic_catalog.load_academic_catalog_metadata(root)
            if (
                build_result.catalog_path != academic_catalog_path(root)
                or installed_metadata != build_result.metadata
            ):
                raise RuntimeError(
                    "Installed catalog identity or metadata differs from build result."
                )
        if args.format == "json":
            _emit_json("academic registry rebuild-catalog", root, True, data, report.findings, stdout)
        else:
            print("Catalog rebuild dry run completed; no files were written." if args.dry_run else f"Academic catalog rebuilt: {academic_catalog_path(root)}", file=stdout)
            print(f"Source snapshot: {reported_digest}", file=stdout)
            if args.verify_manifests or args.require_manifests_valid:
                for finding in report.findings:
                    if finding.domain == "manifests":
                        print(
                            f"{finding.severity}: {finding.code}: {finding.message}",
                            file=stdout,
                        )
        return 0
    except Exception as error:
        return emit_academic_command_error(
            args,
            "academic registry rebuild-catalog",
            error,
            stdout,
            stderr,
            domain="catalog",
            code="catalog.rebuild_failed",
        )


def handle_registry_clear_lock(args: argparse.Namespace, _library: StandardsLibrary, stdout: TextIO, stderr: TextIO) -> int:
    try:
        if not args.force and not args.dry_run:
            raise AcademicCommandUsageError(
                "--force is required unless --dry-run is selected."
            )
        result = clear_registry_lock(args.workspace_root, args.lock_id, expected_sha256=args.expected_sha256, force=args.force, dry_run=args.dry_run)
        if args.format == "json":
            _emit_json("academic registry clear-lock", args.workspace_root, True, result, (), stdout)
        else:
            action = "would be removed" if result.dry_run else "removed"
            print(f"Lock {result.lock.lock_id} {action}; Core cannot prove the lock was stale.", file=stdout)
            print(f"SHA-256: {result.lock.sha256}", file=stdout)
        return 0
    except RegistryAuditError as error:
        return emit_academic_command_error(
            args,
            "academic registry clear-lock",
            error,
            stdout,
            stderr,
            domain="locks",
            code="locks.clear_refused",
        )
    except AcademicCommandUsageError as error:
        return emit_academic_command_error(
            args,
            "academic registry clear-lock",
            error,
            stdout,
            stderr,
            domain="locks",
            code="locks.clear_refused",
        )
