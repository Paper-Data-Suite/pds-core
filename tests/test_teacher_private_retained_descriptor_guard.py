"""Core #238 Slice 3E0 — native workspace descriptor retention and refusal."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_retained_descriptor_guard as guard
from pds_core import _teacher_private_retained_registry_guard as registry_guard
from pds_core.teacher_experience import get_teacher_experience_capabilities


def _make(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "workspace"
    directory = workspace / ".pds"
    directory.mkdir(parents=True)
    sidecar = directory / "teacher-private-association.json"
    sidecar.write_bytes(b'{"schema":"synthetic", "version":1}')
    return workspace, sidecar


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native directory FD only")
def test_linux_real_retention_and_no_mutation(tmp_path: Path) -> None:
    workspace, sidecar = _make(tmp_path)
    previous = sidecar.read_bytes()
    before = sidecar.stat().st_mtime_ns
    with guard._held_linux_descriptor(workspace):
        assert sidecar.read_bytes() == previous
    assert sidecar.read_bytes() == previous
    assert sidecar.stat().st_mtime_ns == before


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native directory FD only")
def test_linux_replaced_file_on_exit_refused(tmp_path: Path) -> None:
    workspace, sidecar = _make(tmp_path)
    with pytest.raises(guard.RetainedDescriptorGuardError) as exc:
        with guard._held_linux_descriptor(workspace):
            sidecar.replace(sidecar.with_suffix(".old"))
            sidecar.write_bytes(b'{"schema":"synthetic", "version":1}')
    assert exc.value.code is guard.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native directory FD only")
def test_linux_parent_replaced_on_exit_refused(tmp_path: Path) -> None:
    workspace, sidecar = _make(tmp_path)
    directory = sidecar.parent
    with pytest.raises(guard.RetainedDescriptorGuardError) as exc:
        with guard._held_linux_descriptor(workspace):
            directory.rename(workspace / "former")
            directory.mkdir()
            (directory / sidecar.name).write_bytes(b"replacement")
    assert exc.value.code is guard.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native directory FD only")
def test_linux_same_file_content_drift_refused(tmp_path: Path) -> None:
    workspace, sidecar = _make(tmp_path)
    with pytest.raises(guard.RetainedDescriptorGuardError) as exc:
        with guard._held_linux_descriptor(workspace):
            sidecar.write_bytes(b"different-size-data")
    assert exc.value.code is guard.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native directory FD only")
def test_linux_missing_descriptor_refused(tmp_path: Path) -> None:
    workspace, sidecar = _make(tmp_path)
    sidecar.unlink()
    with pytest.raises(guard.RetainedDescriptorGuardError) as exc:
        with guard._held_linux_descriptor(workspace):
            pytest.fail("missing descriptor must fail before body")
    assert exc.value.code is guard.RetainedDescriptorGuardCode.MISSING_DESCRIPTOR


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native directory FD only")
def test_linux_symlink_parent_refused(tmp_path: Path) -> None:
    workspace, sidecar = _make(tmp_path)
    parent = sidecar.parent
    parent.rename(workspace / "genuine")
    parent.symlink_to(workspace / "genuine", target_is_directory=True)
    with pytest.raises(guard.RetainedDescriptorGuardError) as exc:
        with guard._held_linux_descriptor(workspace):
            pytest.fail("symlink must fail before body")
    assert exc.value.code in {
        guard.RetainedDescriptorGuardCode.REFUSED_PATH,
        guard.RetainedDescriptorGuardCode.IO_ERROR,
    }


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native directory FD only")
def test_linux_symlink_file_refused(tmp_path: Path) -> None:
    workspace, sidecar = _make(tmp_path)
    sidecar.rename(sidecar.parent / "real")
    sidecar.symlink_to(sidecar.parent / "real")
    with pytest.raises(guard.RetainedDescriptorGuardError):
        with guard._held_linux_descriptor(workspace):
            pytest.fail("symlink must fail before body")


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native directory FD only")
def test_linux_oversized_refused(tmp_path: Path) -> None:
    workspace, sidecar = _make(tmp_path)
    sidecar.write_bytes(b"x" * 4097)
    with pytest.raises(guard.RetainedDescriptorGuardError) as exc:
        with guard._held_linux_descriptor(workspace):
            pytest.fail("oversized descriptor must fail before body")
    assert exc.value.code is guard.RetainedDescriptorGuardCode.REFUSED_PATH


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native directory FD only")
def test_linux_body_exception_is_preserved(tmp_path: Path) -> None:
    workspace, _ = _make(tmp_path)
    with pytest.raises(ZeroDivisionError):
        with guard._held_linux_descriptor(workspace):
            raise ZeroDivisionError


@pytest.mark.skipif(sys.platform != "linux", reason="Linux native directory FD only")
def test_linux_caller_oserror_preserved(tmp_path: Path) -> None:
    workspace, _ = _make(tmp_path)
    with pytest.raises(OSError, match="synthetic-caller-error"):
        with guard._held_linux_descriptor(workspace):
            raise OSError("synthetic-caller-error")


def test_windows_guard_reopens_both_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    closed: list[int | None] = []
    opens: list[bool] = []

    class Kernel:
        def CloseHandle(self, handle: object) -> int:
            closed.append(getattr(handle, "value", None))
            return 1

    kernel = Kernel()

    def opening(_kernel: object, _path: str, *, directory: bool) -> tuple[int, int]:
        opens.append(directory)
        return (
            (11 if directory else 22) if len(opens) <= 2 else (33 if directory else 44)
        ), 0

    def signature(
        _kernel: object, handle: int, *, directory: bool
    ) -> tuple[int, bytes, int, int, int]:
        assert directory == (handle in (11, 33))
        return (7, b"p" * 16 if directory else b"f" * 16, 32, 1, 2)

    monkeypatch.setattr(descriptor, "_windows_api", lambda: kernel)
    monkeypatch.setattr(descriptor, "_windows_ancestry", lambda *_: None)
    monkeypatch.setattr(descriptor, "_windows_open", opening)
    monkeypatch.setattr(guard, "_windows_signature", signature)
    with guard._held_windows_descriptor(workspace):
        assert len(opens) == 4
        assert closed == [33, 44]
    assert len(opens) == 6
    assert closed == [33, 44, 33, 44, 22, 11]


def test_windows_identity_change_refuses_and_closes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    closed: list[int | None] = []
    calls = 0

    class Kernel:
        def CloseHandle(self, handle: object) -> int:
            closed.append(getattr(handle, "value", None))
            return 1

    def opening(_kernel: object, _path: str, *, directory: bool) -> tuple[int, int]:
        return (11 if directory else 22), 0

    def signature(
        _kernel: object, handle: int, *, directory: bool
    ) -> tuple[int, bytes, int, int, int]:
        nonlocal calls
        calls += 1
        return (
            7,
            b"p" * 16 if directory else (b"f" * 16 if calls < 7 else b"x" * 16),
            32,
            1,
            2,
        )

    monkeypatch.setattr(descriptor, "_windows_api", Kernel)
    monkeypatch.setattr(descriptor, "_windows_ancestry", lambda *_: None)
    monkeypatch.setattr(descriptor, "_windows_open", opening)
    monkeypatch.setattr(guard, "_windows_signature", signature)
    with pytest.raises(guard.RetainedDescriptorGuardError) as exc:
        with guard._held_windows_descriptor(workspace):
            pass
    assert exc.value.code is guard.RetainedDescriptorGuardCode.CHANGED_DURING_SCOPE
    assert closed[-2:] == [22, 11]


def test_windows_reparse_refusal_before_body(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(descriptor, "_windows_api", lambda: object())
    monkeypatch.setattr(
        descriptor,
        "_windows_ancestry",
        lambda *_: descriptor.PrivateDescriptorSnapshotState.REFUSED_PATH,
    )
    with pytest.raises(guard.RetainedDescriptorGuardError) as exc:
        with guard._held_windows_descriptor(workspace):
            pytest.fail("ancestry refusal must occur before body")
    assert exc.value.code is guard.RetainedDescriptorGuardCode.REFUSED_PATH


def test_windows_signature_rejects_unsafe_file(monkeypatch: pytest.MonkeyPatch) -> None:
    from pds_core import _teacher_private_native_journal_anchor as anchor

    class Kernel:
        def GetFileInformationByHandleEx(self, *args: object) -> bool:
            return True

    monkeypatch.setattr(anchor, "_windows_id", lambda *_: (10, b"x" * 16))
    monkeypatch.setattr(
        descriptor,
        "_windows_info",
        lambda *_: (
            0x400,
            SimpleNamespace(
                directory=False, delete_pending=False, number_of_links=1, end_of_file=10
            ),
        ),
    )
    assert guard._windows_signature(Kernel(), 42, directory=False) is None


def _fake_outer(
    monkeypatch: pytest.MonkeyPatch, trace: list[str], *, refuse_exit: bool = False
) -> None:
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)

    @contextmanager
    def scope(_private: Path, _workspace: Path) -> Iterator[None]:
        trace.append("registry+locks+journal entered")
        try:
            yield
            if refuse_exit:
                raise registry_guard.RetainedRegistryGuardError(
                    registry_guard.RetainedRegistryGuardCode.CHANGED_DURING_SCOPE
                )
        finally:
            trace.append("registry+locks+journal exited")

    @contextmanager
    def descriptor_scope(_workspace: Path) -> Iterator[None]:
        trace.append("descriptor entered")
        try:
            yield
        finally:
            trace.append("descriptor exited")

    monkeypatch.setattr(registry_guard, "_hold_existing_retained_registry_guard", scope)
    monkeypatch.setattr(guard, "_held_linux_descriptor", descriptor_scope)
    monkeypatch.setattr(guard, "_held_windows_descriptor", descriptor_scope)
    owner = object()
    monkeypatch.setattr(ordered, "_owner", lambda: owner)


def test_nested_guard_order_and_no_write_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    trace: list[str] = []
    _fake_outer(monkeypatch, trace)
    with guard._hold_existing_retained_descriptor_guard(
        tmp_path / "private", tmp_path / "workspace"
    ) as result:
        assert result is None
        trace.append("read-only body")
    assert trace == [
        "registry+locks+journal entered",
        "descriptor entered",
        "read-only body",
        "descriptor exited",
        "registry+locks+journal exited",
    ]
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(guard, "commit_binding")
    assert not hasattr(guard, "admit_journal")


def test_outer_guard_exit_refusal_overrides_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    trace: list[str] = []
    _fake_outer(monkeypatch, trace, refuse_exit=True)
    with pytest.raises(guard.RetainedDescriptorGuardError) as exc:
        with guard._hold_existing_retained_descriptor_guard(
            tmp_path / "private", tmp_path / "workspace"
        ):
            pass
    assert exc.value.code is guard.RetainedDescriptorGuardCode.REGISTRY_GUARD_REFUSED
    assert trace[-2:] == ["descriptor exited", "registry+locks+journal exited"]


def test_owner_drift_refused_inside_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    trace: list[str] = []
    _fake_outer(monkeypatch, trace)
    counter = 0

    def owner() -> int:
        nonlocal counter
        counter += 1
        return 1 if counter == 1 else 2

    monkeypatch.setattr(ordered, "_owner", owner)
    with pytest.raises(guard.RetainedDescriptorGuardError) as exc:
        with guard._hold_existing_retained_descriptor_guard(
            tmp_path / "private", tmp_path / "workspace"
        ):
            pytest.fail("owner drift must refuse before body")
    assert exc.value.code is guard.RetainedDescriptorGuardCode.OWNER_CHANGED
    assert trace[-2:] == ["descriptor exited", "registry+locks+journal exited"]


def test_invalid_and_unsupported_have_no_io(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    trace: list[str] = []
    _fake_outer(monkeypatch, trace)
    assert list(tmp_path.iterdir()) == []
    assert guard._hold_existing_retained_descriptor_guard is not None
    with pytest.raises(guard.RetainedDescriptorGuardError) as exc:
        with guard._hold_existing_retained_descriptor_guard("bad", tmp_path):  # type: ignore[arg-type]
            pass
    assert exc.value.code is guard.RetainedDescriptorGuardCode.INVALID_REQUEST
    assert trace == []
    assert list(tmp_path.iterdir()) == []
