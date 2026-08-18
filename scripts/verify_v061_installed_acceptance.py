"""Standalone installed-wheel/sdist acceptance for pds-core v0.6.1."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import shutil
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

EXPECTED_VERSION = "0.6.1"
SIBLING_IMPORTS = (
    "scoreform",
    "quillan",
    "concord",
    "portia",
    "meridian",
    "paper_data_suite",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _verify_manifest(fixture_root: Path) -> None:
    manifest = fixture_root / "SHA256SUMS.txt"
    expected_paths: set[str] = set()
    for line in manifest.read_text(encoding="ascii").splitlines():
        digest, relative_path = line.split("  ", maxsplit=1)
        expected_paths.add(relative_path)
        actual = hashlib.sha256((fixture_root / relative_path).read_bytes()).hexdigest()
        _require(actual == digest, f"fixture checksum mismatch: {relative_path}")
    actual_paths = {
        path.relative_to(fixture_root).as_posix()
        for path in fixture_root.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS.txt"
    }
    _require(actual_paths == expected_paths, "fixture manifest coverage mismatch")


def _run_acceptance(fixture_root: Path, workspace: Path) -> None:
    import pds_core
    from pds_core.grouping_signal_csv import (
        GroupingSignalCsvError,
        grouping_signal_csv_to_signal_set,
        grouping_signal_set_from_csv,
        grouping_signal_set_to_csv_bytes,
        parse_grouping_signal_csv,
    )
    from pds_core.grouping_signal_diagnostics import diagnose_grouping_signal
    from pds_core.grouping_signal_storage import (
        GroupingSignalConflictError,
        load_grouping_signal,
        write_grouping_signal,
    )
    from pds_core.grouping_signals import (
        grouping_signal_set_from_json,
        grouping_signal_set_to_json_bytes,
    )

    _require(pds_core.__version__ == EXPECTED_VERSION, "installed version mismatch")
    package_file = Path(pds_core.__file__).resolve()
    script_project_root = Path(__file__).resolve().parents[1]
    if (
        (script_project_root / "pyproject.toml").is_file()
        and (script_project_root / "pds_core").is_dir()
    ):
        _require(
            not package_file.is_relative_to(script_project_root),
            "pds_core resolved from the source checkout instead of the installed distribution",
        )
    print(f"installed pds_core path: {package_file}")
    for sibling in SIBLING_IMPORTS:
        _require(
            importlib.util.find_spec(sibling) is None,
            f"standalone environment unexpectedly contains sibling module {sibling}",
        )

    teacher_json = (fixture_root / "teacher_complete.json").read_bytes()
    teacher_csv = (fixture_root / "teacher_complete.csv").read_bytes()
    teacher = grouping_signal_set_from_json(teacher_json)
    _require(grouping_signal_set_to_json_bytes(teacher) == teacher_json, "JSON mismatch")
    _require(
        grouping_signal_set_to_csv_bytes(teacher, "discussion_support") == teacher_csv,
        "CSV export mismatch",
    )
    round_tripped = grouping_signal_set_from_csv(teacher_csv)
    _require(
        grouping_signal_set_to_json_bytes(round_tripped) == teacher_json,
        "complete CSV round trip changed canonical JSON",
    )

    projection = parse_grouping_signal_csv(
        (fixture_root / "module_selected_dimension_projection.csv").read_bytes()
    )
    try:
        grouping_signal_csv_to_signal_set(projection)
    except GroupingSignalCsvError:
        pass
    else:
        raise RuntimeError("projection conversion unexpectedly reused source identity")
    projected = grouping_signal_csv_to_signal_set(
        projection,
        new_signal_set_id="installed_projection_001",
        new_created_at=datetime(2026, 9, 2, 13, tzinfo=UTC),
    )
    _require(projected.signal_set_id == "installed_projection_001", "projection ID mismatch")

    first = write_grouping_signal(workspace, teacher)
    second = write_grouping_signal(workspace, teacher)
    _require(first.disposition == "created", "first immutable write was not created")
    _require(second.disposition == "existing", "idempotent replay was not existing")
    expected_digest = hashlib.sha256(teacher_json).hexdigest()
    _require(first.stored.digest == expected_digest, "stored digest mismatch")
    loaded = load_grouping_signal(workspace, teacher.class_id, teacher.signal_set_id)
    _require(loaded.signal == teacher, "loaded signal mismatch")
    _require(loaded.digest == expected_digest, "loaded digest mismatch")

    changed = replace(
        teacher,
        student_bands=(replace(teacher.student_bands[0], band=2),)
        + teacher.student_bands[1:],
    )
    try:
        write_grouping_signal(workspace, changed)
    except GroupingSignalConflictError:
        pass
    else:
        raise RuntimeError("immutable identity collision did not fail")

    shutil.copytree(fixture_root / "classes", workspace / "classes")
    module_signal = grouping_signal_set_from_json(
        (fixture_root / "module_multi_dimension.json").read_bytes()
    )
    report = diagnose_grouping_signal(workspace, module_signal)
    finding_codes = {item.code for item in report.findings}
    _require("wrong_class_student" in finding_codes, "wrong-class finding missing")
    _require("unknown_student" in finding_codes, "unknown-student finding missing")
    _require("missing_student_signal" in finding_codes, "missing coverage finding missing")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    args = parser.parse_args()
    fixture_root = args.fixtures.resolve()
    _verify_manifest(fixture_root)

    with tempfile.TemporaryDirectory(prefix="pds-core-v061-import-") as import_tmp:
        original_cwd = Path.cwd()
        try:
            os.chdir(import_tmp)
            before = set(Path(import_tmp).iterdir())
            import pds_core.grouping_signal_csv  # noqa: F401
            import pds_core.grouping_signal_diagnostics  # noqa: F401
            import pds_core.grouping_signal_storage  # noqa: F401
            import pds_core.grouping_signals  # noqa: F401
            after = set(Path(import_tmp).iterdir())
            _require(before == after, "Core imports created workspace state")
        finally:
            os.chdir(original_cwd)

    with tempfile.TemporaryDirectory(prefix="pds-core-v061-workspace-") as workspace_tmp:
        _run_acceptance(fixture_root, Path(workspace_tmp))

    print("pds-core v0.6.1 installed standalone acceptance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
