from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.cli.conftest import run_cli
import pds_core.cli_support.academic_periods as academic_periods_cli
from tests.test_academic_period_storage import _calendar, _write_pointer, _write_raw_revision


def test_periods_list_empty_text_and_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output, error = run_cli(
        tmp_path, "academic", "periods", "list", capsys=capsys
    )
    assert code == 0 and output == "No matching records.\n" and not error
    code, output, error = run_cli(
        tmp_path,
        "academic",
        "periods",
        "list",
        "--format",
        "json",
        capsys=capsys,
    )
    assert code == 0 and json.loads(output)["data"]["rows"] == [] and not error


def test_periods_validate_is_focused_and_read_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    publication = tmp_path / "registry/publications/bad.json"
    publication.parent.mkdir(parents=True)
    publication.write_text("bad", encoding="utf-8")
    before = publication.read_bytes()
    code, output, error = run_cli(
        tmp_path, "academic", "periods", "validate", capsys=capsys
    )
    assert code == 0 and "publications." not in output and not error
    assert publication.read_bytes() == before


def test_period_revision_flags_are_mutually_exclusive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, error = run_cli(
        tmp_path,
        "academic",
        "periods",
        "list",
        "--calendar-revision",
        "1",
        "--all-revisions",
        capsys=capsys,
    )
    assert code == 2 and "not allowed" in error


def test_academic_period_integer_ordering_across_digit_lengths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = getattr(academic_periods_cli, "audit_academic_registry")
    options_type = getattr(academic_periods_cli, "RegistryAuditOptions")
    healthy = audit(
        tmp_path,
        options=options_type(scopes=("academic_periods",)),
    )
    (tmp_path / "settings/academic_periods/2026-2027").mkdir(parents=True)
    def calendar(revision: int) -> object:
        periods = tuple(
            SimpleNamespace(
                sequence=sequence,
                period_id=f"p{sequence}",
                period_type="marking_period",
                lifecycle="active",
                start_date=date(2026, 9, 1),
                end_date=date(2026, 10, 1),
                parent_period_id=None,
                label=f"Period {sequence}",
            )
            for sequence in (10, 2)
        )
        return SimpleNamespace(
            periods=periods,
            calendar_revision=revision,
            school_year="2026-2027",
        )

    monkeypatch.setattr(
        academic_periods_cli,
        "_audit_academic_registry_observation",
        lambda *_args, **_kwargs: (
            healthy,
            SimpleNamespace(calendars=[calendar(10), calendar(2)]),
        ),
    )
    code, output, error = run_cli(
        tmp_path,
        "academic", "periods", "list", "--all-revisions", "--format", "json",
        capsys=capsys,
    )
    rows = json.loads(output)["data"]["rows"]
    assert code == 0 and error == ""
    assert [(row["calendar_revision"], row["sequence"]) for row in rows] == [
        (2, 2), (2, 10), (10, 2), (10, 10)
    ]


def test_academic_periods_validate_strict_json_ok_matches_exit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hidden = tmp_path / "settings/academic_periods/.interrupted"
    hidden.parent.mkdir(parents=True)
    hidden.write_text("artifact", encoding="utf-8")
    normal = run_cli(
        tmp_path, "academic", "periods", "validate", "--format", "json",
        capsys=capsys,
    )
    strict = run_cli(
        tmp_path, "academic", "periods", "validate", "--strict", "--format", "json",
        capsys=capsys,
    )
    normal_payload, strict_payload = json.loads(normal[1]), json.loads(strict[1])
    assert normal[0] == 0 and normal_payload["ok"] is True
    assert strict[0] == 1 and strict_payload["ok"] is False
    assert normal_payload["data"] == strict_payload["data"]
    assert normal_payload["findings"] == strict_payload["findings"]


def test_academic_period_all_revisions_lists_valid_complete_history(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = _calendar()
    second = _calendar(revision=2)
    _write_raw_revision(tmp_path, first)
    _write_raw_revision(tmp_path, second)
    _write_pointer(tmp_path, revision=2)
    code, output, error = run_cli(
        tmp_path, "academic", "periods", "list", "--all-revisions",
        "--format", "json", capsys=capsys,
    )
    rows = json.loads(output)["data"]["rows"]
    assert code == 0 and error == ""
    assert {row["calendar_revision"] for row in rows} == {1, 2}


def test_academic_period_all_revisions_with_orphan_history_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_raw_revision(tmp_path, _calendar())
    code, output, error = run_cli(
        tmp_path, "academic", "periods", "list", "--all-revisions",
        "--format", "json", capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 1 and error == "" and payload["ok"] is False
    assert "academic_periods.orphan_revision" in {
        item["code"] for item in payload["findings"]
    }


def test_academic_period_missing_pointer_fails_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_raw_revision(tmp_path, _calendar())
    code, output, _error = run_cli(
        tmp_path, "academic", "periods", "list", "--format", "json",
        capsys=capsys,
    )
    assert code == 1 and "academic_periods.pointer_missing" in {
        item["code"] for item in json.loads(output)["findings"]
    }


def test_academic_period_malformed_pointer_fails_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_raw_revision(tmp_path, _calendar())
    pointer = tmp_path / "settings/academic_periods/2026-2027/current.json"
    pointer.write_text("bad", encoding="utf-8")
    code, output, _error = run_cli(
        tmp_path, "academic", "periods", "list", "--format", "json",
        capsys=capsys,
    )
    assert code == 1 and "academic_periods.pointer_invalid" in {
        item["code"] for item in json.loads(output)["findings"]
    }


def test_academic_period_current_and_explicit_historical_listing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_raw_revision(tmp_path, _calendar())
    _write_raw_revision(tmp_path, _calendar(revision=2))
    _write_pointer(tmp_path, revision=2)
    current = run_cli(
        tmp_path, "academic", "periods", "list", "--format", "json",
        capsys=capsys,
    )
    historical = run_cli(
        tmp_path, "academic", "periods", "list", "--calendar-revision", "1",
        "--format", "json", capsys=capsys,
    )
    assert current[0] == historical[0] == 0
    assert {
        row["calendar_revision"] for row in json.loads(current[1])["data"]["rows"]
    } == {2}
    assert {
        row["calendar_revision"]
        for row in json.loads(historical[1])["data"]["rows"]
    } == {1}


def test_academic_period_pointer_selecting_nonfinal_revision_fails_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = _calendar()
    second = _calendar(revision=2)
    _write_raw_revision(tmp_path, first)
    _write_raw_revision(tmp_path, second)
    _write_pointer(tmp_path, revision=1)
    code, output, _error = run_cli(
        tmp_path, "academic", "periods", "list", "--format", "json",
        capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 1 and "academic_periods.pointer_invalid" in {
        item["code"] for item in payload["findings"]
    }


def test_academic_period_invalid_transition_fails_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = _calendar()
    second = replace(
        first,
        calendar_revision=2,
        created_at=first.created_at + timedelta(days=1),
        updated_at=first.updated_at + timedelta(days=1),
    )
    _write_raw_revision(tmp_path, first)
    _write_raw_revision(tmp_path, second)
    _write_pointer(tmp_path, revision=2)
    code, output, _error = run_cli(
        tmp_path, "academic", "periods", "list", "--all-revisions",
        "--format", "json", capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 1 and "academic_periods.transition_invalid" in {
        item["code"] for item in payload["findings"]
    }


def test_academic_period_list_history_race_is_normalized(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_raw_revision(tmp_path, _calendar())
    _write_pointer(tmp_path, revision=1)
    pointer = tmp_path / "settings/academic_periods/2026-2027/current.json"
    original = getattr(
        academic_periods_cli, "_audit_academic_registry_observation"
    )

    def changing(*args: object, **kwargs: object) -> object:
        observed = original(*args, **kwargs)
        pointer.write_text(
            pointer.read_text(encoding="utf-8") + "\n", encoding="utf-8"
        )
        return observed

    monkeypatch.setattr(
        academic_periods_cli, "_audit_academic_registry_observation", changing
    )
    code, output, error = run_cli(
        tmp_path, "academic", "periods", "list", "--format", "json",
        capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 1 and error == "" and payload["ok"] is False
    assert {item["code"] for item in payload["findings"]} == {
        "academic_periods.changed_during_audit"
    }


def test_initial_period_namespace_guard_race_is_normalized(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    changed = getattr(academic_periods_cli, "_NamespaceChangedError")
    monkeypatch.setattr(
        academic_periods_cli,
        "_namespace_guard",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(changed("race")),
    )
    code, output, error = run_cli(
        tmp_path, "academic", "periods", "list", "--format", "json",
        capsys=capsys,
    )
    payload = json.loads(output)
    assert code == 1 and error == "" and payload["ok"] is False
    assert [finding["code"] for finding in payload["findings"]] == [
        "academic_periods.changed_during_audit"
    ]
