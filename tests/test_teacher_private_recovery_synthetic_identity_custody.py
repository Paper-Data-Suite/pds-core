"""Core #238 Slice 3G20: real disposable file identity/lock continuity tests."""

from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_recovery_synthetic_identity_custody as custody
from pds_core import _teacher_private_recovery_synthetic_native_writer as scratch

Fault = custody.PrivateSyntheticIdentityInterruption
State = custody.PrivateSyntheticIdentityState


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native identity")
def test_native_synthetic_replacement_observes_identity_but_not_durability() -> None:
    result = custody.rehearse_synthetic_private_identity_custody()
    assert result.state is State.IDENTITY_OBSERVED_PERSISTENCE_UNQUALIFIED
    assert "durability" in result.message
    assert not any(
        hasattr(result, name)
        for name in ("root", "path", "id", "identity", "handle", "bytes", "token")
    )
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", State.IO_ERROR)


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native identity")
@pytest.mark.parametrize("fault", list(Fault)[1:])
def test_every_injected_interrupt_is_preserve(fault: Fault) -> None:
    result = custody.rehearse_synthetic_private_identity_custody(fault)
    assert result.state is State.INTERRUPTED_PRESERVE


@pytest.mark.parametrize(
    "invalid", [None, False, True, 0, 1, 1.5, "none", [], {}, (), object()]
)
def test_invalid_request_does_not_allocate_scratch(
    monkeypatch: pytest.MonkeyPatch, invalid: object
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("no scratch on invalid input")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", refuse)
    assert (
        custody.rehearse_synthetic_private_identity_custody(cast(Fault, invalid)).state
        is State.INVALID_REQUEST
    )


def test_unsupported_platform_allocates_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("no scratch on unsupported platform")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", refuse)
    assert (
        custody.rehearse_synthetic_private_identity_custody().state is State.UNSUPPORTED
    )


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native identity")
@pytest.mark.parametrize("fault", list(Fault))
def test_scratch_scope_is_fixed_and_disposed(
    monkeypatch: pytest.MonkeyPatch, fault: Fault
) -> None:
    seen: list[Path] = []
    original = scratch._write_new

    def watch(root: Path, name: str, raw: bytes) -> None:
        seen.append(root)
        assert root.name.startswith("core238_3g20_identity_")
        assert name in {
            "registry.json",
            ".synthetic.registry-stage",
            "descriptor.json",
            "transactions.json",
        }
        original(root, name, raw)

    monkeypatch.setattr(scratch, "_write_new", watch)
    custody.rehearse_synthetic_private_identity_custody(fault)
    assert len(seen) == 4 and len(set(seen)) == 1
    assert not seen[0].exists()


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native identity")
def test_real_identity_matches_open_fd_without_leaking_handle() -> None:
    with tempfile.TemporaryDirectory(prefix="core238_test_3g20_") as root_str:
        root = Path(root_str)
        (root / "entry").write_bytes(b"synthetic")
        file_id = custody._identity(root, "entry")
        detail = (root / "entry").lstat()
        assert file_id == (detail.st_dev, detail.st_ino)
        assert all(type(i) is int for i in file_id)
        (root / "entry").unlink()
        assert not (root / "entry").exists()


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native identity")
@pytest.mark.parametrize(
    "name",
    [
        "registry.json",
        "descriptor.json",
        "transactions.json",
        ".synthetic.registry-stage",
    ],
)
def test_preimage_corruption_refuses_operation(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    original_write = scratch._write_new
    called = False

    def corrupted(root: Path, entry: str, raw: bytes) -> None:
        original_write(root, entry, raw + b"BAD" if entry == name else raw)

    def no_replace(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True
        raise AssertionError("replace called on unsafe preimage")

    monkeypatch.setattr(scratch, "_write_new", corrupted)
    monkeypatch.setattr(os, "replace", no_replace)
    result = custody.rehearse_synthetic_private_identity_custody()
    assert result.state is State.PREIMAGE_REFUSED and not called


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native identity")
def test_byte_identical_copy_instead_of_rename_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def counterfeit(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        Path(target).write_bytes(scratch._AFTER)
        Path(source).unlink()

    monkeypatch.setattr(os, "replace", counterfeit)
    assert (
        custody.rehearse_synthetic_private_identity_custody().state
        is State.IDENTITY_CONFLICT_PRESERVE
    )


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native identity")
@pytest.mark.parametrize("name", ["descriptor.json", "transactions.json"])
def test_byte_identical_secondary_replacement_detected(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    original_replace = os.replace

    def counterfeit(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        original_replace(source, target)
        other = Path(target).parent / name
        previous = other.read_bytes()
        other.unlink()
        other.write_bytes(previous)

    monkeypatch.setattr(os, "replace", counterfeit)
    assert (
        custody.rehearse_synthetic_private_identity_custody().state
        is State.IDENTITY_CONFLICT_PRESERVE
    )


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native identity")
def test_registry_replaced_after_sync_with_same_bytes_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = scratch._sync_target

    def counterfeit(root: Path) -> None:
        original(root)
        registry = root / scratch._REGISTRY
        expected = registry.read_bytes()
        registry.unlink()
        registry.write_bytes(expected)

    monkeypatch.setattr(scratch, "_sync_target", counterfeit)
    assert (
        custody.rehearse_synthetic_private_identity_custody().state
        is State.IDENTITY_CONFLICT_PRESERVE
    )


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native identity")
@pytest.mark.parametrize(
    "name", ["registry.json", "descriptor.json", "transactions.json"]
)
def test_changed_postimage_bytes_refuse_success(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    original_replace = os.replace

    def corrupt(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        original_replace(source, target)
        (Path(target).parent / name).write_bytes(b"CHANGED")

    monkeypatch.setattr(os, "replace", corrupt)
    assert (
        custody.rehearse_synthetic_private_identity_custody().state
        is State.POSTIMAGE_CONFLICT_PRESERVE
    )


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native identity")
def test_missing_identity_is_not_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_id(_root: Path, _name: str) -> tuple[int, int]:
        raise custody._IdentityUnavailable

    monkeypatch.setattr(custody, "_identity", no_id)
    assert (
        custody.rehearse_synthetic_private_identity_custody().state
        is State.IDENTITY_UNAVAILABLE
    )


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native identity")
def test_duplicate_identity_is_not_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def duplicate(_root: Path, _name: str) -> tuple[int, int]:
        return (1, 1)

    monkeypatch.setattr(custody, "_identity", duplicate)
    assert (
        custody.rehearse_synthetic_private_identity_custody().state
        is State.IDENTITY_UNAVAILABLE
    )


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native identity")
def test_lockfile_identity_drift_refuses_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actual = custody._identity
    seen = 0

    def displaced(root: Path, name: str) -> tuple[int, int]:
        nonlocal seen
        identity = actual(root, name)
        if name == scratch._LOCK:
            seen += 1
            if seen == 2:
                return identity[0], identity[1] + 1
        return identity

    monkeypatch.setattr(custody, "_identity", displaced)
    assert (
        custody.rehearse_synthetic_private_identity_custody().state
        is State.IDENTITY_CONFLICT_PRESERVE
    )
    assert seen >= 4


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native identity")
def test_native_lock_failure_prevents_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def refused(_path: Path) -> Iterator[None]:
        raise scratch._GuardRefused
        yield

    def no_replace(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("replace without guard")

    monkeypatch.setattr(scratch, "_scratch_lock", refused)
    monkeypatch.setattr(os, "replace", no_replace)
    assert (
        custody.rehearse_synthetic_private_identity_custody().state
        is State.NATIVE_GUARD_REFUSED
    )


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native identity")
def test_actual_keyboard_interrupt_does_not_claim_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupted(_root: Path) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(scratch, "_sync_target", interrupted)
    assert (
        custody.rehearse_synthetic_private_identity_custody().state
        is State.INTERRUPTED_PRESERVE
    )


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native identity")
def test_file_sync_failure_is_not_durable_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refused(_root: Path) -> None:
        raise OSError("scratch sync denied")

    monkeypatch.setattr(scratch, "_sync_target", refused)
    assert custody.rehearse_synthetic_private_identity_custody().state is State.IO_ERROR


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native identity")
def test_guard_is_live_during_replace_postchecks_and_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_guard = scratch._scratch_lock
    original_replace = os.replace
    original_sync = scratch._sync_target
    original_identity = custody._identity
    active = False
    counts = {"replace": 0, "identity": 0, "sync": 0}

    @contextmanager
    def guarded(path: Path) -> Iterator[None]:
        nonlocal active
        with original_guard(path):
            active = True
            try:
                yield
            finally:
                active = False

    def replacement(src: os.PathLike[str], dst: os.PathLike[str]) -> None:
        assert active
        counts["replace"] += 1
        original_replace(src, dst)

    def identified(root: Path, name: str) -> tuple[int, int]:
        assert active
        counts["identity"] += 1
        return original_identity(root, name)

    def synced(root: Path) -> None:
        assert active
        counts["sync"] += 1
        original_sync(root)

    monkeypatch.setattr(scratch, "_scratch_lock", guarded)
    monkeypatch.setattr(os, "replace", replacement)
    monkeypatch.setattr(custody, "_identity", identified)
    monkeypatch.setattr(scratch, "_sync_target", synced)
    answer = custody.rehearse_synthetic_private_identity_custody()
    assert answer.state is State.IDENTITY_OBSERVED_PERSISTENCE_UNQUALIFIED
    assert not active
    assert counts["replace"] == 1 and counts["sync"] == 1
    assert counts["identity"] >= 16


@pytest.mark.parametrize("candidate", list(State))
def test_every_result_message_is_fixed_and_sanitized(candidate: State) -> None:
    result = custody._result(candidate)
    assert result.message
    assert result.state is candidate
    assert "C:" not in result.message and "/tmp/" not in result.message
