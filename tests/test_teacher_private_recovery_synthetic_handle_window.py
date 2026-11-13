"""3G23: actual disposable open-file handle across one native rename attempt."""

from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import BinaryIO, Iterator, cast

import pytest

from pds_core import _teacher_private_recovery_synthetic_handle_window as window
from pds_core import _teacher_private_recovery_synthetic_identity_custody as identity
from pds_core import _teacher_private_recovery_synthetic_native_writer as scratch

Fault = window.PrivateSyntheticHandleWindowFault
State = window.PrivateSyntheticHandleWindowState


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
def test_real_native_held_target_handle_never_grants_authority() -> None:
    result = window.rehearse_synthetic_private_handle_window()
    assert result.state in {
        State.PATH_REPLACED_OLD_HANDLE_UNQUALIFIED,
        State.OPEN_HANDLE_BLOCKED_REPLACE_UNQUALIFIED,
    }
    assert "production" in result.message or "Native" in result.message
    assert all(
        not hasattr(result, field)
        for field in ("handle", "path", "file_id", "permit", "token", "bytes")
    )
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", State.IO_ERROR)


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
@pytest.mark.parametrize("fault", list(Fault)[1:])
def test_every_interruption_preserves(fault: Fault) -> None:
    assert (
        window.rehearse_synthetic_private_handle_window(fault).state
        is State.INTERRUPTED_PRESERVE
    )


@pytest.mark.parametrize("invalid", [None, False, 0, "none", [], {}, object()])
def test_invalid_fails_before_tempfile(
    monkeypatch: pytest.MonkeyPatch, invalid: object
) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("scratch unexpectedly created")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", refuse)
    assert (
        window.rehearse_synthetic_private_handle_window(cast(Fault, invalid)).state
        is State.INVALID_REQUEST
    )


def test_unsupported_fails_before_tempfile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("scratch unexpectedly created")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", refuse)
    assert window.rehearse_synthetic_private_handle_window().state is State.UNSUPPORTED


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
def test_identity_and_handle_check_stay_inside_one_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = False
    handle_seen = False
    real_lock = scratch._scratch_lock
    real_handle = window._held_image

    @contextmanager
    def guard(path: Path) -> Iterator[None]:
        nonlocal active
        with real_lock(path):
            active = True
            try:
                yield
            finally:
                active = False

    def handle(stream: BinaryIO, old: tuple[int, int]) -> bool:
        nonlocal handle_seen
        assert active
        handle_seen = True
        return real_handle(stream, old)

    monkeypatch.setattr(scratch, "_scratch_lock", guard)
    monkeypatch.setattr(window, "_held_image", handle)
    result = window.rehearse_synthetic_private_handle_window()
    assert not active
    assert handle_seen
    assert result.state in {
        State.PATH_REPLACED_OLD_HANDLE_UNQUALIFIED,
        State.OPEN_HANDLE_BLOCKED_REPLACE_UNQUALIFIED,
    }


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
def test_bad_preimage_prevents_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    real_write = scratch._write_new
    called = False

    def corrupted(root: Path, name: str, value: bytes) -> None:
        real_write(root, name, value + b"x" if name == scratch._REGISTRY else value)

    def refuse_replace(*args: object, **kwargs: object) -> None:
        nonlocal called
        called = True
        raise AssertionError("replace attempted")

    monkeypatch.setattr(scratch, "_write_new", corrupted)
    monkeypatch.setattr(os, "replace", refuse_replace)
    assert (
        window.rehearse_synthetic_private_handle_window().state
        is State.PREIMAGE_REFUSED
    )
    assert not called


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
def test_wrong_held_identity_fails_before_replace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def wrong(_stream: BinaryIO, _old: tuple[int, int]) -> bool:
        return False

    def forbid(*args: object, **kwargs: object) -> None:
        raise AssertionError("replace attempted")

    monkeypatch.setattr(window, "_held_image", wrong)
    monkeypatch.setattr(os, "replace", forbid)
    assert (
        window.rehearse_synthetic_private_handle_window().state
        is State.HANDLE_IDENTITY_CONFLICT_PRESERVE
    )


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
def test_unexpected_replace_error_not_silently_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refused(*args: object, **kwargs: object) -> None:
        raise OSError("unexpected synthetic failure")

    monkeypatch.setattr(os, "replace", refused)
    assert window.rehearse_synthetic_private_handle_window().state is State.IO_ERROR


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
def test_false_postimage_on_success_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = window._closed_window
    calls = 0

    def disagree(root: Path, old: identity._IdentitySet, *, replaced: bool) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            return False
        return original(root, old, replaced=replaced)

    monkeypatch.setattr(window, "_closed_window", disagree)
    assert (
        window.rehearse_synthetic_private_handle_window().state
        is State.POSTIMAGE_CONFLICT_PRESERVE
    )
    assert calls == 1


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
def test_cross_path_identity_failure_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = identity._identities
    calls = 0

    def drift(root: Path, *, stage: bool) -> identity._IdentitySet:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise identity._IdentityUnavailable
        return original(root, stage=stage)

    monkeypatch.setattr(identity, "_identities", drift)
    assert (
        window.rehearse_synthetic_private_handle_window().state
        is State.HANDLE_IDENTITY_CONFLICT_PRESERVE
    )


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
def test_refused_open_handle_replace_requires_unchanged_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise PermissionError("synthetic sharing refusal")

    monkeypatch.setattr(os, "replace", blocked)
    monkeypatch.setattr(window, "_blocked_open_handle", lambda error: True)
    assert (
        window.rehearse_synthetic_private_handle_window().state
        is State.OPEN_HANDLE_BLOCKED_REPLACE_UNQUALIFIED
    )


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
def test_held_handle_drift_after_operation_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = window._held_image
    calls = 0

    def check(stream: BinaryIO, old: tuple[int, int]) -> bool:
        nonlocal calls
        calls += 1
        return calls == 1 and original(stream, old)

    monkeypatch.setattr(window, "_held_image", check)
    assert (
        window.rehearse_synthetic_private_handle_window().state
        is State.HANDLE_IDENTITY_CONFLICT_PRESERVE
    )
    assert calls == 2


@pytest.mark.parametrize("candidate", list(State))
def test_bounded_messages_and_no_secrets(candidate: State) -> None:
    result = window._result(candidate)
    assert (
        result.message and "C:" not in result.message and "/tmp/" not in result.message
    )
    assert result.state is candidate


@pytest.mark.parametrize("fault", list(Fault))
def test_interrupt_matches_only_exact_enum(fault: Fault) -> None:
    if fault is Fault.NONE:
        window._interrupt(fault, Fault.AFTER_GUARD)
    else:
        with pytest.raises(window._InjectedInterruption):
            window._interrupt(fault, fault)


@pytest.mark.parametrize("kind", [OSError("other"), PermissionError("access denied")])
def test_generic_block_classifier_not_portable(
    monkeypatch: pytest.MonkeyPatch, kind: OSError
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    assert not window._blocked_open_handle(kind)


@pytest.mark.skipif(sys.platform not in {"linux", "win32"}, reason="native scratch")
def test_synthetic_scratch_is_deleted(monkeypatch: pytest.MonkeyPatch) -> None:
    roots: list[Path] = []
    original = scratch._write_new

    def watch(root: Path, name: str, raw: bytes) -> None:
        roots.append(root)
        original(root, name, raw)

    monkeypatch.setattr(scratch, "_write_new", watch)
    result = window.rehearse_synthetic_private_handle_window()
    assert result.state in {
        State.PATH_REPLACED_OLD_HANDLE_UNQUALIFIED,
        State.OPEN_HANDLE_BLOCKED_REPLACE_UNQUALIFIED,
    }
    assert len(roots) == 4 and len(set(roots)) == 1
    assert not roots[0].exists()
