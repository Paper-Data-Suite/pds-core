"""Core #238 3G6: one native attempt and failure-safe advisory states."""

from __future__ import annotations

import ctypes
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_registry_replace_attempt as attempt
from pds_core import _teacher_private_windows_registry_replacement_guard as guard
from pds_core.teacher_experience import get_teacher_experience_capabilities

TX = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
State = attempt.PrivateWindowsReplaceAttemptState


def _intent() -> intents.PrivateTransactionIntent:
    candidate = object.__new__(intents.PrivateTransactionIntent)
    witness = SimpleNamespace(transaction_id=TX)
    object.__setattr__(candidate, "witness", witness)
    return candidate


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    guard_refusal: guard.PrivateWindowsRegistryReplacementCode | None = None,
    fail_after_yield: bool = False,
    move_success: bool = True,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    @contextmanager
    def retained(_intent: object, _root: Path, _workspace: Path) -> Iterator[None]:
        events.append("guard-enter")
        if guard_refusal is not None:
            raise guard.PrivateWindowsRegistryReplacementError(guard_refusal)
        yield
        if fail_after_yield:
            raise guard.PrivateWindowsRegistryReplacementError(
                guard.PrivateWindowsRegistryReplacementCode.UNEXPECTED_MUTATION
            )
        events.append("guard-exit")

    monkeypatch.setattr(
        guard, "hold_expected_windows_private_registry_replacement", retained
    )

    def move(source: Path, target: Path) -> bool:
        events.append("move")
        assert source.name == "." + TX + ".registry-stage"
        assert target.name == "registry.json"
        assert source.parent == target.parent
        return move_success

    monkeypatch.setattr(attempt, "_replace_open_target_posix", move)


@pytest.mark.parametrize("platform", ["linux", "darwin", "freebsd"])
def test_unsupported_platform_has_no_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, platform: str
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    assert (
        attempt.attempt_windows_private_registry_stage_replacement(
            _intent(), tmp_path, tmp_path
        ).state
        is State.UNSUPPORTED
    )
    assert not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("bad", [None, object(), "intent", 17])
def test_invalid_intent_has_no_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert (
        attempt.attempt_windows_private_registry_stage_replacement(
            cast(intents.PrivateTransactionIntent, bad), tmp_path, tmp_path
        ).state
        is State.INVALID_REQUEST
    )
    assert not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("bad", [None, "root", 42])
def test_invalid_roots_have_no_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: object
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert (
        attempt.attempt_windows_private_registry_stage_replacement(
            _intent(), cast(Path, bad), tmp_path
        ).state
        is State.INVALID_REQUEST
    )
    assert (
        attempt.attempt_windows_private_registry_stage_replacement(
            _intent(), tmp_path, cast(Path, bad)
        ).state
        is State.INVALID_REQUEST
    )


def test_one_guarded_move_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events)
    result = attempt.attempt_windows_private_registry_stage_replacement(
        _intent(), tmp_path, tmp_path
    )
    assert result.state is State.REPLACED_RECOVERY_REQUIRED
    assert events == ["guard-enter", "move", "guard-exit"]
    assert not hasattr(result, "authorized")
    assert not hasattr(result, "commit_token")
    assert not hasattr(result, "path")
    assert not hasattr(result, "raw")
    for secret in (TX, str(tmp_path)):
        assert secret not in repr(result)
        assert secret not in result.message
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", State.UNSUPPORTED)


@pytest.mark.parametrize(
    "code",
    [
        guard.PrivateWindowsRegistryReplacementCode.UNSUPPORTED,
        guard.PrivateWindowsRegistryReplacementCode.INVALID_REQUEST,
        guard.PrivateWindowsRegistryReplacementCode.BEFORE_IMAGE_MISMATCH,
        guard.PrivateWindowsRegistryReplacementCode.OWNER_CHANGED,
        guard.PrivateWindowsRegistryReplacementCode.NAMESPACE_UNQUALIFIED,
    ],
)
def test_guard_refuses_before_move(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    code: guard.PrivateWindowsRegistryReplacementCode,
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, guard_refusal=code)
    outcome = attempt.attempt_windows_private_registry_stage_replacement(
        _intent(), tmp_path, tmp_path
    )
    if code is guard.PrivateWindowsRegistryReplacementCode.UNSUPPORTED:
        assert outcome.state is State.UNSUPPORTED
    elif code is guard.PrivateWindowsRegistryReplacementCode.INVALID_REQUEST:
        assert outcome.state is State.INVALID_REQUEST
    else:
        assert outcome.state is State.GUARD_REFUSED
    assert events == ["guard-enter"]


@pytest.mark.parametrize("move_success", [False, True])
def test_failed_or_ambiguous_postcheck_is_not_commit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, move_success: bool
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, fail_after_yield=True, move_success=move_success)
    result = attempt.attempt_windows_private_registry_stage_replacement(
        _intent(), tmp_path, tmp_path
    )
    assert result.state is (
        State.REFUSED_RECOVERY_REQUIRED
        if move_success
        else State.NATIVE_MOVE_FAILED_RECOVERY_REQUIRED
    )
    assert events == ["guard-enter", "move"]


def test_false_native_result_preserves_recovery_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events, move_success=False)
    result = attempt.attempt_windows_private_registry_stage_replacement(
        _intent(), tmp_path, tmp_path
    )
    assert result.state is State.REFUSED_RECOVERY_REQUIRED
    assert events == ["guard-enter", "move", "guard-exit"]


@pytest.mark.parametrize("problem", [OSError("private path"), ValueError("secret")])
def test_native_exceptions_are_sanitized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, problem: Exception
) -> None:
    events: list[str] = []
    _setup(monkeypatch, events)

    def raise_failure(_source: Path, _target: Path) -> bool:
        raise problem

    monkeypatch.setattr(attempt, "_replace_open_target_posix", raise_failure)
    result = attempt.attempt_windows_private_registry_stage_replacement(
        _intent(), tmp_path, tmp_path
    )
    assert result.state is State.REFUSED_RECOVERY_REQUIRED
    assert "secret" not in result.message and "private path" not in repr(result)
    assert events == ["guard-enter"]


@pytest.mark.parametrize("native_success", [True, False])
def test_backend_uses_only_posix_rename_info_ex_with_delete_handle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, native_success: bool
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    opened: list[tuple[str, int, int, int, int]] = []
    renamed: list[tuple[int, int, bytes]] = []
    closed: list[int] = []

    class Create:
        argtypes: object = None
        restype: object = None

        def __call__(
            self,
            path: str,
            access: int,
            share: int,
            _sec: object,
            creation: int,
            flags: int,
            _template: object,
        ) -> ctypes.c_void_p:
            opened.append((path, access, share, creation, flags))
            return ctypes.c_void_p(777)

    class Rename:
        argtypes: object = None
        restype: object = None

        def __call__(self, _handle: object, cls: int, buf: object, size: int) -> int:
            info = ctypes.cast(
                cast(ctypes.c_void_p, buf), ctypes.POINTER(attempt._FileRenameInfo)
            ).contents
            encoded = ctypes.string_at(
                ctypes.addressof(info) + attempt._FileRenameInfo.file_name.offset,
                info.file_name_length,
            )
            assert size >= attempt._FileRenameInfo.file_name.offset + len(encoded)
            renamed.append((cls, info.flags, encoded))
            return int(native_success)

    class Close:
        def __call__(self, handle: object) -> int:
            assert isinstance(handle, ctypes.c_void_p)
            assert handle.value == 777
            closed.append(777)
            return 1

    class Kernel:
        CreateFileW = Create()
        SetFileInformationByHandle = Rename()
        CloseHandle = Close()

    monkeypatch.setattr(wincheck, "_bind_api", lambda: (Kernel(), object()))
    source = tmp_path / "stage"
    target = tmp_path / "registry.json"
    assert attempt._replace_open_target_posix(source, target) is native_success
    assert opened == [(str(source), 0x10000 | 0x80 | 0x20000, 7, 3, 0x00200000)]
    assert renamed == [(22, 3, str(target).encode("utf-16-le"))]
    assert closed == [777]
    assert not source.exists()
    assert not target.exists()


def test_backend_does_not_open_cross_directory_or_same_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def never_open() -> object:
        raise AssertionError("Win32 access before local path refusal")

    monkeypatch.setattr(wincheck, "_bind_api", never_open)
    assert not attempt._replace_open_target_posix(
        tmp_path / "stage", tmp_path / "other" / "registry.json"
    )
    assert not attempt._replace_open_target_posix(
        tmp_path / "registry.json", tmp_path / "registry.json"
    )


@pytest.mark.skipif(
    sys.platform != "win32", reason="native Windows scratch volume only"
)
def test_windows_native_scratch_replacement_preserves_handle_ids(
    tmp_path: Path,
) -> None:
    """Native Windows identity assertions in an independent Python interpreter.

    Earlier synthetic Win32 API tests can contaminate per-process ctypes/native
    state. This still runs one real FileRenameInfoEx, with original and stage
    handles held concurrently; failure of ANY assertion fails this test.
    """
    program = r"""
import ctypes
import sys
from ctypes import wintypes
from pathlib import Path
from pds_core import _teacher_private_native_journal_anchor as anchor
from pds_core import _teacher_private_windows_preflight as wincheck
from pds_core import _teacher_private_windows_registry_replace_attempt as attempt

root = Path(sys.argv[1])
source = root / "stage"
target = root / "registry.json"
source.write_bytes(b"synthetic-after")
target.write_bytes(b"synthetic-before")
kernel, _ = wincheck._bind_api()
old_handle = kernel.CreateFileW(
    str(target), 0x80 | 0x20000, 7, None, 3, 0x00200000, None
)
stage_handle = kernel.CreateFileW(
    str(source), 0x80 | 0x20000, 7, None, 3, 0x00200000, None
)
old_value = ctypes.cast(old_handle, ctypes.c_void_p).value
stage_value = ctypes.cast(stage_handle, ctypes.c_void_p).value
bad = ctypes.c_void_p(-1).value
assert old_value is not None and old_value != bad
assert stage_value is not None and stage_value != bad
try:
    old_id = anchor._windows_id(kernel, old_value)
    stage_id = anchor._windows_id(kernel, stage_value)
    assert old_id is not None and stage_id is not None
    assert old_id != stage_id
    # Slice 3G66: report ONLY fixed classifications of this disposable scratch
    # experiment when a native replacement postcondition fails. Do not turn a
    # failed rename into a pass; the original assertions remain below.
    renamed = attempt._replace_open_target_posix(source, target)
    try:
        named_contents = target.read_bytes()
    except FileNotFoundError:
        data_state = "missing"
    except OSError:
        data_state = "unreadable"
    else:
        if named_contents == b"synthetic-after":
            data_state = "after"
        elif named_contents == b"synthetic-before":
            data_state = "before"
        else:
            data_state = "unexpected"
    source_present = source.exists()
    old_stable = anchor._windows_id(kernel, old_value) == old_id
    stage_stable = anchor._windows_id(kernel, stage_value) == stage_id
    reopened = kernel.CreateFileW(
        str(target), 0x80 | 0x20000, 7, None, 3, 0x00200000, None
    )
    reopened_value = ctypes.cast(reopened, ctypes.c_void_p).value
    if reopened_value is None or reopened_value == bad:
        reopened_class = "unavailable"
    else:
        try:
            opened_id = anchor._windows_id(kernel, reopened_value)
            if opened_id == stage_id:
                reopened_class = "stage"
            elif opened_id == old_id:
                reopened_class = "old"
            elif opened_id is None:
                reopened_class = "unverified"
            else:
                reopened_class = "other"
        finally:
            kernel.CloseHandle(reopened)
    # 3G67 forensic extension. The exact original operation and its assertion
    # remain untouched. Everything here is within disposable synthetic scratch.
    def _displaced_stage() -> tuple[str, str]:
        other = [
            entry for entry in root.iterdir()
            if entry.name not in {source.name, target.name}
        ]
        matches = False
        for entry in other:
            try:
                if (
                    not entry.is_symlink()
                    and entry.is_file()
                    and entry.read_bytes() == b"synthetic-after"
                ):
                    matches = True
            except OSError:
                pass
        bucket = "none" if not other else ("one" if len(other) == 1 else "many")
        return bucket, ("yes" if matches else "no")

    def _scratch_variant(mode: str) -> str:
        # Two independent new file pairs, not a retry on the failed stage.
        # Both modes retain an open destination handle and assert native ID.
        candidate_source = root / ("candidate-stage-" + mode)
        candidate_target = root / ("candidate-registry-" + mode)
        candidate_source.write_bytes(b"variant-after")
        candidate_target.write_bytes(b"variant-before")
        old_v = None
        source_v = None
        directory_v = None
        reopened_v = None
        try:
            old_v = kernel.CreateFileW(
                str(candidate_target), 0x80 | 0x20000, 7,
                None, 3, 0x00200000, None
            )
            source_v = kernel.CreateFileW(
                str(candidate_source), 0x10000 | 0x80 | 0x20000, 7,
                None, 3, 0x00200000, None
            )
            old_n = ctypes.cast(old_v, ctypes.c_void_p).value
            source_n = ctypes.cast(source_v, ctypes.c_void_p).value
            if old_n in (None, bad) or source_n in (None, bad):
                return "open-refused"
            before_id = anchor._windows_id(kernel, old_n)
            stage_id_v = anchor._windows_id(kernel, source_n)
            if before_id is None or stage_id_v is None or before_id == stage_id_v:
                return "id-unavailable"
            root_v = None
            if mode == "relative":
                directory_v = kernel.CreateFileW(
                    str(root), 0x80 | 0x20000, 7, None, 3,
                    0x02000000 | 0x00200000, None
                )
                root_v = ctypes.cast(directory_v, ctypes.c_void_p).value
                if root_v in (None, bad):
                    return "directory-refused"
            filename = (
                candidate_target.name if mode == "relative"
                else str(candidate_target)
            )
            name = filename.encode("utf-16-le", errors="strict")
            size = max(
                ctypes.sizeof(attempt._FileRenameInfo),
                attempt._FileRenameInfo.file_name.offset + len(name) + 2,
            )
            raw = ctypes.create_string_buffer(size)
            header = attempt._FileRenameInfo.from_buffer(raw)
            header.flags = 3
            header.root_directory = root_v
            header.file_name_length = len(name)
            ctypes.memmove(
                ctypes.addressof(raw)
                + attempt._FileRenameInfo.file_name.offset,
                name, len(name)
            )
            returned = bool(kernel.SetFileInformationByHandle(
                wintypes.HANDLE(source_n), 22, ctypes.byref(raw), size
            ))
            if not returned:
                return "native-refused"
            try:
                payload = candidate_target.read_bytes()
            except OSError:
                return "target-unreadable"
            if payload != b"variant-after":
                return "target-before" if payload == b"variant-before" else "target-other"
            if candidate_source.exists():
                return "source-remains"
            reopened_v = kernel.CreateFileW(
                str(candidate_target), 0x80 | 0x20000, 7,
                None, 3, 0x00200000, None
            )
            reopened_n = ctypes.cast(reopened_v, ctypes.c_void_p).value
            if reopened_n in (None, bad):
                return "reopen-refused"
            if anchor._windows_id(kernel, reopened_n) != stage_id_v:
                return "wrong-identity"
            if anchor._windows_id(kernel, old_n) != before_id:
                return "old-identity-changed"
            if anchor._windows_id(kernel, source_n) != stage_id_v:
                return "stage-identity-changed"
            return "correct"
        except (OSError, ValueError, TypeError, AttributeError, OverflowError):
            return "exception"
        finally:
            for opened in (reopened_v, directory_v, source_v, old_v):
                if opened is not None:
                    opened_n = ctypes.cast(opened, ctypes.c_void_p).value
                    if opened_n not in (None, bad):
                        kernel.CloseHandle(opened)

    if (
        not renamed
        or data_state != "after"
        or source_present
        or not old_stable
        or not stage_stable
        or reopened_class != "stage"
    ):
        displaced_count, displaced_payload = _displaced_stage()
        # Do not suppress the original failure even if a variant succeeds.
        absolute_variant = _scratch_variant("absolute")
        relative_variant = _scratch_variant("relative")
        raise AssertionError(
            "NATIVE_SCRATCH_RENAME_POSTCONDITION: "
            f"rename_reported={renamed}; target_data={data_state}; "
            f"source_name_present={source_present}; "
            f"old_handle_stable={old_stable}; "
            f"stage_handle_stable={stage_stable}; "
            f"reopened_target_identity={reopened_class}; "
            f"unexpected_names={displaced_count}; "
            f"displaced_stage_payload={displaced_payload}; "
            f"absolute_nul_variant={absolute_variant}; "
            f"relative_parent_variant={relative_variant}; "
            f"rename_struct_offset={attempt._FileRenameInfo.file_name.offset}; "
            f"rename_struct_size={ctypes.sizeof(attempt._FileRenameInfo)}; "
            f"native_wchar_size={ctypes.sizeof(wintypes.WCHAR)}"
        )
    assert renamed
    assert target.read_bytes() == b"synthetic-after"
    assert not source.exists()
    assert anchor._windows_id(kernel, old_value) == old_id
    assert anchor._windows_id(kernel, stage_value) == stage_id
    new_handle = kernel.CreateFileW(
        str(target), 0x80 | 0x20000, 7, None, 3, 0x00200000, None
    )
    try:
        new_value = ctypes.cast(new_handle, ctypes.c_void_p).value
        assert new_value is not None and new_value != bad
        assert anchor._windows_id(kernel, new_value) == stage_id
    finally:
        kernel.CloseHandle(new_handle)
finally:
    kernel.CloseHandle(stage_handle)
    kernel.CloseHandle(old_handle)
"""
    completed = subprocess.run(
        [sys.executable, "-c", program, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, (
        f"Native Windows scratch child failed (exit {completed.returncode}): "
        + completed.stderr[-1400:]
    )


def test_no_notes_capabilities_or_writer_export() -> None:
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
    assert not hasattr(attempt, "commit_private_workspace_binding")
    assert not hasattr(attempt, "retire_private_journal")
    assert not hasattr(attempt, "open_notes")
