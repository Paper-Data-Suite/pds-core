"""Core #238 3G25: read-only protected Windows handle mask compatibility."""

from __future__ import annotations

import ast
import inspect
import textwrap
from dataclasses import FrozenInstanceError
from typing import Callable, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_registry_image_snapshot as registry_image
from pds_core import _teacher_private_retained_descriptor_guard as descriptor_guard
from pds_core import _teacher_private_retained_journal_guard as journal_guard
from pds_core import _teacher_private_retained_registry_guard as registry_guard
from pds_core import _teacher_private_windows_handle_contract_review as contract

Role = contract.PrivateWindowsHandleRole
State = contract.PrivateWindowsHandleContractState
Observation = contract.PrivateWindowsHandleObservation


def _correct() -> tuple[Observation, ...]:
    return tuple(
        Observation(role, access, share) for role, access, share in contract._EXPECTED
    )


def _native_open_call(function: Callable[..., object]) -> ast.Call:
    # Inspect committed Python helper code, not user-provided files or paths.
    parsed = ast.parse(textwrap.dedent(inspect.getsource(function)))
    found = [
        item
        for item in ast.walk(parsed)
        if isinstance(item, ast.Call)
        and isinstance(item.func, ast.Attribute)
        and isinstance(item.func.value, ast.Name)
        and item.func.value.id == "kernel"
        and item.func.attr == "CreateFileW"
    ]
    assert len(found) == 1
    assert len(found[0].args) == 7
    return found[0]


def _constant(arg: ast.expr) -> int:
    # Numeric literals and the BitOr combination used by the reviewed helpers.
    if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.BitOr):
        return _constant(arg.left) | _constant(arg.right)
    value = ast.literal_eval(arg)
    assert type(value) is int
    return value


def _source_open_masks(function: Callable[..., object]) -> tuple[int, int]:
    call = _native_open_call(function)
    return _constant(call.args[1]), _constant(call.args[2])


def test_contract_matches_reviewed_windows_helpers() -> None:
    # Original opener is reused for retained journal AND registry guards.
    # Descriptor opener is reused for workspace .pds AND its sidecar.
    captured = {
        Role.JOURNAL_DIRECTORY: _source_open_masks(anchor._windows_open),
        Role.RETAINED_REGISTRY: _source_open_masks(anchor._windows_open),
        Role.DESCRIPTOR_DIRECTORY: _source_open_masks(descriptor._windows_open),
        Role.RETAINED_DESCRIPTOR: _source_open_masks(descriptor._windows_open),
        Role.REGISTRY_IMAGE_READ: _source_open_masks(registry_image._read_windows),
    }
    values = tuple(Observation(role, *captured[role]) for role in Role)
    result = contract.review_native_private_windows_handle_contracts(values)
    assert result.state is State.ADVISORY_SHARING_REVIEW_REQUIRED


def test_journal_registry_descriptor_guards_retain_same_source_openers() -> None:
    assert "anchor._windows_open" in inspect.getsource(journal_guard._held_windows)
    assert "anchor._windows_open" in inspect.getsource(
        registry_guard._held_windows_registry
    )
    assert "descriptor._windows_open" in inspect.getsource(
        descriptor_guard._held_windows_descriptor
    )
    assert "descriptor._windows_open" in inspect.getsource(
        descriptor_guard._windows_check
    )
    assert "anchor._windows_open" in inspect.getsource(registry_guard._windows_check)
    assert "anchor._windows_open" in inspect.getsource(journal_guard._windows_check)


def test_valid_baseline_is_read_only_advisory_not_mutation_authority() -> None:
    result = contract.review_native_private_windows_handle_contracts(_correct())
    assert result.state is State.ADVISORY_SHARING_REVIEW_REQUIRED
    assert "No production mutation" in result.message
    assert all(
        not hasattr(result, name)
        for name in ("token", "permit", "path", "handle", "owner", "bytes")
    )
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", State.INVALID_REQUEST)


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("delta", [1, 2, 4, 8, 0x10000])
def test_every_access_mask_drift_refused(role: Role, delta: int) -> None:
    changed = tuple(
        Observation(
            x.role,
            x.desired_access ^ delta if x.role is role else x.desired_access,
            x.share_mask,
        )
        for x in _correct()
    )
    assert (
        contract.review_native_private_windows_handle_contracts(changed).state
        is State.CONTRACT_DRIFT_PRESERVE
    )


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("share", [0, 1, 2, 3, 4, 5, 6, 7])
def test_share_mask_mismatch_is_preserved(role: Role, share: int) -> None:
    expected = next(x.share_mask for x in _correct() if x.role is role)
    changed = tuple(
        Observation(x.role, x.desired_access, share if x.role is role else x.share_mask)
        for x in _correct()
    )
    outcome = contract.review_native_private_windows_handle_contracts(changed).state
    assert outcome is (
        State.ADVISORY_SHARING_REVIEW_REQUIRED
        if share == expected
        else State.CONTRACT_DRIFT_PRESERVE
    )


@pytest.mark.parametrize("share", [-1, 8, 15, 0x100])
def test_out_of_range_sharing_refused(share: int) -> None:
    items = list(_correct())
    first = items[0]
    items[0] = Observation(first.role, first.desired_access, share)
    assert (
        contract.review_native_private_windows_handle_contracts(tuple(items)).state
        is State.INVALID_REQUEST
    )


@pytest.mark.parametrize("access", [-1, 0x100000000, True, 0.5, "read"])
def test_invalid_access_refused(access: object) -> None:
    items = list(_correct())
    first = items[0]
    items[0] = Observation(first.role, cast(int, access), first.share_mask)
    assert (
        contract.review_native_private_windows_handle_contracts(tuple(items)).state
        is State.INVALID_REQUEST
    )


@pytest.mark.parametrize("invalid", [None, [], "mask", {}, (), (None,)])
def test_invalid_envelope_refused(invalid: object) -> None:
    assert (
        contract.review_native_private_windows_handle_contracts(
            cast(tuple[Observation, ...], invalid)
        ).state
        is State.INVALID_REQUEST
    )


def test_duplicate_role_is_not_a_complete_contract() -> None:
    items = list(_correct())
    items[0] = items[1]
    assert (
        contract.review_native_private_windows_handle_contracts(tuple(items)).state
        is State.INCOMPLETE_OR_DUPLICATE_REFUSED
    )


def test_order_does_not_change_contract() -> None:
    assert (
        contract.review_native_private_windows_handle_contracts(
            tuple(reversed(_correct()))
        ).state
        is State.ADVISORY_SHARING_REVIEW_REQUIRED
    )


def test_share_delete_retained_guards_are_not_an_exclusive_mutation_fence() -> None:
    for item in _correct()[:-1]:
        assert item.share_mask & 0x4
    assert _correct()[-1].share_mask == 0x1
    assert (
        contract.review_native_private_windows_handle_contracts(_correct()).state
        is State.ADVISORY_SHARING_REVIEW_REQUIRED
    )


def test_no_public_write_path_or_notes_activation() -> None:
    source = inspect.getsource(contract)
    for marker in ("os.replace(", "unlink(", "write_bytes(", "CreateFileW(", "Commit("):
        assert marker not in source
    assert not hasattr(contract, "commit_private_registry")


def test_contract_metadata_does_not_contain_user_paths() -> None:
    result = contract.review_native_private_windows_handle_contracts(_correct())
    assert "C:/" not in result.message and "/home/" not in result.message
    assert all(isinstance(item.role.value, str) for item in _correct())
