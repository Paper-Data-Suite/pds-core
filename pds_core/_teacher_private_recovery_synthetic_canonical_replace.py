"""Disposable canonical-intent two-root stage replacement (Core #238 3G34).

Only module-generated canonical metadata and fixed, synthetic OS-owner/root
labels are used. Native scratch lock and FOUR retained parent FD/HANDLE checks
cover exact journal, registry, descriptor and stage images, the restrictive
reader release, os.replace, post-image observation and file sync request.

This deliberately does NOT call a production writer, accept caller paths,
accept arbitrary intents or callbacks, prove OS-user ACL/backing custody,
prevent uncooperative same-user writers, prove directory-entry durability,
retire a journal, or expose any Notes capability. No successful status is a
permission to mutate teacher-private storage.
"""

from __future__ import annotations

import hashlib
import os
import stat
import sys
import tempfile
from contextlib import ExitStack
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import BinaryIO

from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_recovery_prepared_write_intent as prepared
from pds_core import _teacher_private_recovery_synthetic_identity_custody as identity
from pds_core import _teacher_private_recovery_synthetic_native_writer as scratch
from pds_core import _teacher_private_recovery_synthetic_owned_scope as owned
from pds_core import _teacher_private_recovery_synthetic_two_root_replace as two
from pds_core import _teacher_private_recovery_synthetic_windows_share as winshare
from pds_core import _teacher_private_recovery_synthetic_writer_admission as admission
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witnesses


class PrivateCanonicalReplaceFault(str, Enum):
    NONE = "none"
    AFTER_LOCK = "after_lock"
    AFTER_PARENTS = "after_parents"
    AFTER_CANONICAL_ADMISSION = "after_canonical_admission"
    AFTER_PREIMAGE = "after_preimage"
    AFTER_READER_RELEASE = "after_reader_release"
    BEFORE_REPLACE = "before_replace"
    AFTER_REPLACE = "after_replace"
    AFTER_POSTIMAGE = "after_postimage"
    AFTER_FILE_SYNC = "after_file_sync"
    AFTER_PARENT_RELEASE = "after_parent_release"


class PrivateCanonicalReplaceState(str, Enum):
    SCRATCH_CANONICAL_REPLACEMENT_UNQUALIFIED = (
        "scratch_canonical_replacement_unqualified"
    )
    INVALID_REQUEST = "invalid_request"
    OPERATION_NOT_ADMITTED = "operation_not_admitted"
    UNSUPPORTED = "unsupported"
    CANONICAL_INTENT_REFUSED = "canonical_intent_refused"
    PREIMAGE_REFUSED = "preimage_refused"
    NAMESPACE_CONFLICT_PRESERVE = "namespace_conflict_preserve"
    PARENT_CONFLICT_PRESERVE = "parent_conflict_preserve"
    FILE_CONFLICT_PRESERVE = "file_conflict_preserve"
    IMAGE_CONFLICT_PRESERVE = "image_conflict_preserve"
    READER_CONFLICT_PRESERVE = "reader_conflict_preserve"
    ADMISSION_DRIFT_PRESERVE = "admission_drift_preserve"
    REPLACEMENT_REFUSED_PRESERVE = "replacement_refused_preserve"
    POSTIMAGE_CONFLICT_PRESERVE = "postimage_conflict_preserve"
    INTERRUPTED_PRESERVE = "interrupted_preserve"
    GUARD_REFUSED = "guard_refused"
    IO_ERROR = "io_error"


_MESSAGES = {
    PrivateCanonicalReplaceState.SCRATCH_CANONICAL_REPLACEMENT_UNQUALIFIED: "Disposable two-root canonical stage replacement observed; no production write or durable commit.",
    PrivateCanonicalReplaceState.INVALID_REQUEST: "Synthetic replacement parameters refused.",
    PrivateCanonicalReplaceState.OPERATION_NOT_ADMITTED: "Only one fixed synthetic stage-to-registry operation is supported.",
    PrivateCanonicalReplaceState.UNSUPPORTED: "Native scratch custody unsupported on this platform.",
    PrivateCanonicalReplaceState.CANONICAL_INTENT_REFUSED: "Canonical synthetic transaction intent was refused.",
    PrivateCanonicalReplaceState.PREIMAGE_REFUSED: "Synthetic prepared image or native identity was unqualified.",
    PrivateCanonicalReplaceState.NAMESPACE_CONFLICT_PRESERVE: "Disposable recovery namespace changed or was unqualified.",
    PrivateCanonicalReplaceState.PARENT_CONFLICT_PRESERVE: "Retained native scratch parent identity was unqualified.",
    PrivateCanonicalReplaceState.FILE_CONFLICT_PRESERVE: "Disposable file identity conflicted with expected native evidence.",
    PrivateCanonicalReplaceState.IMAGE_CONFLICT_PRESERVE: "Canonical intent digests or exact bytes conflicted.",
    PrivateCanonicalReplaceState.READER_CONFLICT_PRESERVE: "Restrictive registry reader did not qualify.",
    PrivateCanonicalReplaceState.ADMISSION_DRIFT_PRESERVE: "Prepared native evidence changed before replacement.",
    PrivateCanonicalReplaceState.REPLACEMENT_REFUSED_PRESERVE: "Scratch native replace refused; no fallback is authorized.",
    PrivateCanonicalReplaceState.POSTIMAGE_CONFLICT_PRESERVE: "Disposable after-image or stage retirement from namespace conflicted.",
    PrivateCanonicalReplaceState.INTERRUPTED_PRESERVE: "Synthetic in-process interruption; no completion or restart claim.",
    PrivateCanonicalReplaceState.GUARD_REFUSED: "Scratch lock or native custody was refused, including release.",
    PrivateCanonicalReplaceState.IO_ERROR: "Native synthetic recovery rehearsal encountered an I/O refusal.",
}


@dataclass(frozen=True, slots=True, repr=False)
class PrivateCanonicalReplaceReview:
    state: PrivateCanonicalReplaceState
    message: str

    def __repr__(self) -> str:
        return "PrivateCanonicalReplaceReview(non_authorizing=True)"


def _result(state: PrivateCanonicalReplaceState) -> PrivateCanonicalReplaceReview:
    return PrivateCanonicalReplaceReview(state, _MESSAGES[state])


class _Interrupted(Exception):
    pass


class _Namespace(Exception):
    pass


class _Images(Exception):
    pass


class _Files(Exception):
    pass


class _Reader(Exception):
    pass


class _Parents(Exception):
    pass


_ASSOCIATION = "6fb32a62-83e2-43f6-9823-687801593c8b"
_TRANSACTION = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"
_JOURNAL = "pending-transaction.json"
_DESCRIPTOR = "teacher-private-association.json"


def _sha(raw: bytes | None) -> str | None:
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def _canonical() -> intents.PrivateTransactionIntent:
    """Construct genuine v1 metadata with FIXED NON-OS synthetic identity."""
    owner = metadata.PrivateRegistryOwner("posix_euid", "1000")
    first = metadata.PrivateRegistryBinding(_ASSOCIATION, 1, "/synthetic_before")
    next_binding = metadata.PrivateRegistryBinding(_ASSOCIATION, 2, "/synthetic_after")
    prior = metadata.encode_private_registry(
        metadata.PrivateRegistry(owner, 2, (first,))
    )
    later = metadata.encode_private_registry(
        metadata.PrivateRegistry(owner, 3, (next_binding,))
    )
    descriptor_bytes = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(_ASSOCIATION)
    )
    witness = witnesses.PrivateTransactionWitness(
        operation=witnesses.PrivateBindingOperation.REBIND_MOVE,
        transaction_id=_TRANSACTION,
        association_before=_ASSOCIATION,
        association_after=_ASSOCIATION,
        registry_revision_before=2,
        registry_revision_after=3,
        descriptor_sha256_before=_sha(descriptor_bytes),
        descriptor_sha256_after=_sha(descriptor_bytes) or "",
        registry_sha256_before=_sha(prior),
        registry_sha256_after=_sha(later) or "",
    )
    return intents.PrivateTransactionIntent(
        witness, descriptor_bytes, descriptor_bytes, prior, later
    )


@dataclass(frozen=True, slots=True)
class _Census:
    parents: tuple[tuple[int, int], ...]
    registry: tuple[int, int]
    journal: tuple[int, int]
    descriptor: tuple[int, int]
    guard: tuple[int, int]
    stage: tuple[int, int] | None


def _names(path: Path, wanted: set[str]) -> bool:
    entries = list(path.iterdir())
    return (
        len(entries) == len(wanted)
        and {entry.name for entry in entries} == wanted
        and not any(entry.is_symlink() for entry in entries)
    )


def _exact(path: Path, expected: bytes) -> bool:
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        return False
    with path.open("rb") as stream:
        return stream.read(len(expected) + 1) == expected


def _observe(
    paths: two._Paths,
    checked: intents.PrivateTransactionIntent,
    raw: bytes,
    *,
    stage: bool,
) -> _Census:
    """Four root identity stamps and five exact byte images under scratch custody."""
    private_names = {scratch._REGISTRY, scratch._LOCK, "transactions"}
    if stage:
        private_names.add(scratch._STAGE)
    if not (
        _names(paths.private, private_names)
        and _names(paths.transactions, {_JOURNAL})
        and _names(paths.workspace, {".pds"})
        and _names(paths.association_dir, {_DESCRIPTOR})
    ):
        raise _Namespace
    before = checked.registry_before
    after = checked.registry_after
    sidecar = checked.descriptor_before
    if (
        type(before) is not bytes
        or type(after) is not bytes
        or type(sidecar) is not bytes
    ):
        raise _Images
    expected = (
        (paths.transactions / _JOURNAL, raw),
        (paths.private / scratch._REGISTRY, before if stage else after),
        (paths.association_dir / _DESCRIPTOR, sidecar),
    )
    if not two._locked_file_shape(paths.private / scratch._LOCK) or not all(
        _exact(path, image) for path, image in expected
    ):
        raise _Images
    if stage and not _exact(paths.private / scratch._STAGE, after):
        raise _Images
    root_ids = tuple(admission._parent_id(root) for root in two._parents(paths))
    if len(set(root_ids)) != 4:
        raise _Parents
    registry = identity._identity(paths.private, scratch._REGISTRY)
    journal = identity._identity(paths.transactions, _JOURNAL)
    descriptor = identity._identity(paths.association_dir, _DESCRIPTOR)
    guard = identity._identity(paths.private, scratch._LOCK)
    stage_id = identity._identity(paths.private, scratch._STAGE) if stage else None
    all_ids = {registry, journal, descriptor, guard}
    if stage_id is not None:
        all_ids.add(stage_id)
    if len(all_ids) != (5 if stage else 4):
        raise _Files
    return _Census(root_ids, registry, journal, descriptor, guard, stage_id)


def _held(checks: tuple[object, ...]) -> bool:
    return len(checks) == 4 and all(
        callable(check) and check() is True for check in checks
    )


def _reader(paths: two._Paths, expected_id: tuple[int, int], image: bytes) -> bool:
    """The restrictive Windows HANDLE is closed before the native replace."""
    registry_path = paths.private / scratch._REGISTRY
    if sys.platform == "win32":
        with winshare._native_target(
            registry_path, winshare.PrivateSyntheticWindowsShareMode.NO_DELETE_SHARE
        ) as stream:
            return _held_bytes(stream, expected_id, image)
    with registry_path.open("rb") as stream:
        return _held_bytes(stream, expected_id, image)


def _held_bytes(stream: BinaryIO, expected_id: tuple[int, int], image: bytes) -> bool:
    info = os.fstat(stream.fileno())
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or (info.st_dev, info.st_ino) != expected_id
        or info.st_size != len(image)
    ):
        return False
    stream.seek(0)
    return stream.read(len(image) + 1) == image


def _interrupt(
    selected: PrivateCanonicalReplaceFault, at: PrivateCanonicalReplaceFault
) -> None:
    if selected is at:
        raise _Interrupted


def _make_layout(
    base: Path, checked: intents.PrivateTransactionIntent, raw: bytes
) -> two._Paths:
    private = base / "private"
    transactions = private / "transactions"
    workspace = base / "workspace"
    association = workspace / ".pds"
    transactions.mkdir(parents=True)
    association.mkdir(parents=True)
    before = checked.registry_before
    sidecar = checked.descriptor_before
    if type(before) is not bytes or type(sidecar) is not bytes:
        raise _Images
    scratch._write_new(private, scratch._REGISTRY, before)
    scratch._write_new(private, scratch._STAGE, checked.registry_after)
    scratch._write_new(transactions, _JOURNAL, raw)
    scratch._write_new(association, _DESCRIPTOR, sidecar)
    return two._Paths(private, transactions, workspace, association)


def _post(before: _Census, after: _Census) -> bool:
    return (
        before.parents == after.parents
        and before.stage is not None
        and after.registry == before.stage
        and after.registry != before.registry
        and after.journal == before.journal
        and after.descriptor == before.descriptor
        and after.guard == before.guard
        and after.stage is None
    )


def rehearse_synthetic_canonical_two_root_replace(
    step: admission.PrivateScratchWriterStep = admission.PrivateScratchWriterStep.STAGE_TO_REGISTRY,
    interruption: PrivateCanonicalReplaceFault = PrivateCanonicalReplaceFault.NONE,
) -> PrivateCanonicalReplaceReview:
    """Execute a canonical metadata replacement ONLY on internally owned scratch.

    Positive result is explicitly NOT a native production authorization, a
    durable commit, a safe journal-retirement state, or Notes service.
    """
    state = PrivateCanonicalReplaceState
    fault = PrivateCanonicalReplaceFault
    if (
        type(step) is not admission.PrivateScratchWriterStep
        or type(interruption) is not fault
    ):
        return _result(state.INVALID_REQUEST)
    if step is not admission.PrivateScratchWriterStep.STAGE_TO_REGISTRY:
        return _result(state.OPERATION_NOT_ADMITTED)
    if sys.platform not in {"win32", "linux"}:
        return _result(state.UNSUPPORTED)
    reached_operation = False
    try:
        checked = _canonical()
        raw = intents.encode_private_transaction_intent(checked)
        if (
            intents.decode_private_transaction_intent(raw) != checked
            or intents.encode_private_transaction_intent(checked) != raw
        ):
            return _result(state.CANONICAL_INTENT_REFUSED)
        first = prepared.describe_private_prepared_stage_write_intent(step, 2, checked)
        if (
            first.state
            is not prepared.PrivatePreparedWriteIntentState.DESCRIPTION_ONLY_REVIEW_REQUIRED
            or first.description is None
            or first.description.pending_intent_sha256 != _sha(raw)
        ):
            return _result(state.CANONICAL_INTENT_REFUSED)
        with tempfile.TemporaryDirectory(prefix="core238_3g34_canonical_") as temp:
            paths = _make_layout(Path(temp), checked, raw)
            with scratch._scratch_lock(paths.private / scratch._LOCK):
                _interrupt(interruption, fault.AFTER_LOCK)
                with ExitStack() as stack:
                    checks = tuple(
                        stack.enter_context(owned._held_native_parent(path))
                        for path in two._parents(paths)
                    )
                    if not _held(checks):
                        raise _Parents
                    _interrupt(interruption, fault.AFTER_PARENTS)
                    second = prepared.describe_private_prepared_stage_write_intent(
                        step, 2, checked
                    )
                    if (
                        second.description != first.description
                        or second.state is not first.state
                    ):
                        return _result(state.CANONICAL_INTENT_REFUSED)
                    if not _held(checks):
                        raise _Parents
                    _interrupt(interruption, fault.AFTER_CANONICAL_ADMISSION)
                    baseline = _observe(paths, checked, raw, stage=True)
                    if baseline.stage is None or baseline.stage == baseline.registry:
                        return _result(state.PREIMAGE_REFUSED)
                    _interrupt(interruption, fault.AFTER_PREIMAGE)
                    if not _reader(
                        paths, baseline.registry, checked.registry_before or b""
                    ):
                        return _result(state.READER_CONFLICT_PRESERVE)
                    _interrupt(interruption, fault.AFTER_READER_RELEASE)
                    for _ in range(3):
                        if not _held(checks):
                            raise _Parents
                        if _observe(paths, checked, raw, stage=True) != baseline:
                            return _result(state.ADMISSION_DRIFT_PRESERVE)
                    _interrupt(interruption, fault.BEFORE_REPLACE)
                    if not _held(checks):
                        raise _Parents
                    reached_operation = True
                    try:
                        os.replace(
                            paths.private / scratch._STAGE,
                            paths.private / scratch._REGISTRY,
                        )
                    except OSError as error:
                        if isinstance(error, PermissionError) or getattr(
                            error, "winerror", None
                        ) in (5, 32, 33):
                            return _result(state.REPLACEMENT_REFUSED_PRESERVE)
                        raise
                    _interrupt(interruption, fault.AFTER_REPLACE)
                    if not _held(checks):
                        raise _Parents
                    after = _observe(paths, checked, raw, stage=False)
                    if not _post(baseline, after):
                        return _result(state.POSTIMAGE_CONFLICT_PRESERVE)
                    _interrupt(interruption, fault.AFTER_POSTIMAGE)
                    scratch._sync_target(paths.private)
                    _interrupt(interruption, fault.AFTER_FILE_SYNC)
                    if not _held(checks) or not _post(
                        baseline, _observe(paths, checked, raw, stage=False)
                    ):
                        return _result(state.POSTIMAGE_CONFLICT_PRESERVE)
                _interrupt(interruption, fault.AFTER_PARENT_RELEASE)
            return _result(state.SCRATCH_CANONICAL_REPLACEMENT_UNQUALIFIED)
    except (_Interrupted, KeyboardInterrupt):
        return _result(state.INTERRUPTED_PRESERVE)
    except scratch._GuardRefused:
        return _result(state.GUARD_REFUSED)
    except (owned._ParentUnqualified, admission._ParentUnqualified, _Parents):
        return _result(state.PARENT_CONFLICT_PRESERVE)
    except _Namespace:
        return _result(state.NAMESPACE_CONFLICT_PRESERVE)
    except (_Images, scratch._UnsafeImage):
        return _result(
            state.POSTIMAGE_CONFLICT_PRESERVE
            if reached_operation
            else state.IMAGE_CONFLICT_PRESERVE
        )
    except (identity._IdentityUnavailable, _Files):
        return _result(
            state.FILE_CONFLICT_PRESERVE
            if reached_operation
            else state.PREIMAGE_REFUSED
        )
    except _Reader:
        return _result(state.READER_CONFLICT_PRESERVE)
    except FileNotFoundError:
        return _result(
            state.POSTIMAGE_CONFLICT_PRESERVE
            if reached_operation
            else state.PREIMAGE_REFUSED
        )
    except PermissionError:
        return _result(
            state.REPLACEMENT_REFUSED_PRESERVE
            if reached_operation
            else state.GUARD_REFUSED
        )
    except (
        intents.PrivateIntentError,
        metadata.PrivateMetadataError,
        witnesses.PrivateTransactionError,
    ):
        return _result(state.CANONICAL_INTENT_REFUSED)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return _result(state.IO_ERROR)
