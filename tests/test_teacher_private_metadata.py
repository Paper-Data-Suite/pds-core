"""#238 Slice 3A: pure v1 private metadata codecs, no storage operations."""

from __future__ import annotations

import json
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from uuid import UUID

import pytest

from pds_core import _teacher_private_metadata as codec
from pds_core.teacher_experience import get_teacher_experience_capabilities

UUID_A = "6fb32a62-83e2-43f6-9823-687801593c8b"
UUID_B = "d2f5733a-e471-4865-a070-e943ad20863f"


def descriptor() -> codec.PrivateAssociationDescriptor:
    return codec.PrivateAssociationDescriptor(UUID_A)


def registry(
    *,
    kind: str = "posix_euid",
    value: str = "1000",
    root: str = "/synthetic_workspace_a",
) -> codec.PrivateRegistry:
    return codec.PrivateRegistry(
        owner=codec.PrivateRegistryOwner(kind=kind, value=value),  # type: ignore[arg-type]
        revision=1,
        bindings=(
            codec.PrivateRegistryBinding(
                association_id=UUID_A,
                binding_revision=1,
                accepted_root=root,
            ),
        ),
    )


def as_json(value: object) -> bytes:
    return json.dumps(value).encode("utf-8")


def mutate_encoded(data: bytes, **changes: object) -> bytes:
    obj = json.loads(data)
    obj.update(changes)
    return as_json(obj)


def reject(
    function: object,
    data: bytes,
    code: codec.PrivateMetadataErrorCode,
) -> None:
    assert callable(function)
    with pytest.raises(codec.PrivateMetadataError) as result:
        function(data)
    assert result.value.code is code
    assert "synthetic_workspace" not in str(result.value)
    assert "1000" not in str(result.value)


def test_descriptor_exact_canonical_utf8_roundtrip() -> None:
    original = descriptor()
    encoded = codec.encode_association_descriptor(original)
    assert encoded.endswith(b"\n")
    assert b'"version": 1' in encoded
    assert codec.decode_association_descriptor(encoded) == original
    assert (
        codec.encode_association_descriptor(
            codec.decode_association_descriptor(encoded)
        )
        == encoded
    )


def test_registry_exact_canonical_utf8_roundtrip() -> None:
    original = registry()
    encoded = codec.encode_private_registry(original)
    assert codec.decode_private_registry(encoded) == original
    assert (
        codec.encode_private_registry(codec.decode_private_registry(encoded)) == encoded
    )
    assert "synthetic_workspace_a" not in repr(original)
    assert "1000" not in repr(original)
    assert "synthetic_workspace_a" not in repr(original.bindings[0])
    assert "1000" not in repr(original.owner)


def test_windows_owner_syntax_and_absolute_drive_path() -> None:
    original = registry(
        kind="windows_token_sid",
        value="S-1-5-21-1000-2000-3000-1001",
        root="C:\\PDS\\Synthetic Workspace",
    )
    assert (
        codec.decode_private_registry(codec.encode_private_registry(original))
        == original
    )


def test_registry_can_be_empty_without_implying_notes_records() -> None:
    empty = codec.PrivateRegistry(
        owner=codec.PrivateRegistryOwner("posix_euid", "0"),
        revision=1,
        bindings=(),
    )
    assert codec.decode_private_registry(codec.encode_private_registry(empty)) == empty


def test_dataclasses_are_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        descriptor().association_id = UUID_B  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        registry().revision = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    "identity",
    [
        "",
        "6FB32A62-83E2-43F6-9823-687801593C8B",
        "6fb32a62-83e2-13f6-9823-687801593c8b",
        "00000000-0000-4000-8000-000000000000\n",
        "../../relative",
        True,
        None,
        123,
    ],
)
def test_rejects_noncanonical_or_non_v4_identity(identity: object) -> None:
    with pytest.raises(codec.PrivateMetadataError) as error:
        codec.PrivateAssociationDescriptor(identity)  # type: ignore[arg-type]
    assert error.value.code is codec.PrivateMetadataErrorCode.INVALID_IDENTITY


@pytest.mark.parametrize("bad", [0, -1, 1.0, "1", None, True])
def test_rejects_nonpositive_nonint_revisions(bad: object) -> None:
    with pytest.raises(codec.PrivateMetadataError):
        codec.PrivateRegistry(
            owner=codec.PrivateRegistryOwner("posix_euid", "1000"),
            revision=bad,  # type: ignore[arg-type]
            bindings=(),
        )
    with pytest.raises(codec.PrivateMetadataError):
        codec.PrivateRegistryBinding(
            association_id=UUID_A,
            binding_revision=bad,  # type: ignore[arg-type]
            accepted_root="/synthetic",
        )


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("posix_euid", "001"),
        ("posix_euid", "-1"),
        ("posix_euid", "1000\n"),
        ("posix_euid", "teacher"),
        ("windows_token_sid", "S-1-5-21-user"),
        ("windows_token_sid", "s-1-5-21-123"),
        ("actor_reference", "1000"),
    ],
)
def test_invalid_owner_identity_refused(kind: str, value: str) -> None:
    with pytest.raises(codec.PrivateMetadataError) as error:
        codec.PrivateRegistryOwner(kind=kind, value=value)  # type: ignore[arg-type]
    assert error.value.code is codec.PrivateMetadataErrorCode.INVALID_IDENTITY


@pytest.mark.parametrize(
    "root",
    [
        "relative/root",
        "",
        "../workspace",
        "/synthetic/../escape",
        "/synthetic/./a",
        "/synthetic\nworkspace",
        "/synthetic\ud800",
        "//network/drive",
        "/synthetic\x1b[31m",
    ],
)
def test_invalid_posix_binding_root_refused(root: str) -> None:
    with pytest.raises(codec.PrivateMetadataError):
        registry(root=root)


@pytest.mark.parametrize(
    "root", ["relative", "\\\\server\\share", "C:relative", "C:\\a\\..\\b"]
)
def test_invalid_windows_binding_root_refused(root: str) -> None:
    with pytest.raises(codec.PrivateMetadataError):
        registry(kind="windows_token_sid", value="S-1-5-21-1", root=root)


def test_duplicate_association_ids_refused() -> None:
    original = registry()
    with pytest.raises(codec.PrivateMetadataError) as result:
        codec.PrivateRegistry(
            owner=original.owner,
            revision=1,
            bindings=(original.bindings[0], original.bindings[0]),
        )
    assert result.value.code is codec.PrivateMetadataErrorCode.DUPLICATE_ASSOCIATION


def test_two_independent_associations_are_not_merged() -> None:
    original = registry()
    second = codec.PrivateRegistryBinding(
        association_id=UUID_B,
        binding_revision=1,
        accepted_root="/synthetic_workspace_b",
    )
    extended = codec.PrivateRegistry(original.owner, 2, (original.bindings[0], second))
    assert (
        len(
            codec.decode_private_registry(
                codec.encode_private_registry(extended)
            ).bindings
        )
        == 2
    )


@pytest.mark.parametrize("invalid", [None, {}, [], 123, "text", b"", b"{", b"\xff"])
def test_descriptor_rejects_invalid_source_without_secret_leak(invalid: object) -> None:
    with pytest.raises(codec.PrivateMetadataError):
        codec.decode_association_descriptor(invalid)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "source", [b'{"schema":"a","schema":"b"}', b'{"version": NaN}', b"\xef\xbb\xbf{}"]
)
def test_duplicate_keys_nonfinite_and_bom_rejected(source: bytes) -> None:
    with pytest.raises(codec.PrivateMetadataError):
        codec.decode_association_descriptor(source)


def test_duplicate_nested_owner_keys_refused() -> None:
    original = codec.encode_private_registry(registry())
    duped = original.replace(
        b'"kind": "posix_euid",', b'"kind": "posix_euid", "kind": "posix_euid",'
    )
    reject(
        codec.decode_private_registry,
        duped,
        codec.PrivateMetadataErrorCode.DUPLICATE_KEY,
    )


def test_invalid_descriptor_version_does_not_get_migrated() -> None:
    invalid = mutate_encoded(
        codec.encode_association_descriptor(descriptor()), version=2
    )
    reject(
        codec.decode_association_descriptor,
        invalid,
        codec.PrivateMetadataErrorCode.UNSUPPORTED_VERSION,
    )


def test_bool_version_is_not_integer_version() -> None:
    invalid = mutate_encoded(
        codec.encode_association_descriptor(descriptor()), version=True
    )
    reject(
        codec.decode_association_descriptor,
        invalid,
        codec.PrivateMetadataErrorCode.INVALID_SHAPE,
    )


def test_unknown_field_is_not_silently_preserved_or_discarded() -> None:
    invalid = mutate_encoded(
        codec.encode_association_descriptor(descriptor()), teacher="private"
    )
    reject(
        codec.decode_association_descriptor,
        invalid,
        codec.PrivateMetadataErrorCode.INVALID_SHAPE,
    )


def test_registry_invalid_nested_shape_is_rejected() -> None:
    invalid = mutate_encoded(
        codec.encode_private_registry(registry()), owner={"kind": "posix_euid"}
    )
    reject(
        codec.decode_private_registry,
        invalid,
        codec.PrivateMetadataErrorCode.INVALID_SHAPE,
    )


def test_registry_binding_extra_key_is_rejected() -> None:
    original = json.loads(codec.encode_private_registry(registry()))
    original["bindings"][0]["notes"] = "hidden"
    reject(
        codec.decode_private_registry,
        as_json(original),
        codec.PrivateMetadataErrorCode.INVALID_SHAPE,
    )


def test_registry_unknown_version_refused_before_owner_read() -> None:
    invalid = mutate_encoded(codec.encode_private_registry(registry()), version=7)
    reject(
        codec.decode_private_registry,
        invalid,
        codec.PrivateMetadataErrorCode.UNSUPPORTED_VERSION,
    )


def test_size_limits_fail_before_parse_and_serialize() -> None:
    with pytest.raises(codec.PrivateMetadataError) as error:
        codec.decode_association_descriptor(b" " * (codec.MAX_ASSOCIATION_BYTES + 1))
    assert error.value.code is codec.PrivateMetadataErrorCode.SIZE_LIMIT
    with pytest.raises(codec.PrivateMetadataError) as error:
        codec.decode_private_registry(b" " * (codec.MAX_REGISTRY_BYTES + 1))
    assert error.value.code is codec.PrivateMetadataErrorCode.SIZE_LIMIT


def test_binding_count_limit_is_enforced_before_iteration() -> None:
    base = registry()
    oversize = (base.bindings[0],) * (codec.MAX_REGISTRY_BINDINGS + 1)
    with pytest.raises(codec.PrivateMetadataError) as error:
        codec.PrivateRegistry(base.owner, 1, oversize)
    assert error.value.code is codec.PrivateMetadataErrorCode.SIZE_LIMIT


def test_registry_rejects_nonprintable_fingerprint() -> None:
    with pytest.raises(codec.PrivateMetadataError):
        codec.PrivateRegistryBinding(UUID_A, 1, "/synthetic", "private\nsecret")


def test_codec_invariants_are_pure_and_do_not_create_workspaces(tmp_path: Path) -> None:
    before = list(tmp_path.iterdir())
    assert codec.decode_association_descriptor(
        codec.encode_association_descriptor(descriptor())
    )
    assert codec.decode_private_registry(codec.encode_private_registry(registry()))
    assert list(tmp_path.iterdir()) == before


def test_existing_teacher_capabilities_remain_negative() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )


def test_import_has_no_file_or_user_lookups(tmp_path: Path) -> None:
    # A fresh Python -B process also checks no access to working directory.
    import os
    import subprocess

    code = (
        "from pds_core._teacher_private_metadata import "
        "decode_private_registry, encode_private_registry; "
        "assert callable(decode_private_registry) and callable(encode_private_registry)"
    )
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    repo = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = str(repo)
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=tmp_path,
        env=env,
        input="",
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    assert list(tmp_path.iterdir()) == []


def test_uuid_test_values_are_actual_v4() -> None:
    assert UUID(UUID_A).version == UUID(UUID_B).version == 4
