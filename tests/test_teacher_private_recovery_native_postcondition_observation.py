"""Core #238 3G16: native protected postimage observation, never a writer."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_metadata as metadata
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_postcrash_reconciliation as recovery
from pds_core import _teacher_private_recovery_exact_revision_review as exact
from pds_core import (
    _teacher_private_recovery_native_postcondition_observation as native,
)
from pds_core import _teacher_private_recovery_operation_guard as operation
from pds_core import _teacher_private_recovery_operation_postconditions as post
from pds_core import _teacher_private_retained_descriptor_guard as retained
from pds_core import _teacher_private_transaction_intent as intents
from pds_core import _teacher_private_transaction_witness as witness
from pds_core.teacher_experience import get_teacher_experience_capabilities

State = native.PrivateNativeRecoveryPostimageState
Kind = post.PrivateRecoveryOperationKind

JOURNAL = b"canonical-private-intent"
REGISTRY_BEFORE = b"registry-revision-7"
REGISTRY_AFTER = b"registry-revision-8"
DESCRIPTOR_BEFORE = b"descriptor-before"
DESCRIPTOR_AFTER = b"descriptor-after"
TX = "11111111-1111-4111-8111-111111111111"


def _intent() -> intents.PrivateTransactionIntent:
    value = object.__new__(intents.PrivateTransactionIntent)
    object.__setattr__(
        value,
        "witness",
        SimpleNamespace(
            operation=witness.PrivateBindingOperation.REBIND_MOVE,
            transaction_id=TX,
            registry_revision_before=7,
            registry_revision_after=8,
        ),
    )
    object.__setattr__(value, "registry_before", REGISTRY_BEFORE)
    object.__setattr__(value, "registry_after", REGISTRY_AFTER)
    object.__setattr__(value, "descriptor_before", DESCRIPTOR_BEFORE)
    object.__setattr__(value, "descriptor_after", DESCRIPTOR_AFTER)
    return value


INTENT = _intent()
KINDS = (Kind.STAGE_TO_REGISTRY, Kind.DESCRIPTOR_AFTER_IMAGE)


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    *,
    kind: Kind = Kind.STAGE_TO_REGISTRY,
    images: list[object] | None = None,
    namespaces: list[object] | None = None,
    owner_values: list[object] | None = None,
    namespace_results: list[bool] | None = None,
    throw: BaseException | None = None,
    throw_at: str = "",
    release_error: BaseException | None = None,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(
        intents, "encode_private_transaction_intent", lambda *_: JOURNAL
    )
    monkeypatch.setattr(intents, "decode_private_transaction_intent", lambda *_: INTENT)

    def decode(raw: bytes) -> SimpleNamespace:
        if raw == REGISTRY_BEFORE:
            return SimpleNamespace(revision=7)
        if raw == REGISTRY_AFTER:
            return SimpleNamespace(revision=8)
        raise metadata.PrivateMetadataError(
            metadata.PrivateMetadataErrorCode.INVALID_SHAPE
        )

    def encode(value: SimpleNamespace) -> bytes:
        return REGISTRY_BEFORE if value.revision == 7 else REGISTRY_AFTER

    monkeypatch.setattr(metadata, "decode_private_registry", decode)
    monkeypatch.setattr(metadata, "encode_private_registry", encode)
    active = [False]

    @contextmanager
    def guard(*_args: object) -> Iterator[None]:
        calls.append("acquire")
        assert not active[0]
        active[0] = True
        try:
            yield
        finally:
            active[0] = False
            calls.append("release")
            if release_error is not None:
                raise release_error

    monkeypatch.setattr(retained, "_hold_existing_retained_descriptor_guard", guard)

    def native_call(label: str, values: list[object] | None, default: object) -> object:
        sequence = iter(values) if values is not None else None

        def wrapped(*_args: object) -> object:
            calls.append(label)
            assert active[0], "Native observation escaped retained guard"
            if label == throw_at and throw is not None:
                raise throw
            return next(sequence) if sequence is not None else default

        return wrapped

    owner = SimpleNamespace(uid="local-teacher")
    monkeypatch.setattr(ordered, "_owner", native_call("owner", owner_values, owner))
    namespace: tuple[frozenset[str], frozenset[str], bool] = (
        frozenset({TX + ".json"}),
        frozenset(),
        False,
    )
    monkeypatch.setattr(
        recovery, "_namespace", native_call("namespace", namespaces, namespace)
    )
    monkeypatch.setattr(
        operation,
        "_same_native_namespace",
        native_call("census", cast(list[object] | None, namespace_results), True),
    )
    image = (
        JOURNAL,
        REGISTRY_AFTER,
        DESCRIPTOR_BEFORE if kind is Kind.STAGE_TO_REGISTRY else DESCRIPTOR_AFTER,
        None,
    )
    monkeypatch.setattr(exact, "_images", native_call("images", images, image))


def _review(
    root: Path,
    kind: Kind = Kind.STAGE_TO_REGISTRY,
    revision: int | None = None,
    proposed: intents.PrivateTransactionIntent = INTENT,
) -> native.PrivateNativeRecoveryPostimageReview:
    selected = 7 if kind is Kind.STAGE_TO_REGISTRY else 8
    return native.review_native_private_recovery_postimage(
        kind, selected if revision is None else revision, proposed, root, root
    )


@pytest.mark.parametrize("kind", KINDS)
def test_matching_postimage_requires_one_retained_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, kind=kind)
    actual = _review(tmp_path, kind)
    assert actual.state is State.STABLE_POSTIMAGE_REVIEW_REQUIRED
    assert calls.count("acquire") == calls.count("release") == 1
    assert calls.count("images") == 2
    assert calls.count("census") == 5
    assert calls[0] == "acquire" and calls[-1] == "release"
    assert "not proved" in actual.message
    assert "registry-revision" not in repr(actual)
    assert not hasattr(actual, "permit")
    assert not hasattr(actual, "path")
    assert not hasattr(actual, "handles")
    with pytest.raises(FrozenInstanceError):
        actual.state = State.IO_ERROR  # type: ignore[misc]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("index", range(4))
def test_all_postimage_fields_are_exact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind, index: int
) -> None:
    valid: list[bytes | None] = [
        JOURNAL,
        REGISTRY_AFTER,
        DESCRIPTOR_BEFORE if kind is Kind.STAGE_TO_REGISTRY else DESCRIPTOR_AFTER,
        None,
    ]
    valid[index] = b"foreign"
    calls: list[str] = []
    _setup(monkeypatch, calls, kind=kind, images=[tuple(valid)] * 2)
    actual = _review(tmp_path, kind)
    assert actual.state is State.POSTIMAGE_CONFLICT_PRESERVE
    assert calls.count("release") == 1


@pytest.mark.parametrize("kind", KINDS)
def test_native_bytes_drift_is_preserved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind
) -> None:
    original = (
        JOURNAL,
        REGISTRY_AFTER,
        DESCRIPTOR_BEFORE if kind is Kind.STAGE_TO_REGISTRY else DESCRIPTOR_AFTER,
        None,
    )
    changed = (b"different", *original[1:])
    _setup(monkeypatch, [], kind=kind, images=[original, changed])
    assert _review(tmp_path, kind).state is State.IMAGE_DRIFT_PRESERVE


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(
    "bad",
    [
        None,
        tuple(),
        (b"bad",),
        (JOURNAL, REGISTRY_AFTER, DESCRIPTOR_BEFORE, b"unexpected-stage"),
    ],
)
def test_missing_or_malformed_native_image_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind, bad: object
) -> None:
    _setup(monkeypatch, [], kind=kind, images=[bad])
    assert _review(tmp_path, kind).state is State.POSTIMAGE_CONFLICT_PRESERVE


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("wrong", [0, -1, True, 2.5, "7", 6, 9])
def test_wrong_revision_refused_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind, wrong: object
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, kind=kind)
    value = _review(tmp_path, kind, cast(int, wrong))
    assert value.state in {State.REVISION_MISMATCH_REFUSED, State.INVALID_REQUEST}
    assert calls == []


@pytest.mark.parametrize("kind", KINDS)
def test_stage_present_is_not_postcondition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind
) -> None:
    calls: list[str] = []
    namespace = (
        frozenset({TX + ".json"}),
        frozenset({"." + TX + ".registry-stage"}),
        True,
    )
    _setup(monkeypatch, calls, kind=kind, namespaces=[namespace])
    assert _review(tmp_path, kind).state is State.STAGE_PRESENT_PRESERVE
    assert calls.count("release") == 1
    assert "images" not in calls


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("index", range(5))
def test_native_census_drift_is_preserved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind, index: int
) -> None:
    results = [True] * 5
    results[index] = False
    _setup(monkeypatch, [], kind=kind, namespace_results=results)
    assert _review(tmp_path, kind).state is State.NAMESPACE_CHANGED_PRESERVE


@pytest.mark.parametrize("kind", KINDS)
def test_owner_changes_during_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind
) -> None:
    owner = SimpleNamespace(uid="original")
    _setup(
        monkeypatch, [], kind=kind, owner_values=[owner, SimpleNamespace(uid="other")]
    )
    assert _review(tmp_path, kind).state is State.OWNER_CHANGED


@pytest.mark.parametrize("kind", KINDS)
def test_no_progress_requires_preserving_journal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind
) -> None:
    unchanged = (JOURNAL, REGISTRY_AFTER, DESCRIPTOR_BEFORE, None)
    _setup(monkeypatch, [], kind=kind, images=[unchanged] * 2)
    state = _review(tmp_path, kind).state
    if kind is Kind.DESCRIPTOR_AFTER_IMAGE:
        assert state is State.NO_PROGRESS_PRESERVE
    else:
        assert state is State.STABLE_POSTIMAGE_REVIEW_REQUIRED


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("when", ["owner", "namespace", "census", "images"])
def test_keyboard_interrupt_never_reports_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind, when: str
) -> None:
    _setup(monkeypatch, [], kind=kind, throw=KeyboardInterrupt(), throw_at=when)
    assert _review(tmp_path, kind).state is State.INTERRUPTED_PRESERVE


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("when", ["owner", "namespace", "census", "images"])
def test_native_io_error_refuses_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind, when: str
) -> None:
    _setup(monkeypatch, [], kind=kind, throw=OSError("synthetic"), throw_at=when)
    assert _review(tmp_path, kind).state is State.IO_ERROR


@pytest.mark.parametrize("kind", KINDS)
def test_guard_release_failure_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind
) -> None:
    error = retained.RetainedDescriptorGuardError(
        retained.RetainedDescriptorGuardCode.OWNER_CHANGED
    )
    _setup(monkeypatch, [], kind=kind, release_error=error)
    assert _review(tmp_path, kind).state is State.OWNER_CHANGED


@pytest.mark.parametrize("kind", KINDS)
def test_invalid_intent_or_platform_fails_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, kind=kind)
    assert (
        _review(
            tmp_path, kind, proposed=cast(intents.PrivateTransactionIntent, None)
        ).state
        is State.INVALID_REQUEST
    )
    assert calls == []
    monkeypatch.setattr(sys, "platform", "darwin")
    assert _review(tmp_path, kind).state is State.UNSUPPORTED


@pytest.mark.parametrize("kind", KINDS)
def test_initialization_intent_refused_without_native_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, kind=kind)
    init = _intent()
    object.__setattr__(
        init.witness, "operation", witness.PrivateBindingOperation.INITIALIZE
    )
    monkeypatch.setattr(intents, "decode_private_transaction_intent", lambda *_: init)
    result = _review(tmp_path, kind, proposed=init)
    assert result.state is State.INITIALIZATION_REFUSED
    assert calls == []


def test_journal_retirement_requires_independent_native_absence_protocol(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    result = _review(tmp_path, Kind.JOURNAL_RETIREMENT, 8)
    assert result.state is State.RETIREMENT_UNQUALIFIED
    assert calls == []


def test_no_teacher_notes_capability_advertised() -> None:
    capabilities = get_teacher_experience_capabilities()
    assert "notes.records.v1" not in capabilities
    assert "notes.menu.v1" not in capabilities
    assert "notes.portability.v1" not in capabilities


@pytest.mark.parametrize(
    "wrong", [None, "stage_to_registry", True, 7, b"stage_to_registry"]
)
def test_invalid_kind_is_refused_without_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, wrong: object
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls)
    actual = _review(tmp_path, cast(Kind, wrong))
    assert actual.state is State.INVALID_REQUEST
    assert calls == []


@pytest.mark.parametrize("kind", KINDS)
def test_wrong_namespace_type_refused_without_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind
) -> None:
    _setup(monkeypatch, [], kind=kind, namespaces=[None])
    assert _review(tmp_path, kind).state is State.IO_ERROR


@pytest.mark.parametrize("kind", KINDS)
def test_encoded_intent_mismatch_refused_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, kind=kind)
    monkeypatch.setattr(intents, "decode_private_transaction_intent", lambda *_: None)
    assert _review(tmp_path, kind).state is State.INVALID_REQUEST
    assert calls == []


@pytest.mark.parametrize("kind", KINDS)
def test_canonical_revision_mismatch_refused_before_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind
) -> None:
    calls: list[str] = []
    _setup(monkeypatch, calls, kind=kind)
    monkeypatch.setattr(metadata, "encode_private_registry", lambda *_: b"wrong")
    assert _review(tmp_path, kind).state is State.INVALID_REQUEST
    assert calls == []


@pytest.mark.parametrize("kind", KINDS)
def test_non_owner_guard_failure_never_promotes_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind
) -> None:
    failure = retained.RetainedDescriptorGuardError(
        retained.RetainedDescriptorGuardCode.UNSUPPORTED
    )
    _setup(monkeypatch, [], kind=kind, release_error=failure)
    assert _review(tmp_path, kind).state is State.UNSUPPORTED


@pytest.mark.parametrize("kind", KINDS)
def test_namespace_missing_denies_native_postimage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind
) -> None:
    _setup(monkeypatch, [], kind=kind, throw=FileNotFoundError(), throw_at="namespace")
    assert _review(tmp_path, kind).state is State.NAMESPACE_CHANGED_PRESERVE


@pytest.mark.parametrize("kind", KINDS)
def test_permission_denial_is_never_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: Kind
) -> None:
    _setup(monkeypatch, [], kind=kind, throw=PermissionError(), throw_at="images")
    assert _review(tmp_path, kind).state is State.GUARD_REFUSED
