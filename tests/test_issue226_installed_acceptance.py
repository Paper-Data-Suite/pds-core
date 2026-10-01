"""Tests for Issue #226 installed-artifact acceptance helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import verify_issue226_installed_acceptance as acceptance


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "issue226" / "legacy_retained_source_v063.json"


def test_issue226_installed_helpers_cover_bounded_and_legacy_contracts(
    tmp_path: Path,
) -> None:
    acceptance._assert_bounded_retention(tmp_path / "bounded")
    acceptance._assert_legacy_fixture(tmp_path / "legacy", FIXTURE)


def test_issue226_fixture_loader_rejects_shape_drift(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    payload["unexpected"] = True
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match="keys"):
        acceptance._load_fixture(path)


def test_issue226_installed_verifier_requires_explicit_artifact_identity() -> None:
    source = (ROOT / "scripts" / "verify_issue226_installed_acceptance.py").read_text(
        encoding="utf-8"
    )
    assert "--expected-version" in source
    assert "--source-checkout" in source
    assert "--legacy-fixture" in source
    assert "installed artifact" in source
    assert "LongPathsEnabled" not in source


def test_issue226_installed_acceptance_is_active_on_windows_ci() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "Issue #226 installed acceptance" in workflow
    assert "verify_issue226_installed_acceptance.py" in workflow
    assert "windows-latest" in workflow
    assert "LongPathsEnabled" in workflow
    assert "Get-ItemProperty" in workflow
    assert "Set-ItemProperty" not in workflow
