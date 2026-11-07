"""Canonical two-document FORK_COPY + fresh-restart drill (#238 Slice 3G52).

Only internally generated canonical metadata, fixed NON-OS synthetic identity,
and fresh TemporaryDirectory paths enter this transaction. A journal and two
stages are written, flushes are requested, and registry then descriptor stages
are replaced. The first scratch lock is released before a separately acquired
restart lock reopens and verifies all exact images and namespaces. No caller
path, arbitrary intent, callback, retry token or production writer is accepted.

This remains synthetic. A passing flush is neither crash/power-loss durability
nor OS-private custody; no result authorizes a write, replay, journal retirement,
commit, or access to Notes. All injected interruptions retain journal evidence
until the private disposable directory is destroyed by the test harness.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_registry_stage_transition as transition
from pds_core import _teacher_private_recovery_durable_scratch_sequence as durable
from pds_core import _teacher_private_recovery_journaled_restart_drill as prior
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witnesses

_ASSOCIATION_BEFORE = "6fb32a62-83e2-43f6-9823-687801593c8b"
_ASSOCIATION_AFTER = "661281eb-35e0-40c8-bedd-bd6238a19b4a"
_TRANSACTION = "e3ba2e44-3f47-4588-9023-44cbb799d5a8"


class PrivateCanonicalRestartFault(str, Enum):
    NONE = "none"
    AFTER_PREPARED_FLUSH = "after_prepared_flush"
    AFTER_REGISTRY_REPLACE = "after_registry_replace"
    AFTER_REGISTRY_FLUSH = "after_registry_flush"
    AFTER_DESCRIPTOR_REPLACE = "after_descriptor_replace"
    AFTER_DESCRIPTOR_FLUSH = "after_descriptor_flush"
    AFTER_OPERATION_LOCK_RELEASE = "after_operation_lock_release"


class PrivateCanonicalRestartCheckpoint(str, Enum):
    PREPARED_HOLD = "prepared_hold"
    REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD = "registry_after_descriptor_pending_hold"
    BOTH_AFTER_JOURNAL_PENDING_HOLD = "both_after_journal_pending_hold"
    CONFLICT_PRESERVE = "conflict_preserve"
    OBSERVATION_REFUSED = "observation_refused"


class PrivateCanonicalRestartState(str, Enum):
    CANONICAL_SCRATCH_AFTER_IMAGES_UNQUALIFIED = (
        "canonical_scratch_after_images_unqualified"
    )
    INJECTED_INTERRUPTION_HOLD = "injected_interruption_hold"
    FILE_OR_DIRECTORY_FLUSH_REFUSED_HOLD = "file_or_directory_flush_refused_hold"
    NATIVE_REPLACEMENT_OUTCOME_UNKNOWN_HOLD = "native_replacement_outcome_unknown_hold"
    CANONICAL_IMAGE_CONFLICT_PRESERVE = "canonical_image_conflict_preserve"
    GUARD_REFUSED_PRESERVE = "guard_refused_preserve"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    SCRATCH_IO_REFUSED = "scratch_io_refused"


@dataclass(frozen=True, slots=True, repr=False)
class PrivateCanonicalRestartReview:
    state: PrivateCanonicalRestartState
    checkpoint: PrivateCanonicalRestartCheckpoint
    replacement_may_have_occurred: bool
    journal_seen_at_restart: bool
    pending_evidence_must_remain: bool = True
    production_writes_blocked: bool = True
    automatic_replay_forbidden: bool = True
    journal_retirement_forbidden: bool = True
    durability_unqualified: bool = True
    phases: tuple[str, ...] = field(default=(), repr=False)

    def __repr__(self) -> str:
        return "PrivateCanonicalRestartReview(non_authorizing=True)"


def _result(
    state: PrivateCanonicalRestartState,
    checkpoint: PrivateCanonicalRestartCheckpoint = (
        PrivateCanonicalRestartCheckpoint.OBSERVATION_REFUSED
    ),
    *,
    attempted: bool = False,
    journal_seen: bool = False,
    phases: tuple[str, ...] = (),
) -> PrivateCanonicalRestartReview:
    return PrivateCanonicalRestartReview(
        state,
        checkpoint,
        attempted,
        journal_seen,
        True,
        True,
        True,
        True,
        True,
        phases,
    )


class _Interrupted(Exception):
    pass


def _sha(value: bytes | None) -> str | None:
    return hashlib.sha256(value).hexdigest() if value is not None else None


def _canonical_fork_intent() -> intents.PrivateTransactionIntent:
    """Create a *real* canonical two-document FORK_COPY with fixed fake identity."""
    owner = metadata.PrivateRegistryOwner("posix_euid", "1000")
    old = metadata.PrivateRegistryBinding(_ASSOCIATION_BEFORE, 1, "/synthetic_existing")
    new = metadata.PrivateRegistryBinding(_ASSOCIATION_AFTER, 1, "/synthetic_fork")
    before = metadata.encode_private_registry(
        metadata.PrivateRegistry(owner, 2, (old,))
    )
    after = metadata.encode_private_registry(
        metadata.PrivateRegistry(owner, 3, (old, new))
    )
    descriptor_before = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(_ASSOCIATION_BEFORE)
    )
    descriptor_after = metadata.encode_association_descriptor(
        metadata.PrivateAssociationDescriptor(_ASSOCIATION_AFTER)
    )
    witness = witnesses.PrivateTransactionWitness(
        operation=witnesses.PrivateBindingOperation.FORK_COPY,
        transaction_id=_TRANSACTION,
        association_before=_ASSOCIATION_BEFORE,
        association_after=_ASSOCIATION_AFTER,
        registry_revision_before=2,
        registry_revision_after=3,
        descriptor_sha256_before=_sha(descriptor_before),
        descriptor_sha256_after=_sha(descriptor_after) or "",
        registry_sha256_before=_sha(before),
        registry_sha256_after=_sha(after) or "",
    )
    candidate = intents.PrivateTransactionIntent(
        witness, descriptor_before, descriptor_after, before, after
    )
    encoded = intents.encode_private_transaction_intent(candidate)
    checked = intents.decode_private_transaction_intent(encoded)
    if (
        checked != candidate
        or intents.encode_private_transaction_intent(checked) != encoded
        or candidate.descriptor_before == candidate.descriptor_after
        or candidate.registry_before == candidate.registry_after
    ):
        raise ValueError("Canonical synthetic intent refused")
    return checked


def _paths(private: Path, descriptor_directory: Path) -> tuple[Path, ...]:
    """Derive ONLY hardcoded, disposable names; never accept external operations."""
    return (
        private / "registry.json",
        private / ("." + _TRANSACTION + ".registry-stage"),
        descriptor_directory / "teacher-private-association.json",
        descriptor_directory / ("." + _TRANSACTION + ".descriptor-stage"),
        private / "transactions" / (_TRANSACTION + ".json"),
    )


def _checkpoint(
    private: Path, descriptor_directory: Path, checked: intents.PrivateTransactionIntent
) -> PrivateCanonicalRestartCheckpoint:
    """Strict two-root names plus exact genuine journal/metadata after reopen."""
    checkpoint = PrivateCanonicalRestartCheckpoint
    registry, registry_stage, descriptor, descriptor_stage, journal = _paths(
        private, descriptor_directory
    )
    raw = intents.encode_private_transaction_intent(checked)
    before = checked.registry_before
    d_before = checked.descriptor_before
    if type(before) is not bytes or type(d_before) is not bytes:
        return checkpoint.CONFLICT_PRESERVE
    try:
        stage_exists = registry_stage.exists()
        descriptor_stage_exists = descriptor_stage.exists()
        if (
            not prior._names(private / "transactions", frozenset({journal.name}))
            or not prior._names(
                private,
                frozenset({"registry.json", "transactions", ".native-lock"})
                | (frozenset({registry_stage.name}) if stage_exists else frozenset()),
            )
            or not prior._names(
                descriptor_directory,
                frozenset({descriptor.name})
                | (
                    frozenset({descriptor_stage.name})
                    if descriptor_stage_exists
                    else frozenset()
                ),
            )
            or not durable._exact(journal, raw)
            or (
                stage_exists
                and not durable._exact(registry_stage, checked.registry_after)
            )
            or (
                descriptor_stage_exists
                and not durable._exact(descriptor_stage, checked.descriptor_after)
            )
        ):
            return checkpoint.CONFLICT_PRESERVE
        # Use exact byte predicates, not unauthenticated read_text or stale reviews.
        registry_before = durable._exact(registry, before)
        registry_after = durable._exact(registry, checked.registry_after)
        descriptor_before = durable._exact(descriptor, d_before)
        descriptor_after = durable._exact(descriptor, checked.descriptor_after)
        if (
            registry_before
            and descriptor_before
            and stage_exists
            and descriptor_stage_exists
        ):
            expected = transition.PrivateRegistryStageTransitionState.PRE_REPLACE_REVIEW_REQUIRED
            outcome = checkpoint.PREPARED_HOLD
        elif (
            registry_after
            and descriptor_before
            and not stage_exists
            and descriptor_stage_exists
        ):
            expected = transition.PrivateRegistryStageTransitionState.REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED
            outcome = checkpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD
        elif (
            registry_after
            and descriptor_after
            and not stage_exists
            and not descriptor_stage_exists
        ):
            expected = transition.PrivateRegistryStageTransitionState.BOTH_AFTER_RETIREMENT_REVIEW_REQUIRED
            outcome = checkpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD
        else:
            return checkpoint.CONFLICT_PRESERVE
        # A *pure* canonical classifier must independently agree with the snapshot.
        classified = transition.classify_private_registry_stage_transition(
            checked,
            observed_journal=raw,
            observed_registry=before if registry_before else checked.registry_after,
            observed_descriptor=d_before
            if descriptor_before
            else checked.descriptor_after,
            observed_stage=checked.registry_after if stage_exists else None,
        )
        if classified.state is not expected:
            return checkpoint.CONFLICT_PRESERVE
        return outcome
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return checkpoint.CONFLICT_PRESERVE


def _inject(
    selected: PrivateCanonicalRestartFault, at: PrivateCanonicalRestartFault
) -> None:
    if selected is at:
        raise _Interrupted


def rehearse_canonical_two_document_restart(
    interruption: PrivateCanonicalRestartFault = PrivateCanonicalRestartFault.NONE,
) -> PrivateCanonicalRestartReview:
    """One scratch-only canonical FORK_COPY transaction with fresh restart lock.

    TemporaryDirectory cleanup is NOT production journal retirement. This never
    accepts teacher-private roots, intents, native handles or retry callbacks.
    """
    state = PrivateCanonicalRestartState
    checkpoint = PrivateCanonicalRestartCheckpoint
    fault = PrivateCanonicalRestartFault
    if type(interruption) is not fault:
        return _result(state.INVALID_REQUEST)
    if sys.platform not in {"linux", "win32"}:
        return _result(state.UNSUPPORTED)
    attempted = False
    phases: list[str] = []
    try:
        checked = _canonical_fork_intent()
        journal_image = intents.encode_private_transaction_intent(checked)
        with tempfile.TemporaryDirectory(prefix="core238_3g52_canonical_") as temporary:
            root = Path(temporary)
            private = root / "private"
            transactions = private / "transactions"
            descriptor_directory = root / "workspace" / ".pds"
            transactions.mkdir(parents=True)
            descriptor_directory.mkdir(parents=True)
            registry, registry_stage, descriptor, descriptor_stage, journal = _paths(
                private, descriptor_directory
            )
            failure: PrivateCanonicalRestartState | None = None
            try:
                with durable._scratch_lock(private / ".native-lock"):
                    for path, image in (
                        (registry, checked.registry_before),
                        (registry_stage, checked.registry_after),
                        (descriptor, checked.descriptor_before),
                        (descriptor_stage, checked.descriptor_after),
                        (journal, journal_image),
                    ):
                        if type(image) is not bytes:
                            raise ValueError("Canonical intent missing image")
                        durable._write_new(path, image)
                    if (
                        _checkpoint(private, descriptor_directory, checked)
                        is not checkpoint.PREPARED_HOLD
                    ):
                        failure = state.CANONICAL_IMAGE_CONFLICT_PRESERVE
                    else:
                        for path in (journal, registry_stage, descriptor_stage):
                            durable._file_flush(path)
                        phases.append("journal_and_stages_flushed")
                        for path in (transactions, private, descriptor_directory):
                            durable._directory_flush(path)
                        phases.append("prepared_parents_flushed")
                        _inject(interruption, fault.AFTER_PREPARED_FLUSH)
                        if (
                            _checkpoint(private, descriptor_directory, checked)
                            is not checkpoint.PREPARED_HOLD
                        ):
                            failure = state.CANONICAL_IMAGE_CONFLICT_PRESERVE
                        else:
                            attempted = True
                            os.replace(registry_stage, registry)
                            phases.append("registry_replaced")
                            _inject(interruption, fault.AFTER_REGISTRY_REPLACE)
                            if (
                                _checkpoint(private, descriptor_directory, checked)
                                is not checkpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD
                            ):
                                failure = state.CANONICAL_IMAGE_CONFLICT_PRESERVE
                            else:
                                durable._file_flush(registry)
                                durable._directory_flush(private)
                                phases.append("registry_flush_requested")
                                _inject(interruption, fault.AFTER_REGISTRY_FLUSH)
                                if (
                                    _checkpoint(private, descriptor_directory, checked)
                                    is not checkpoint.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD
                                ):
                                    failure = state.CANONICAL_IMAGE_CONFLICT_PRESERVE
                                else:
                                    os.replace(descriptor_stage, descriptor)
                                    phases.append("descriptor_replaced")
                                    _inject(
                                        interruption, fault.AFTER_DESCRIPTOR_REPLACE
                                    )
                                    if (
                                        _checkpoint(
                                            private, descriptor_directory, checked
                                        )
                                        is not checkpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD
                                    ):
                                        failure = (
                                            state.CANONICAL_IMAGE_CONFLICT_PRESERVE
                                        )
                                    else:
                                        durable._file_flush(descriptor)
                                        durable._directory_flush(descriptor_directory)
                                        phases.append("descriptor_flush_requested")
                                        _inject(
                                            interruption, fault.AFTER_DESCRIPTOR_FLUSH
                                        )
                                        if (
                                            _checkpoint(
                                                private, descriptor_directory, checked
                                            )
                                            is not checkpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD
                                        ):
                                            failure = (
                                                state.CANONICAL_IMAGE_CONFLICT_PRESERVE
                                            )
            except (_Interrupted, KeyboardInterrupt):
                failure = state.INJECTED_INTERRUPTION_HOLD
            except (durable._DirectoryFlushRefused, durable._FileFlushRefused):
                failure = state.FILE_OR_DIRECTORY_FLUSH_REFUSED_HOLD
            except durable._GuardRefused:
                failure = state.GUARD_REFUSED_PRESERVE
            except (OSError, ValueError, TypeError, AttributeError, OverflowError):
                failure = (
                    state.NATIVE_REPLACEMENT_OUTCOME_UNKNOWN_HOLD
                    if attempted
                    else state.SCRATCH_IO_REFUSED
                )
            # Deliberately do not carry the operation-owned handle into restart.
            try:
                _inject(interruption, fault.AFTER_OPERATION_LOCK_RELEASE)
            except (_Interrupted, KeyboardInterrupt):
                failure = state.INJECTED_INTERRUPTION_HOLD
            try:
                with prior._held_existing_restart_lock(private / ".native-lock"):
                    observed = _checkpoint(private, descriptor_directory, checked)
                    journal_seen = durable._exact(journal, journal_image)
            except (prior._RestartGuardRefused, KeyboardInterrupt, OSError, ValueError):
                return _result(
                    state.GUARD_REFUSED_PRESERVE,
                    attempted=attempted,
                    phases=tuple(phases),
                )
            if not journal_seen or observed is checkpoint.CONFLICT_PRESERVE:
                failure = state.CANONICAL_IMAGE_CONFLICT_PRESERVE
            if failure is None:
                failure = (
                    state.CANONICAL_SCRATCH_AFTER_IMAGES_UNQUALIFIED
                    if observed is checkpoint.BOTH_AFTER_JOURNAL_PENDING_HOLD
                    else state.CANONICAL_IMAGE_CONFLICT_PRESERVE
                )
            return _result(
                failure,
                observed,
                attempted=attempted,
                journal_seen=journal_seen,
                phases=tuple(phases),
            )
    except (
        KeyboardInterrupt,
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
    ):
        return _result(
            state.NATIVE_REPLACEMENT_OUTCOME_UNKNOWN_HOLD
            if attempted
            else state.SCRATCH_IO_REFUSED,
            attempted=attempted,
            phases=tuple(phases),
        )
