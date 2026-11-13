"""Core #238 Slice 3G26: restrictive registry-reader HANDLE release boundary."""

from __future__ import annotations

import ast
import inspect
import io
import os
import sys
import tempfile
import textwrap
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import BinaryIO, Iterator, cast

import pytest

from pds_core import _teacher_private_recovery_reader_release_window as release
from pds_core import _teacher_private_recovery_synthetic_identity_custody as identity
from pds_core import _teacher_private_recovery_synthetic_native_writer as scratch
from pds_core import _teacher_private_registry_image_snapshot as image_reader

Fault = release.PrivateReaderReleaseFault
State = release.PrivateReaderReleaseState


class _Snapshot(io.BytesIO):
    def __init__(self, raw: bytes, file_id: identity._FileID) -> None:
        super().__init__(raw)
        self.file_id = file_id


@pytest.fixture
def emulated_reader(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Only emulate HANDLE coexistence; native scratch file I/O remains real."""
    visited: list[Path] = []
    original = release._held_before
    monkeypatch.setattr(release, "_windows", lambda: True)

    @contextmanager
    def held(path: Path) -> Iterator[_Snapshot]:
        assert path.name == scratch._REGISTRY
        assert path.parent.name.startswith("core238_3g26_reader_")
        visited.append(path.parent)
        with _Snapshot(
            path.read_bytes(), identity._identity(path.parent, scratch._REGISTRY)
        ) as snapshot:
            yield snapshot

    def held_before(stream: BinaryIO, expected: identity._FileID) -> bool:
        if not isinstance(stream, _Snapshot):
            return original(stream, expected)
        stream.seek(0)
        return (
            stream.file_id == expected
            and stream.read(len(scratch._BEFORE) + 1) == scratch._BEFORE
        )

    monkeypatch.setattr(release, "_restrictive_reader", held)
    monkeypatch.setattr(release, "_held_before", held_before)
    return visited


@pytest.fixture
def blocked_then_succeed(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    native = os.replace
    count: list[int] = []

    def replace(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        count.append(len(count) + 1)
        if len(count) == 1:
            raise PermissionError("synthetic reader share refusal")
        native(source, target)

    monkeypatch.setattr(os, "replace", replace)
    return count


def test_release_then_replace_is_observation_only(
    emulated_reader: list[Path], blocked_then_succeed: list[int]
) -> None:
    report = release.rehearse_synthetic_registry_reader_release()
    assert report.state is State.RELEASE_ORDER_OBSERVED_UNQUALIFIED
    assert blocked_then_succeed == [1, 2]
    assert len(emulated_reader) == 1
    assert not emulated_reader[0].exists()
    assert "No production authority" in report.message


@pytest.mark.skipif(sys.platform != "win32", reason="real Win32 HANDLE sharing")
def test_actual_windows_restrictive_reader_blocks_then_releases() -> None:
    report = release.rehearse_synthetic_registry_reader_release()
    assert report.state in {
        State.RELEASE_ORDER_OBSERVED_UNQUALIFIED,
        State.POST_RELEASE_REPLACEMENT_REFUSED,
    }
    assert "C:" not in report.message and "\\\\" not in report.message


@pytest.mark.skipif(sys.platform not in {"win32", "linux"}, reason="native file IDs")
def test_held_reader_requires_real_native_file_id_and_bytes(tmp_path: Path) -> None:
    target = tmp_path / scratch._REGISTRY
    target.write_bytes(scratch._BEFORE)
    old = identity._identity(tmp_path, scratch._REGISTRY)
    with target.open("rb") as stream:
        assert release._held_before(stream, old)
        assert not release._held_before(stream, (old[0], old[1] + 1))
    target.write_bytes(b"not-the-original-bytes")
    with target.open("rb") as stream:
        assert not release._held_before(stream, old)


def _int_expr(value: ast.expr) -> int:
    if isinstance(value, ast.BinOp) and isinstance(value.op, ast.BitOr):
        return _int_expr(value.left) | _int_expr(value.right)
    result = ast.literal_eval(value)
    assert type(result) is int
    return result


def test_reader_sharing_masks_match_actual_read_helper() -> None:
    # Parse source-owned helpers; no production file opened in this test.
    source = ast.parse(textwrap.dedent(inspect.getsource(release._restrictive_reader)))
    calls = [
        part
        for part in ast.walk(source)
        if isinstance(part, ast.Call)
        and isinstance(part.func, ast.Attribute)
        and part.func.attr == "CreateFileW"
    ]
    assert len(calls) == 1
    expected = calls[0]
    assert len(expected.args) == 7
    assert _int_expr(expected.args[1]) == (0x80000000 | 0x20000)
    assert _int_expr(expected.args[2]) == 0x1
    actual_source = ast.parse(
        textwrap.dedent(inspect.getsource(image_reader._read_windows))
    )
    actual_calls = [
        part
        for part in ast.walk(actual_source)
        if isinstance(part, ast.Call)
        and isinstance(part.func, ast.Attribute)
        and part.func.attr == "CreateFileW"
    ]
    assert len(actual_calls) == 1
    assert _int_expr(actual_calls[0].args[1]) == (0x80000000 | 0x20000)
    assert _int_expr(actual_calls[0].args[2]) == 0x1


@pytest.mark.parametrize("fault", [entry for entry in Fault if entry is not Fault.NONE])
def test_interrupted_release_boundary_preserves_evidence(
    emulated_reader: list[Path], blocked_then_succeed: list[int], fault: Fault
) -> None:
    report = release.rehearse_synthetic_registry_reader_release(fault)
    assert report.state is State.INTERRUPTED_PRESERVE
    assert all(not path.exists() for path in emulated_reader)
    assert len(blocked_then_succeed) == (
        0
        if fault in {Fault.AFTER_GUARD, Fault.AFTER_PREIMAGE, Fault.AFTER_READER_OPEN}
        else 1
        if fault in {Fault.AFTER_BLOCKED_ATTEMPT, Fault.AFTER_READER_RELEASE}
        else 2
    )


@pytest.mark.parametrize("bad", [None, "none", 0, True, (), {}, object(), 1.0])
def test_invalid_fault_has_zero_scratch_io(
    monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    def reject(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("scratch created for invalid fault")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", reject)
    assert (
        release.rehearse_synthetic_registry_reader_release(cast(Fault, bad)).state
        is State.INVALID_REQUEST
    )


def test_nonwindows_refuses_before_scratch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(release, "_windows", lambda: False)

    def reject(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("unsupported request performed I/O")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", reject)
    assert (
        release.rehearse_synthetic_registry_reader_release().state is State.UNSUPPORTED
    )


@pytest.mark.parametrize(
    "file", [scratch._REGISTRY, scratch._STAGE, "descriptor.json", "transactions.json"]
)
def test_bad_preimage_refused_before_reader_acquisition(
    monkeypatch: pytest.MonkeyPatch,
    emulated_reader: list[Path],
    file: str,
) -> None:
    original = scratch._write_new

    def corrupt(root: Path, name: str, data: bytes) -> None:
        original(root, name, data + (b"corrupt" if name == file else b""))

    monkeypatch.setattr(scratch, "_write_new", corrupt)
    assert (
        release.rehearse_synthetic_registry_reader_release().state
        is State.PREIMAGE_REFUSED
    )
    assert emulated_reader == []


@pytest.mark.parametrize("number", [1, 2])
def test_unexpected_replace_success_or_refusal_is_not_authorization(
    monkeypatch: pytest.MonkeyPatch,
    emulated_reader: list[Path],
    number: int,
) -> None:
    native = os.replace
    calls = [0]

    def switched(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        calls[0] += 1
        if number == 1:
            native(source, target)
        elif calls[0] == 1:
            raise PermissionError("blocked")
        else:
            raise PermissionError("still blocked after closure")

    monkeypatch.setattr(os, "replace", switched)
    report = release.rehearse_synthetic_registry_reader_release()
    assert report.state is (
        State.PRE_RELEASE_REPLACEMENT_CONFLICT_PRESERVE
        if number == 1
        else State.POST_RELEASE_REPLACEMENT_REFUSED
    )
    assert calls[0] == number


@pytest.mark.parametrize("number", [1, 2])
def test_nonsharing_native_io_error_refuses(
    monkeypatch: pytest.MonkeyPatch, emulated_reader: list[Path], number: int
) -> None:
    native = os.replace
    calls = [0]

    def fails(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        calls[0] += 1
        if calls[0] == number:
            raise OSError("non-sharing I/O failure")
        if calls[0] == 1:
            raise PermissionError("expected blocked")
        native(source, target)

    monkeypatch.setattr(os, "replace", fails)
    assert release.rehearse_synthetic_registry_reader_release().state is State.IO_ERROR


@pytest.mark.parametrize(
    "name", [scratch._REGISTRY, "descriptor.json", "transactions.json"]
)
def test_postimage_corruption_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    emulated_reader: list[Path],
    name: str,
) -> None:
    native = os.replace
    calls = [0]

    def corrupt(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        calls[0] += 1
        if calls[0] == 1:
            raise PermissionError("blocked")
        native(source, target)
        (Path(target).parent / name).write_bytes(b"corrupt-after-replace")

    monkeypatch.setattr(os, "replace", corrupt)
    assert (
        release.rehearse_synthetic_registry_reader_release().state
        is State.POSTIMAGE_CONFLICT_PRESERVE
    )


@pytest.mark.parametrize("point", [1, 2, 3])
def test_reader_identity_drift_refuses(
    monkeypatch: pytest.MonkeyPatch,
    emulated_reader: list[Path],
    blocked_then_succeed: list[int],
    point: int,
) -> None:
    original = release._held_before
    count = [0]

    def faulty(stream: BinaryIO, expected: identity._FileID) -> bool:
        count[0] += 1
        if point < 3 and count[0] == point:
            return False
        return original(stream, expected)

    monkeypatch.setattr(release, "_held_before", faulty)
    if point == 3:
        original_images = release._same_images
        census = [0]

        def drift(
            root: Path,
            expected: identity._IdentitySet,
            lock_id: identity._FileID,
            *,
            replaced: bool,
        ) -> State | None:
            census[0] += 1
            if census[0] == 2:
                return State.IDENTITY_CONFLICT_PRESERVE
            return original_images(root, expected, lock_id, replaced=replaced)

        monkeypatch.setattr(release, "_same_images", drift)
        assert (
            release.rehearse_synthetic_registry_reader_release().state
            is State.IDENTITY_CONFLICT_PRESERVE
        )
    else:
        assert (
            release.rehearse_synthetic_registry_reader_release().state
            is State.READER_CONFLICT_PRESERVE
        )


def test_pre_release_namespace_drift_refused(
    monkeypatch: pytest.MonkeyPatch,
    emulated_reader: list[Path],
    blocked_then_succeed: list[int],
) -> None:
    native = release._same_images
    visits = [0]

    def drift(
        root: Path,
        expected: identity._IdentitySet,
        lock_id: identity._FileID,
        *,
        replaced: bool,
    ) -> State | None:
        visits[0] += 1
        if visits[0] == 1:
            return State.POSTIMAGE_CONFLICT_PRESERVE
        return native(root, expected, lock_id, replaced=replaced)

    monkeypatch.setattr(release, "_same_images", drift)
    assert (
        release.rehearse_synthetic_registry_reader_release().state
        is State.POSTIMAGE_CONFLICT_PRESERVE
    )
    assert blocked_then_succeed == [1]


def test_native_reader_open_error_is_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(release, "_windows", lambda: True)

    @contextmanager
    def denied(_path: Path) -> Iterator[BinaryIO]:
        raise OSError("synthetic open failure")
        yield  # pragma: no cover

    def no_replace(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("replace called without successful read open")

    monkeypatch.setattr(release, "_restrictive_reader", denied)
    monkeypatch.setattr(os, "replace", no_replace)
    assert release.rehearse_synthetic_registry_reader_release().state is State.IO_ERROR


def test_native_advisory_guard_failure_prevents_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(release, "_windows", lambda: True)

    @contextmanager
    def denied(_path: Path) -> Iterator[None]:
        raise scratch._GuardRefused
        yield  # pragma: no cover

    @contextmanager
    def no_reader(_path: Path) -> Iterator[BinaryIO]:
        raise AssertionError("reader acquired without guard")
        yield  # pragma: no cover

    monkeypatch.setattr(scratch, "_scratch_lock", denied)
    monkeypatch.setattr(release, "_restrictive_reader", no_reader)
    assert (
        release.rehearse_synthetic_registry_reader_release().state
        is State.GUARD_REFUSED
    )


def test_keyboard_interrupt_is_preserved(
    monkeypatch: pytest.MonkeyPatch, emulated_reader: list[Path]
) -> None:
    def interrupt(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "replace", interrupt)
    assert (
        release.rehearse_synthetic_registry_reader_release().state
        is State.INTERRUPTED_PRESERVE
    )


@pytest.mark.parametrize("state", list(State))
def test_sanitized_immutable_result_has_no_write_token(state: State) -> None:
    result = release._result(state)
    assert result.state is state
    assert result.message
    assert "C:" not in result.message and "/tmp/" not in result.message
    assert not any(
        hasattr(result, key)
        for key in (
            "path",
            "private_root",
            "handle",
            "owner",
            "token",
            "permit",
            "bytes",
            "commit",
        )
    )
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", State.IO_ERROR)


def test_no_private_paths_bytes_or_writer_callbacks_in_public_api() -> None:
    signature = inspect.signature(release.rehearse_synthetic_registry_reader_release)
    assert list(signature.parameters) == ["interruption"]
    assert not hasattr(release, "commit_private_registry")
    assert not hasattr(release, "retire_journal")
