"""Core #238 Slice 3B4: pure, strict transaction-intent journal envelope."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_transaction_intent as intent
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

UUID_A = "6fb32a62-83e2-43f6-9823-687801593c8b"
UUID_B = "d2f5733a-e471-4865-a070-e943ad20863f"
UUID_TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
ROOT_A = "/synthetic_workspace_a"
ROOT_B = "/synthetic_workspace_b"


def _sha(raw: bytes | None) -> str | None:
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def _descriptor(association_id: str) -> bytes:
    return metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(association_id)
    )


def _registry(
    revision: int,
    items: tuple[metadata.PrivateRegistryBinding, ...],
) -> bytes:
    return metadata.encode_private_registry(
        metadata.PrivateRegistry(
            metadata.PrivateRegistryOwner("posix_euid", "1000"), revision, items
        )
    )


def _binding(
    association_id: str, root: str, revision: int = 1
) -> metadata.PrivateRegistryBinding:
    return metadata.PrivateRegistryBinding(association_id, revision, root)


def _journal(
    operation: witness.PrivateBindingOperation,
    *,
    existing_registry: bool = True,
) -> intent.PrivateTransactionIntent:
    before_descriptor: bytes | None
    before_registry: bytes | None
    if operation is witness.PrivateBindingOperation.INITIALIZE:
        before_descriptor = None
        before_registry = (
            _registry(3, (_binding(UUID_A, ROOT_A),)) if existing_registry else None
        )
        after_descriptor = _descriptor(UUID_B)
        after_registry = _registry(
            4 if existing_registry else 1,
            (_binding(UUID_A, ROOT_A), _binding(UUID_B, ROOT_B))
            if existing_registry
            else (_binding(UUID_B, ROOT_B),),
        )
        old_id = None
        new_id = UUID_B
    elif operation is witness.PrivateBindingOperation.REBIND_MOVE:
        before_descriptor = _descriptor(UUID_A)
        after_descriptor = before_descriptor
        before_registry = _registry(2, (_binding(UUID_A, ROOT_A),))
        after_registry = _registry(3, (_binding(UUID_A, ROOT_B, 2),))
        old_id = new_id = UUID_A
    else:
        before_descriptor = _descriptor(UUID_A)
        after_descriptor = _descriptor(UUID_B)
        before_registry = _registry(2, (_binding(UUID_A, ROOT_A),))
        after_registry = _registry(
            3, (_binding(UUID_A, ROOT_A), _binding(UUID_B, ROOT_B))
        )
        old_id, new_id = UUID_A, UUID_B
    before_revision = (
        metadata.decode_private_registry(before_registry).revision
        if before_registry is not None
        else 0
    )
    intent_witness = witness.PrivateTransactionWitness(
        operation=operation,
        transaction_id=UUID_TX,
        association_before=old_id,
        association_after=new_id,
        registry_revision_before=before_revision,
        registry_revision_after=before_revision + 1,
        descriptor_sha256_before=_sha(before_descriptor),
        descriptor_sha256_after=_sha(after_descriptor) or "",
        registry_sha256_before=_sha(before_registry),
        registry_sha256_after=_sha(after_registry) or "",
    )
    return intent.PrivateTransactionIntent(
        intent_witness,
        before_descriptor,
        after_descriptor,
        before_registry,
        after_registry,
    )


def _mutate(encoded: bytes, **changes: object) -> bytes:
    data = json.loads(encoded)
    data.update(changes)
    return json.dumps(data).encode("utf-8")


@pytest.mark.parametrize("operation", list(witness.PrivateBindingOperation))
def test_all_three_operations_roundtrip_and_are_deterministic(
    operation: witness.PrivateBindingOperation,
) -> None:
    original = _journal(operation)
    raw = intent.encode_private_transaction_intent(original)
    assert raw.endswith(b"\n")
    assert intent.decode_private_transaction_intent(raw) == original
    assert (
        intent.encode_private_transaction_intent(
            intent.decode_private_transaction_intent(raw)
        )
        == raw
    )


def test_initialize_with_no_prior_registry_roundtrip() -> None:
    original = _journal(
        witness.PrivateBindingOperation.INITIALIZE, existing_registry=False
    )
    assert original.registry_before is None
    assert original.descriptor_before is None
    assert (
        intent.decode_private_transaction_intent(
            intent.encode_private_transaction_intent(original)
        )
        == original
    )


def test_private_metadata_not_in_repr_or_error_message() -> None:
    record = _journal(witness.PrivateBindingOperation.FORK_COPY)
    representation = repr(record)
    assert "synthetic_workspace" not in representation
    assert "1000" not in representation
    assert UUID_A not in representation
    assert UUID_TX not in representation
    with pytest.raises(intent.PrivateIntentError) as caught:
        replace(record, registry_after=b"private secret")
    assert "private secret" not in str(caught.value)
    assert "synthetic" not in str(caught.value)


@pytest.mark.parametrize(
    "field",
    [
        "descriptor_before",
        "descriptor_after",
        "registry_before",
        "registry_after",
    ],
)
def test_digest_mismatch_is_refused(field: str) -> None:
    original = _journal(witness.PrivateBindingOperation.FORK_COPY)
    with pytest.raises(intent.PrivateIntentError):
        if field == "descriptor_before":
            replace(original, descriptor_before=b"tampered bytes")
        elif field == "descriptor_after":
            replace(original, descriptor_after=b"tampered bytes")
        elif field == "registry_before":
            replace(original, registry_before=b"tampered bytes")
        elif field == "registry_after":
            replace(original, registry_after=b"tampered bytes")
        else:
            raise AssertionError("Unknown test field")


def test_invalid_matching_hashes_still_refused_by_nested_metadata_codec() -> None:
    original = _journal(witness.PrivateBindingOperation.FORK_COPY)
    forged = b'{"schema":"future-version"}'
    changed_witness = replace(
        original.witness, registry_sha256_after=_sha(forged) or ""
    )
    with pytest.raises(intent.PrivateIntentError):
        replace(original, witness=changed_witness, registry_after=forged)


def test_registry_owner_change_is_refused_even_if_hashes_match() -> None:
    original = _journal(witness.PrivateBindingOperation.FORK_COPY)
    obj = json.loads(original.registry_after)
    obj["owner"]["value"] = "1001"
    new_bytes = json.dumps(obj).encode("utf-8")
    changed_witness = replace(
        original.witness, registry_sha256_after=_sha(new_bytes) or ""
    )
    with pytest.raises(intent.PrivateIntentError):
        replace(original, witness=changed_witness, registry_after=new_bytes)


def test_rebind_must_preserve_other_bindings_and_increment_binding_revision() -> None:
    original = _journal(witness.PrivateBindingOperation.REBIND_MOVE)
    obj = json.loads(original.registry_after)
    obj["bindings"][0]["binding_revision"] = 1
    new_bytes = json.dumps(obj).encode("utf-8")
    changed_witness = replace(
        original.witness, registry_sha256_after=_sha(new_bytes) or ""
    )
    with pytest.raises(intent.PrivateIntentError):
        replace(original, witness=changed_witness, registry_after=new_bytes)


def test_fork_must_preserve_old_binding_and_use_distinct_root() -> None:
    original = _journal(witness.PrivateBindingOperation.FORK_COPY)
    obj = json.loads(original.registry_after)
    obj["bindings"][1]["accepted_root"] = ROOT_A
    new_bytes = json.dumps(obj).encode("utf-8")
    changed_witness = replace(
        original.witness, registry_sha256_after=_sha(new_bytes) or ""
    )
    with pytest.raises(intent.PrivateIntentError):
        replace(original, witness=changed_witness, registry_after=new_bytes)


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        {},
        "text",
        b"",
        b"{",
        b"\xff",
        b"\xef\xbb\xbf{}",
        pytest.param(b" " * (intent.MAX_INTENT_BYTES + 1), id="oversized-input"),
    ],
)
def test_invalid_or_oversized_source_refused(invalid: object) -> None:
    with pytest.raises(intent.PrivateIntentError):
        intent.decode_private_transaction_intent(invalid)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "extra",
    [
        {"version": 2},
        {"version": True},
        {"schema": "malicious"},
        {"unexpected": "body"},
        {"operation": "overwrite"},
        {"descriptor_after_b64": "%%%"},
        {"registry_after_b64": None},
        {"association_after": "unknown"},
        {"registry_revision_after": 900},
        {"registry_sha256_after": "not-a-digest"},
    ],
)
def test_invalid_fields_refused_without_echo(extra: dict[str, object]) -> None:
    raw = _mutate(
        intent.encode_private_transaction_intent(
            _journal(witness.PrivateBindingOperation.FORK_COPY)
        ),
        **extra,
    )
    with pytest.raises(intent.PrivateIntentError) as error:
        intent.decode_private_transaction_intent(raw)
    assert "synthetic" not in str(error.value)


def test_duplicate_json_keys_are_refused_at_nested_level() -> None:
    raw = intent.encode_private_transaction_intent(
        _journal(witness.PrivateBindingOperation.FORK_COPY)
    )
    duped = raw.replace(b'"version": 1\n', b'"version": 1,\n  "version": 1\n')
    assert duped != raw
    with pytest.raises(intent.PrivateIntentError):
        intent.decode_private_transaction_intent(duped)


def test_noncanonical_base64_is_refused() -> None:
    original = _journal(witness.PrivateBindingOperation.FORK_COPY)
    raw = intent.encode_private_transaction_intent(original)
    candidate = json.loads(raw)
    candidate["descriptor_after_b64"] = (
        base64.b64encode(original.descriptor_after).decode() + "="
    )
    with pytest.raises(intent.PrivateIntentError):
        intent.decode_private_transaction_intent(json.dumps(candidate).encode())


def test_import_only_no_io_and_no_new_capability(tmp_path: Path) -> None:
    before = tuple(tmp_path.iterdir())
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(intent, "write_intent")
    assert not hasattr(intent, "commit_intent")
    assert not hasattr(intent, "create_private_store")
    repo = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repo)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "import pds_core._teacher_private_transaction_intent",
        ],
        cwd=tmp_path,
        env=environment,
        input="",
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""
    assert tuple(tmp_path.iterdir()) == before
