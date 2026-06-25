"""Standards profile CLI tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pds_core.standards import (
    StandardsLibrary,
    StandardsProfile,
    load_standards_library,
    standards_profile_from_dict,
    standards_profile_to_dict,
    write_workspace_standards_library,
)
from tests.cli.conftest import make_cli_library, run_cli

def test_profile_create_allows_empty_profile_and_creates_only_library(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "create",
        "--profile-id",
        "empty_profile",
        "--title",
        "Empty Profile",
        capsys=capsys,
    )

    assert code == 0
    assert out == "Created standards profile empty_profile.\n"
    assert err == ""
    library = load_standards_library(tmp_path / "standards" / "library.json")
    assert library.profiles == (
        StandardsProfile(
            profile_id="empty_profile",
            standards=(),
            title="Empty Profile",
        ),
    )
    assert not (tmp_path / "standards" / "usage").exists()
    assert not (tmp_path / "ScoreForm").exists()
    assert not (tmp_path / "Quillan").exists()


def test_profile_create_preserves_standard_order_and_rejects_unsafe_inputs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    base_library = StandardsLibrary(
        standards=make_cli_library().standards,
        profiles=(),
    )
    write_workspace_standards_library(tmp_path, base_library)
    library_path = tmp_path / "standards" / "library.json"

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "create",
        "--profile-id",
        "english_12_new",
        "--title",
        "English 12 New",
        "--standard",
        "njsls-ela:RI.CR.11-12.1",
        "--standard",
        "njsls-ela:RL.CR.11-12.1",
        capsys=capsys,
    )

    assert code == 0
    assert out == "Created standards profile english_12_new.\n"
    assert err == ""
    created = load_standards_library(library_path)
    assert created.profiles[0].standards == (
        "njsls-ela:RI.CR.11-12.1",
        "njsls-ela:RL.CR.11-12.1",
    )
    before = library_path.read_text(encoding="utf-8")

    for command_args, expected_error in (
        (
            (
                "--profile-id",
                "english_12_new",
                "--standard",
                "njsls-ela:RL.CR.11-12.1",
            ),
            "duplicate",
        ),
        (
            ("--profile-id", "unknown_profile", "--standard", "missing:standard"),
            "unknown standard IDs",
        ),
        (
            (
                "--profile-id",
                "duplicate_membership",
                "--standard",
                "njsls-ela:RL.CR.11-12.1",
                "--standard",
                "njsls-ela:RL.CR.11-12.1",
            ),
            "duplicate standard IDs",
        ),
        (("--profile-id", " "), "profile_id"),
    ):
        code, out, err = run_cli(
            tmp_path,
            "standards",
            "profile",
            "create",
            *command_args,
            capsys=capsys,
        )

        assert code == 1
        assert out == ""
        assert expected_error in err
        assert library_path.read_text(encoding="utf-8") == before


def test_profile_replace_clears_metadata_and_replaces_membership(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    library_path = tmp_path / "standards" / "library.json"

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "replace",
        "english_12_njsls",
        "--standard",
        "local-writing:evidence_explanation",
        capsys=capsys,
    )

    assert code == 0
    assert out == "Replaced standards profile english_12_njsls.\n"
    assert err == ""
    replaced = load_standards_library(library_path).profiles[0]
    assert replaced.profile_id == "english_12_njsls"
    assert replaced.standards == ("local-writing:evidence_explanation",)
    assert replaced.title is None
    assert replaced.source is None
    before = library_path.read_text(encoding="utf-8")

    for command_args, expected_error in (
        (("missing_profile",), "missing"),
        (("english_12_njsls", "--standard", "missing:standard"), "unknown"),
        (
            (
                "english_12_njsls",
                "--standard",
                "njsls-ela:RL.CR.11-12.1",
                "--standard",
                "njsls-ela:RL.CR.11-12.1",
            ),
            "duplicate standard IDs",
        ),
    ):
        code, out, err = run_cli(
            tmp_path,
            "standards",
            "profile",
            "replace",
            *command_args,
            capsys=capsys,
        )

        assert code == 1
        assert out == ""
        assert expected_error in err
        assert library_path.read_text(encoding="utf-8") == before


def test_profile_add_and_remove_standard_preserve_order_and_definitions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    library = make_cli_library()
    write_workspace_standards_library(tmp_path, library)
    library_path = tmp_path / "standards" / "library.json"

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "add-standard",
        "english_12_local",
        "njsls-ela:RL.CR.11-12.1",
        capsys=capsys,
    )

    assert code == 0
    assert out == (
        "Added standard njsls-ela:RL.CR.11-12.1 to profile english_12_local.\n"
    )
    assert err == ""
    updated = load_standards_library(library_path)
    assert updated.profiles[1].standards == (
        "local-writing:evidence_explanation",
        "njsls-ela:RL.CR.11-12.1",
    )
    before = library_path.read_text(encoding="utf-8")

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "remove-standard",
        "english_12_local",
        "local-writing:evidence_explanation",
        capsys=capsys,
    )

    assert code == 0
    assert out == (
        "Removed standard local-writing:evidence_explanation from profile "
        "english_12_local.\n"
    )
    assert err == ""
    updated = load_standards_library(library_path)
    assert updated.profiles[1].standards == ("njsls-ela:RL.CR.11-12.1",)
    assert tuple(definition.standard_id for definition in updated.standards) == (
        tuple(definition.standard_id for definition in library.standards)
    )
    assert not (tmp_path / "standards" / "usage").exists()

    for command_args, expected_error in (
        (
            (
                "add-standard",
                "english_12_local",
                "njsls-ela:RL.CR.11-12.1",
            ),
            "already contains",
        ),
        (("add-standard", "missing_profile", "njsls-ela:RL.CR.11-12.1"), "not found"),
        (
            ("add-standard", "english_12_local", "missing:standard"),
            "standard not found",
        ),
        (
            (
                "remove-standard",
                "english_12_local",
                "local-writing:evidence_explanation",
            ),
            "does not contain",
        ),
        (
            (
                "remove-standard",
                "missing_profile",
                "njsls-ela:RL.CR.11-12.1",
            ),
            "not found",
        ),
    ):
        before_failure = library_path.read_text(encoding="utf-8")
        code, out, err = run_cli(
            tmp_path,
            "standards",
            "profile",
            *command_args,
            capsys=capsys,
        )

        assert code == 1
        assert out == ""
        assert expected_error in err
        assert library_path.read_text(encoding="utf-8") == before_failure

    assert library_path.read_text(encoding="utf-8") != before


def test_profile_validate_does_not_write_or_create_missing_library(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    library_path = tmp_path / "standards" / "library.json"
    before = library_path.read_text(encoding="utf-8")

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "validate",
        "english_12_njsls",
        capsys=capsys,
    )

    assert code == 0
    assert out == "Standards profile is valid: english_12_njsls\n"
    assert err == ""
    assert library_path.read_text(encoding="utf-8") == before

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "validate",
        "missing_profile",
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "standards profile not found: missing_profile" in err

    empty_workspace = tmp_path / "empty"
    empty_workspace.mkdir()
    code, out, err = run_cli(
        empty_workspace,
        "standards",
        "profile",
        "validate",
        "english_12_njsls",
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "standards profile not found: english_12_njsls" in err
    assert list(empty_workspace.iterdir()) == []


def test_profile_delete_is_not_implemented(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    library_path = tmp_path / "standards" / "library.json"
    before = library_path.read_text(encoding="utf-8")

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "delete",
        "english_12_njsls",
        capsys=capsys,
    )

    assert code == 2
    assert out == ""
    assert "invalid choice: 'delete'" in err
    assert library_path.read_text(encoding="utf-8") == before


def test_profile_export_writes_deterministic_profile_and_refuses_overwrite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    library = make_cli_library()
    write_workspace_standards_library(tmp_path, library)
    export_path = tmp_path / "profiles" / "english_12_njsls.json"

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "export",
        "english_12_njsls",
        str(export_path),
        capsys=capsys,
    )

    assert code == 0
    assert out == (
        f"Exported standards profile english_12_njsls to {export_path}.\n"
    )
    assert err == ""
    assert standards_profile_from_dict(json.loads(export_path.read_text())) == (
        library.profiles[0]
    )
    assert export_path.read_text(encoding="utf-8") == (
        json.dumps(
            standards_profile_to_dict(library.profiles[0]),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    export_path.write_text("keep me", encoding="utf-8")
    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "export",
        "english_12_njsls",
        str(export_path),
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert f"Error: target file already exists: {export_path}" in err
    assert export_path.read_text(encoding="utf-8") == "keep me"


def test_profile_export_fails_for_missing_profile(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "export",
        "missing_profile",
        str(tmp_path / "missing.json"),
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "Standards profile not found: missing_profile" in err


def test_profile_import_add_validates_references_and_duplicate_ids(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    base_library = StandardsLibrary(standards=make_cli_library().standards, profiles=())
    write_workspace_standards_library(tmp_path, base_library)
    profile = make_cli_library().profiles[0]
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(standards_profile_to_dict(profile)),
        encoding="utf-8",
    )

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "import",
        str(profile_path),
        "--add",
        capsys=capsys,
    )

    assert code == 0
    assert out == f"Added standards profile english_12_njsls from {profile_path}.\n"
    assert err == ""
    imported = load_standards_library(tmp_path / "standards" / "library.json")
    assert imported.profiles == (profile,)
    assert not (tmp_path / "standards" / "usage").exists()

    before = (tmp_path / "standards" / "library.json").read_text(encoding="utf-8")
    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "import",
        str(profile_path),
        "--add",
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "duplicate" in err
    assert (tmp_path / "standards" / "library.json").read_text(
        encoding="utf-8"
    ) == before

    bad_profile_path = tmp_path / "bad_profile.json"
    bad_profile_path.write_text(
        json.dumps(
            {
                **standards_profile_to_dict(
                    StandardsProfile(
                        profile_id="bad_profile",
                        standards=("njsls-ela:RL.CR.11-12.1",),
                    )
                ),
                "standards": ["missing:standard"],
            }
        ),
        encoding="utf-8",
    )
    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "import",
        str(bad_profile_path),
        "--add",
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "unknown standard IDs" in err
    assert (tmp_path / "standards" / "library.json").read_text(
        encoding="utf-8"
    ) == before


def test_profile_import_requires_explicit_mode(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_workspace_standards_library(tmp_path, make_cli_library())
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(standards_profile_to_dict(make_cli_library().profiles[0])),
        encoding="utf-8",
    )

    code, out, err = run_cli(
        tmp_path,
        "standards",
        "profile",
        "import",
        str(profile_path),
        capsys=capsys,
    )

    assert code == 2
    assert out == ""
    assert "profile import requires an explicit mode" in err
