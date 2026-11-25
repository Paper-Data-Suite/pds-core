"""Synthetic C3B6 CLI tests for guarded class creation and recovery."""

from __future__ import annotations

import io
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

import pds_core.workspace as workspace
from pds_core.cli import _run
from pds_core.routes import class_dir, class_metadata_path, class_roster_path
from pds_core.school_years import close_school_year, open_school_year

YEAR = "2026-2027"
CLASS = "english10_p2"
AT = "2026-09-02T08:00:00+00:00"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    location = tmp_path / "synthetic-workspace"
    location.mkdir()
    monkeypatch.setattr(
        workspace, "get_default_workspace_root", lambda: tmp_path / "default-root"
    )
    monkeypatch.setattr(
        workspace,
        "get_workspace_config_path",
        lambda: tmp_path / "private-config" / "config.json",
    )
    monkeypatch.delenv(workspace.WORKSPACE_ROOT_ENV_VAR, raising=False)
    open_school_year(
        location, YEAR, opened_at=datetime.fromisoformat("2026-09-01T08:00:00+00:00")
    )
    return location


def _invoke(*args: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    code = _run(args, stdout=stdout, stderr=stderr)
    return code, stdout.getvalue(), stderr.getvalue()


def _args(root: Path, op: str, *, at: str = AT, class_id: str = CLASS) -> list[str]:
    return [
        "--workspace", str(root), "workspace", op, class_id, YEAR,
        "--created-at", at,
    ]


def _json(*args: str) -> tuple[int, dict[str, Any], str]:
    code, out, err = _invoke(*args, "--format", "json")
    payload: dict[str, Any] = json.loads(out)
    return code, payload, err


def _preview(root: Path) -> dict[str, Any]:
    code, payload, err = _json(*_args(root, "class-preview"))
    assert code == 0 and err == ""
    assert payload["scope"] == "class"
    assert payload["command"] == "workspace class-preview"
    assert payload["ok"] is True
    data: dict[str, Any] = payload["data"]
    return data


def _commit(
    root: Path,
    review: dict[str, Any],
    *,
    confirm: bool = True,
    at: str = AT,
    class_id: str = CLASS,
) -> tuple[int, dict[str, Any], str]:
    parts = _args(root, "class-commit", at=at, class_id=class_id)
    parts.extend([
        "--expected-current-state-token", review["current_state_token"],
        "--expected-candidate-state-token", review["candidate_state_token"],
    ])
    if confirm:
        parts.append("--confirm")
    return _json(*parts)


def _recovery(root: Path) -> dict[str, Any]:
    code, payload, err = _json(*_args(root, "class-recovery"))
    assert code == 0 and err == ""
    data: dict[str, Any] = payload["data"]
    assert data["ownership_established"] is False
    assert data["retry_authorized"] is False
    assert data["saved"] is False
    assert data["revalidation_required"] is True
    return data


def test_preview_is_read_only(root: Path) -> None:
    data = _preview(root)
    assert data["saved"] is False
    assert data["status"] == "preview"
    assert data["workspace_root"] == str(root.resolve())
    assert data["target_class_directory"] == str(class_dir(root.resolve(), CLASS))
    assert data["metadata_would_be_created"] is True
    assert data["roster_would_be_created"] is False
    assert len(data["current_state_token"]) == 64
    assert len(data["candidate_state_token"]) == 64
    assert not (root / "classes").exists()


def test_commit_and_replay(root: Path) -> None:
    review = _preview(root)
    code, payload, err = _commit(root, review)
    assert code == 0 and err == ""
    assert payload["ok"] is True
    assert payload["data"]["status"] == "committed"
    assert payload["data"]["changed_scopes"] == ["CLASS"]
    assert payload["data"]["revalidation_required"] is True
    assert not class_roster_path(root, CLASS).exists()
    path = class_metadata_path(root, CLASS)
    before = path.read_bytes()
    code, payload, err = _commit(root, review)
    assert code == 4 and err == ""
    assert payload["error"]["code"] == "class.class_exists"
    assert path.read_bytes() == before


def test_missing_confirmation(root: Path) -> None:
    code, payload, err = _commit(root, _preview(root), confirm=False)
    assert code == 2 and err == ""
    assert payload["error"]["code"] == "class.not_confirmed"
    assert not (root / "classes").exists()


@pytest.mark.parametrize(
    "class_id, at", [
        ("another_class", AT),
        (CLASS, "2026-09-03T08:00:00+00:00"),
    ],
)
def test_changed_proposal(root: Path, class_id: str, at: str) -> None:
    code, payload, err = _commit(root, _preview(root), class_id=class_id, at=at)
    assert code == 4 and err == ""
    assert payload["error"]["code"] == "class.candidate_changed"
    assert not (root / "classes").exists()


def test_invalid_token(root: Path) -> None:
    review = _preview(root)
    review["current_state_token"] = "invalid"
    code, payload, err = _commit(root, review)
    assert code == 2 and err == ""
    assert payload["error"]["code"] == "class.invalid_token"
    assert not (root / "classes").exists()


def test_stale_year(root: Path) -> None:
    review = _preview(root)
    close_school_year(root, closed_at=datetime.fromisoformat(AT))
    code, payload, err = _commit(root, review)
    assert code == 4 and err == ""
    assert payload["error"]["code"] == "class.no_open_year"
    assert not (root / "classes").exists()


def test_missing_workspace_structured(root: Path) -> None:
    missing = root / "missing"
    code, payload, err = _json(*_args(missing, "class-preview"))
    assert code == 5 and err == ""
    assert payload["error"]["code"] == "class.missing_workspace"
    assert not missing.exists()


def test_recovery_states_are_observations(root: Path) -> None:
    assert _recovery(root)["status"] == "absent"
    target = class_dir(root, CLASS)
    target.mkdir(parents=True)
    assert _recovery(root)["status"] == "empty_directory"
    sentinel = target / "producer-owned.txt"
    sentinel.write_text("preserved", encoding="utf-8")
    assert _recovery(root)["status"] == "conflict"
    assert sentinel.read_text(encoding="utf-8") == "preserved"


def test_recovery_match_is_not_commit_receipt(root: Path) -> None:
    code, _, _ = _commit(root, _preview(root))
    assert code == 0
    data = _recovery(root)
    assert data["status"] == "matches_review"
    assert "changed_scopes" not in data


def test_partial_publication_reported(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    review = _preview(root)

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("private injected detail")

    monkeypatch.setattr(os, "link", fail)
    code, payload, err = _commit(root, review)
    assert code == 7 and err == ""
    assert payload["ok"] is False
    assert payload["data"]["status"] == "partial"
    assert payload["data"]["changed_scopes"] == ["CLASS"]
    assert "private injected detail" not in json.dumps(payload)
    assert _recovery(root)["status"] == "empty_directory"


def test_uncertain_publication_reported(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    review = _preview(root)
    actual = os.link

    def link_then_fail(source: Path, destination: Path) -> None:
        actual(source, destination)
        raise OSError("private injected detail")

    monkeypatch.setattr(os, "link", link_then_fail)
    code, payload, err = _commit(root, review)
    assert code == 7 and err == ""
    assert payload["data"]["status"] == "indeterminate"
    assert payload["data"]["revalidation_required"] is True
    assert _recovery(root)["status"] == "matches_review"


def test_text_preview_and_legacy_show(root: Path) -> None:
    code, out, err = _invoke(*_args(root, "class-preview"))
    assert code == 0 and err == ""
    assert "current_state_token:" in out
    assert 'status: "preview"' in out
    code, out, err = _invoke("--workspace", str(root), "workspace", "show")
    assert code == 0 and out and err == ""


def test_invalid_timestamp_parse_refusal(root: Path) -> None:
    code, _, _ = _invoke(*_args(root, "class-preview", at="2026-09-02T08:00:00"))
    assert code == 2
    assert not (root / "classes").exists()
