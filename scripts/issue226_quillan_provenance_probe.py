"""Installed exact-wheel probe for Issue #226 / Quillan 0.10.4 provenance."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import tempfile
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import cast

import pds_core
from pds_core.scan_retention import RetainedSourceScan, retain_source_scan
from pds_core.scan_routes import (
    RETAINED_SOURCE_FILENAME_MAX_LENGTH,
    SOURCE_SCAN_ID_MAX_LENGTH,
    retained_source_scan_path,
)

EXPECTED_CORE_VERSION = "0.6.4"
EXPECTED_QUILLAN_VERSION = "0.10.4"


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise RuntimeError(f"{field} must be a JSON object.")
    return cast(dict[str, object], value)


def _text(mapping: dict[str, object], field: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"{field} must be nonempty text.")
    return value


def _assert_not_under_checkout(path: Path, checkout: Path, label: str) -> None:
    try:
        path.resolve().relative_to(checkout.resolve())
    except ValueError:
        return
    raise RuntimeError(f"{label} resolved from the Core source checkout.")


def _validator() -> Callable[..., object]:
    module = importlib.import_module("quillan.retained_source_provenance")
    value = getattr(module, "validate_core_retention_event_consistency", None)
    if not callable(value):
        raise RuntimeError("Quillan retention consistency validator is unavailable.")
    return cast(Callable[..., object], value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-fixture", type=Path, required=True)
    parser.add_argument("--source-checkout", type=Path, required=True)
    args = parser.parse_args()

    core_version = importlib.metadata.version("pds-core")
    quillan_version = importlib.metadata.version("quillan")
    if core_version != EXPECTED_CORE_VERSION or pds_core.__version__ != core_version:
        raise RuntimeError("Installed Core identity is not the expected 0.6.4 candidate.")
    if quillan_version != EXPECTED_QUILLAN_VERSION:
        raise RuntimeError("Installed Quillan identity is not exact release 0.10.4.")

    core_file = Path(pds_core.__file__).resolve()
    _assert_not_under_checkout(core_file, args.source_checkout, "pds_core")
    quillan_spec = importlib.util.find_spec("quillan")
    if quillan_spec is None or quillan_spec.origin is None:
        raise RuntimeError("Installed Quillan package could not be located.")
    _assert_not_under_checkout(Path(quillan_spec.origin), args.source_checkout, "quillan")

    fixture = _mapping(
        json.loads(args.legacy_fixture.read_text(encoding="utf-8")),
        "legacy fixture",
    )
    source_filename = _text(fixture, "source_filename")
    source_sha256 = _text(fixture, "source_sha256")
    intake_timestamp_text = _text(fixture, "intake_timestamp")
    intake_date_text = _text(fixture, "intake_date")
    retained_filename = _text(fixture, "retained_filename")
    retained_relative = _text(fixture, "retained_source_relative_path")
    source_scan_id = _text(fixture, "source_scan_id")
    content = _text(fixture, "content_text").encode("utf-8")
    if hashlib.sha256(content).hexdigest() != source_sha256:
        raise RuntimeError("Legacy fixture content digest does not match its provenance.")

    timestamp = datetime.fromisoformat(intake_timestamp_text)
    intake_date = date.fromisoformat(intake_date_text)
    validate = _validator()

    with tempfile.TemporaryDirectory(prefix="pds-core-issue226-quillan-probe-") as temp:
        workspace = Path(temp) / "workspace"
        workspace.mkdir()
        source = Path(temp) / source_filename
        source.write_bytes(content)

        fresh = retain_source_scan(workspace, source, intake_timestamp=timestamp)
        if len(fresh.retained_source_path.name) > RETAINED_SOURCE_FILENAME_MAX_LENGTH:
            raise RuntimeError("Fresh retained filename exceeds the Core writer maximum.")
        if len(fresh.source_scan_id) > SOURCE_SCAN_ID_MAX_LENGTH:
            raise RuntimeError("Fresh source_scan_id exceeds the Core writer maximum.")
        validate(
            source_scan_id=fresh.source_scan_id,
            source_filename=fresh.source_filename,
            source_sha256=fresh.source_sha256,
            retained_source_path=fresh.retained_source_path,
            retained_source_relative_path=fresh.retained_source_relative_path,
            intake_timestamp=fresh.intake_timestamp,
            intake_date=fresh.intake_date,
            workspace_root=workspace,
        )

        legacy_path = retained_source_scan_path(
            workspace,
            intake_date=intake_date,
            retained_filename=retained_filename,
        )
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_bytes(content)
        legacy = RetainedSourceScan(
            source_scan_id=source_scan_id,
            source_filename=source_filename,
            source_sha256=source_sha256,
            retained_source_path=legacy_path,
            retained_source_relative_path=retained_relative,
            intake_timestamp=timestamp,
            intake_date=intake_date,
        )
        validate(
            source_scan_id=legacy.source_scan_id,
            source_filename=legacy.source_filename,
            source_sha256=legacy.source_sha256,
            retained_source_path=legacy.retained_source_path,
            retained_source_relative_path=legacy.retained_source_relative_path,
            intake_timestamp=legacy.intake_timestamp,
            intake_date=legacy.intake_date,
            workspace_root=workspace,
        )

    result = {
        "candidate_core_version": core_version,
        "fresh_bounded_provenance": "pass",
        "legacy_failure": None,
        "legacy_v063_long_name_provenance": "pass",
        "quillan_version": quillan_version,
        "release_blocker": False,
    }
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
