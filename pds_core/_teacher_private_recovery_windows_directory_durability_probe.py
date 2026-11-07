"""Windows scratch-only, three-parent native directory flush census (#238 3G49).

The result is NEVER proof of durable directory names, multi-file transaction
completion, protection of a real workspace, or authority to retire a journal.
No caller-supplied path or data is accepted. No fallback volume flush is used.
"""

from __future__ import annotations

import ctypes
import os
import stat
import sys
import tempfile
from ctypes import wintypes
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class PrivateDirectoryFlushState(str, Enum):
    REQUESTS_RETURNED_UNQUALIFIED = "requests_returned_unqualified"
    OPEN_REFUSED = "open_refused"
    FLUSH_REFUSED = "flush_refused"
    IDENTITY_CHANGED = "identity_changed"
    FILE_FLUSH_REFUSED = "file_flush_refused"
    UNSUPPORTED_PLATFORM = "unsupported_platform"
    NATIVE_UNAVAILABLE = "native_unavailable"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    IO_ERROR_PRESERVE = "io_error_preserve"


class PrivateDirectoryFlushObservation(str, Enum):
    RETURNED_UNQUALIFIED = "returned_unqualified"
    OPEN_ACCESS_DENIED = "open_access_denied"
    OPEN_UNSUPPORTED = "open_unsupported"
    FLUSH_ACCESS_DENIED = "flush_access_denied"
    FLUSH_UNSUPPORTED = "flush_unsupported"
    FLUSH_OTHER_REFUSAL = "flush_other_refusal"
    HANDLE_UNQUALIFIED = "handle_unqualified"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateDirectoryFlushReview:
    state: PrivateDirectoryFlushState
    message: str
    # Names are synthetic roles, never live private paths.
    observations: tuple[tuple[str, PrivateDirectoryFlushObservation], ...] = field(
        default=(), repr=False
    )
    production_writes_blocked: bool = True
    journal_retirement_forbidden: bool = True
    pending_evidence_must_remain: bool = True
    directory_durability_unqualified: bool = True

    def __repr__(self) -> str:
        return "PrivateDirectoryFlushReview(non_authorizing=True)"


def _result(
    state: PrivateDirectoryFlushState,
    observations: tuple[tuple[str, PrivateDirectoryFlushObservation], ...] = (),
) -> PrivateDirectoryFlushReview:
    return PrivateDirectoryFlushReview(
        state,
        "Windows scratch directory flush request is not a durable commit.",
        observations,
    )


class _FileTime(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]


class _FileInfo(ctypes.Structure):
    _fields_ = [
        ("attributes", wintypes.DWORD),
        ("created", _FileTime),
        ("accessed", _FileTime),
        ("written", _FileTime),
        ("volume", wintypes.DWORD),
        ("size_hi", wintypes.DWORD),
        ("size_lo", wintypes.DWORD),
        ("links", wintypes.DWORD),
        ("index_hi", wintypes.DWORD),
        ("index_lo", wintypes.DWORD),
    ]


def _kernel() -> Any:
    kernel: Any = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_FileInfo),
    ]
    kernel.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    kernel.FlushFileBuffers.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    return kernel


def _open(kernel: Any, path: Path) -> tuple[int | None, int]:
    # GENERIC_WRITE is documented for FlushFileBuffers, directory opening uses
    # BACKUP_SEMANTICS and refuses to traverse reparse points; OPEN_EXISTING only.
    raw = kernel.CreateFileW(
        str(path),
        0x40000000 | 0x80,
        7,
        None,
        3,
        0x02000000 | 0x00200000,
        None,
    )
    value = ctypes.cast(raw, ctypes.c_void_p).value
    if value is None or value == ctypes.c_void_p(-1).value:
        return None, ctypes.get_last_error()
    return value, 0


def _identity(kernel: Any, handle: int) -> tuple[int, int, int] | None:
    info = _FileInfo()
    if not kernel.GetFileInformationByHandle(
        wintypes.HANDLE(handle), ctypes.byref(info)
    ):
        return None
    if not info.attributes & 0x10 or info.attributes & 0x400:
        return None
    stamp = (int(info.volume), int(info.index_hi), int(info.index_lo))
    return stamp if any(stamp) else None


def _classified(code: int, *, opening: bool) -> PrivateDirectoryFlushObservation:
    kind = PrivateDirectoryFlushObservation
    if code in {5, 32, 33}:
        return kind.OPEN_ACCESS_DENIED if opening else kind.FLUSH_ACCESS_DENIED
    if opening:
        return kind.OPEN_UNSUPPORTED
    return (
        kind.FLUSH_UNSUPPORTED if code in {1, 6, 50, 87} else kind.FLUSH_OTHER_REFUSAL
    )


def _probe_one(kernel: Any, path: Path) -> PrivateDirectoryFlushObservation:
    if path.is_symlink() or not path.is_dir():
        return PrivateDirectoryFlushObservation.HANDLE_UNQUALIFIED
    handle: int | None = None
    reopened: int | None = None
    try:
        handle, error = _open(kernel, path)
        if handle is None:
            return _classified(error, opening=True)
        first = _identity(kernel, handle)
        if first is None:
            return PrivateDirectoryFlushObservation.HANDLE_UNQUALIFIED
        returned = bool(kernel.FlushFileBuffers(wintypes.HANDLE(handle)))
        error = ctypes.get_last_error() if not returned else 0
        reopened, _ = _open(kernel, path)
        if (
            reopened is None
            or _identity(kernel, handle) != first
            or _identity(kernel, reopened) != first
        ):
            return PrivateDirectoryFlushObservation.HANDLE_UNQUALIFIED
        return (
            PrivateDirectoryFlushObservation.RETURNED_UNQUALIFIED
            if returned
            else _classified(error, opening=False)
        )
    finally:
        if reopened is not None:
            kernel.CloseHandle(wintypes.HANDLE(reopened))
        if handle is not None:
            kernel.CloseHandle(wintypes.HANDLE(handle))


def _prepare(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _same(path: Path, raw: bytes) -> bool:
    try:
        before = path.lstat()
        with path.open("rb") as stream:
            held = os.fstat(stream.fileno())
            data = stream.read(len(raw) + 1)
        after = path.lstat()
        return (
            stat.S_ISREG(before.st_mode)
            and before.st_nlink == 1
            and (before.st_dev, before.st_ino, before.st_size)
            == (held.st_dev, held.st_ino, held.st_size)
            == (after.st_dev, after.st_ino, after.st_size)
            and data == raw
        )
    except OSError:
        return False


def probe_private_windows_directory_flush_contract() -> PrivateDirectoryFlushReview:
    """Probe only new disposable parents; never authorize retry or retirement.

    Results describe the temporary volume, not the production private root.
    Even a returned flush request is not proof of survived power loss.
    """
    state = PrivateDirectoryFlushState
    kind = PrivateDirectoryFlushObservation
    if sys.platform != "win32":
        return _result(state.UNSUPPORTED_PLATFORM)
    try:
        kernel = _kernel()
    except (OSError, ValueError, TypeError, AttributeError):
        return _result(state.NATIVE_UNAVAILABLE)
    findings: list[tuple[str, PrivateDirectoryFlushObservation]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="core238_3g49_dirprobe_") as directory:
            base = Path(directory)
            parents = (
                ("journal", base / "private" / "transactions", b"pending\n"),
                ("registry", base / "private", b"staged-registry\n"),
                ("descriptor", base / "workspace" / ".pds", b"staged-descriptor\n"),
            )
            for label, parent, image in parents:
                parent.mkdir(parents=True, exist_ok=True)
                try:
                    _prepare(parent / (label + ".probe"), image)
                except OSError:
                    return _result(state.FILE_FLUSH_REFUSED)
            if not all(
                _same(parent / (label + ".probe"), raw)
                for label, parent, raw in parents
            ):
                return _result(state.IDENTITY_CHANGED)
            for label, parent, _ in parents:
                findings.append((label, _probe_one(kernel, parent)))
            if not all(
                _same(parent / (label + ".probe"), raw)
                for label, parent, raw in parents
            ):
                return _result(state.IDENTITY_CHANGED, tuple(findings))
        observed = tuple(findings)
        if all(result is kind.RETURNED_UNQUALIFIED for _, result in observed):
            return _result(state.REQUESTS_RETURNED_UNQUALIFIED, observed)
        if any(result is kind.HANDLE_UNQUALIFIED for _, result in observed):
            return _result(state.IDENTITY_CHANGED, observed)
        if any(
            result in {kind.OPEN_ACCESS_DENIED, kind.OPEN_UNSUPPORTED}
            for _, result in observed
        ):
            return _result(state.OPEN_REFUSED, observed)
        return _result(state.FLUSH_REFUSED, observed)
    except KeyboardInterrupt:
        return _result(state.INTERRUPTED_PRESERVE, tuple(findings))
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(state.IO_ERROR_PRESERVE, tuple(findings))
