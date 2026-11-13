"""Core #238 Slice 3G42: registry-stage native ID transition under retained guard."""

from __future__ import annotations

import inspect
import os
import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Callable, Iterator, cast

import pytest

from pds_core import _teacher_private_descriptor_snapshot as descriptor
from pds_core import _teacher_private_inspection as inspection
from pds_core import _teacher_private_lock_file_provision as lock_file
from pds_core import _teacher_private_ordered_coordination as ordered
from pds_core import _teacher_private_posix_provision as posix
from pds_core import _teacher_private_recovery_production_native_preflight as preflight
from pds_core import _teacher_private_recovery_production_write_barrier as barrier
from pds_core import _teacher_private_recovery_transition_guard as transition
from pds_core import _teacher_private_recovery_transition_registry_custody as native

State = native.PrivateRegistryTransitionIdentityState


def _key(n: int) -> native.NativeKey:
    return (17, n.to_bytes(16, "big"))


def _baseline() -> native._Identities:
    return native._Identities(_key(10), _key(20), _key(30))


def _entries(
    *,
    parent: native.NativeKey | None = None,
    old: native.NativeKey | None = None,
    staged: native.NativeKey | None = None,
    registry: native.NativeKey | None = None,
    stage: native.NativeKey | None = None,
    absent_stage: bool = False,
    absent_registry: bool = False,
) -> native._Entries:
    baseline = _baseline()
    return native._Entries(
        parent or baseline.parent,
        old or baseline.old,
        staged or baseline.staged,
        None if absent_registry else (registry or baseline.old),
        None if absent_stage else (stage or baseline.staged),
    )


def test_prepared_native_pair_remains_non_authorizing() -> None:
    assert (
        native._transition_state(_baseline(), _entries())
        is State.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
    )
    review = native._result(State.PREPARED_IDENTITIES_OBSERVED_NO_WRITE)
    assert review.pending_evidence_must_remain is True
    assert review.unqualified_requirements == barrier._REQUIRED
    assert "non_authorizing=True" in repr(review)
    with pytest.raises(FrozenInstanceError):
        setattr(review, "state", State.IO_ERROR)


def test_exact_stage_installation_is_not_durable_success() -> None:
    result = native._transition_state(
        _baseline(), _entries(registry=_key(30), absent_stage=True)
    )
    assert result is State.EXPECTED_STAGE_INSTALLED_RECOVERY_REQUIRED
    assert "durability" in native._result(result).message


@pytest.mark.parametrize(
    ("observed", "wanted"),
    [
        (_entries(parent=_key(40)), State.PARENT_CHANGED_PRESERVE),
        (_entries(old=_key(40)), State.OLD_HANDLE_CHANGED_PRESERVE),
        (_entries(staged=_key(40)), State.STAGE_HANDLE_CHANGED_PRESERVE),
        (_entries(absent_registry=True), State.REGISTRY_MISSING_PRESERVE),
        (_entries(absent_stage=True), State.STAGE_MISSING_BEFORE_PRESERVE),
        (_entries(registry=_key(40)), State.REGISTRY_FOREIGN_PRESERVE),
        (_entries(stage=_key(40)), State.STAGE_FOREIGN_PRESERVE),
        (_entries(registry=_key(30)), State.STAGE_FOREIGN_PRESERVE),
        (_entries(registry=_key(30), stage=_key(40)), State.STAGE_FOREIGN_PRESERVE),
    ],
)
def test_every_foreign_transition_has_specific_refusal(
    observed: native._Entries, wanted: State
) -> None:
    assert native._transition_state(_baseline(), observed) is wanted


@pytest.mark.parametrize(
    "ident", [b"", b"short", b"\x00" * 16, b"x" * 17, "not-bytes", None]
)
def test_bad_native_file_identifiers_refuse(ident: object) -> None:
    assert native._native_key(1, cast(bytes, ident)) is None


@pytest.mark.parametrize("volume", [None, True, -1, "17", 3.14])
def test_bad_volume_refuses(volume: object) -> None:
    assert native._native_key(cast(int, volume), b"x" * 16) is None


def test_aliases_refused() -> None:
    original = _baseline()
    for pair in (
        native._Identities(original.parent, original.old, original.old),
        native._Identities(original.old, original.old, original.staged),
        native._Identities(original.staged, original.old, original.staged),
    ):
        assert (
            native._transition_state(pair, _entries()) is State.IDENTITY_ALIAS_PRESERVE
        )


def test_invalid_evidence_refused() -> None:
    assert (
        native._transition_state(cast(native._Identities, object()), _entries())
        is State.INVALID_REQUEST
    )
    assert (
        native._transition_state(_baseline(), cast(native._Entries, object()))
        is State.INVALID_REQUEST
    )
    assert (
        native._transition_state(
            native._Identities((0, b"bad"), _key(20), _key(30)), _entries()
        )
        is State.INVALID_REQUEST
    )


def _setup(
    monkeypatch: pytest.MonkeyPatch, *, drift_at: int = 0, fail_release: bool = False
) -> list[str]:
    events: list[str] = []
    owner = inspection.EffectiveOSOwner("windows_token_sid", "FAKE")
    monkeypatch.setattr(lock_file, "_requested_root", lambda *_: True)
    monkeypatch.setattr(descriptor, "_valid_root", lambda *_: True)
    monkeypatch.setattr(preflight, "_native_observation", lambda *_: (None, owner))
    monkeypatch.setattr(ordered, "_owner", lambda: owner)

    @contextmanager
    def held_guard(*_args: object) -> Iterator[None]:
        events.append("guard-enter")
        try:
            yield
        finally:
            events.append("guard-exit")
            if fail_release:
                raise transition._WriterGuardRefused(
                    transition.PrivateTransitionGuardState.GUARD_REFUSED
                )

    @contextmanager
    def held_pair(*_args: object) -> Iterator[Callable[[], State]]:
        assert events[-1] == "guard-enter"
        events.append("pair-enter")
        count = 0

        def check() -> State:
            nonlocal count
            count += 1
            events.append("check")
            if count == drift_at:
                return State.REGISTRY_FOREIGN_PRESERVE
            return State.PREPARED_IDENTITIES_OBSERVED_NO_WRITE

        try:
            yield check
        finally:
            events.append("pair-exit")

    monkeypatch.setattr(
        transition, "_hold_transitionable_journal_descriptor_guard", held_guard
    )
    monkeypatch.setattr(native, "_held_registry_stage_pair", held_pair)
    return events


def _review(tmp_path: Path) -> native.PrivateRegistryTransitionIdentityReview:
    return native.review_native_registry_transition_identity_custody(
        tmp_path, tmp_path, "11111111-1111-4111-8111-111111111111", 15, 20
    )


def test_real_guard_scope_would_span_all_five_checks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events = _setup(monkeypatch)
    result = _review(tmp_path)
    assert result.state is State.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
    assert events == ["guard-enter", "pair-enter"] + ["check"] * 5 + [
        "pair-exit",
        "guard-exit",
    ]


@pytest.mark.parametrize("at", [1, 2, 3, 4, 5])
def test_drift_in_every_observation_is_preserved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at: int
) -> None:
    events = _setup(monkeypatch, drift_at=at)
    assert _review(tmp_path).state is State.REGISTRY_FOREIGN_PRESERVE
    assert events[-2:] == ["pair-exit", "guard-exit"]


def test_guard_release_failure_overrides_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events = _setup(monkeypatch, fail_release=True)
    assert _review(tmp_path).state is State.GUARD_REFUSED
    assert events[-1] == "guard-exit"


def test_owner_change_inside_scope_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events = _setup(monkeypatch)
    monkeypatch.setattr(ordered, "_owner", lambda: None)
    assert _review(tmp_path).state is State.OWNER_CHANGED
    assert events[-1] == "guard-exit"


def test_preflight_refusal_never_opens_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events = _setup(monkeypatch)
    monkeypatch.setattr(preflight, "_native_observation", lambda *_: (object(), None))
    assert _review(tmp_path).state is State.OWNER_OR_PROTECTION_REFUSED
    assert not events


@pytest.mark.parametrize("tx", ["bad", "../etc/passwd", "", "A" * 36, None, 14])
def test_invalid_tx_never_opens_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tx: object
) -> None:
    events = _setup(monkeypatch)
    result = native.review_native_registry_transition_identity_custody(
        tmp_path, tmp_path, cast(str, tx), 15, 20
    )
    assert result.state is State.INVALID_REQUEST
    assert not events


@pytest.mark.parametrize("size", [None, True, 0, -1, "15", 15.2])
def test_invalid_size_never_opens_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, size: object
) -> None:
    events = _setup(monkeypatch)
    assert (
        native.review_native_registry_transition_identity_custody(
            tmp_path,
            tmp_path,
            "11111111-1111-4111-8111-111111111111",
            cast(int, size),
            20,
        ).state
        is State.INVALID_REQUEST
    )
    assert not events


def test_no_production_mutation_or_authority_in_source() -> None:
    source = inspect.getsource(native)
    assert "os.replace(" not in source
    assert "os.remove(" not in source
    assert "unlink(" not in source
    assert "NamedTemporaryFile(" not in source
    assert "def commit_" not in source
    assert not hasattr(native, "activate_notes")
    assert "_hold_transitionable_journal_descriptor_guard" in source


@pytest.mark.skipif(
    sys.platform != "linux"
    or not hasattr(os, "geteuid")
    or getattr(os, "geteuid", lambda: 0)() == 0,
    reason="native Linux owner exercise requires unprivileged Linux",
)
def test_actual_posix_handles_remain_open_and_classify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid = getattr(os, "geteuid")()
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    (root / "registry.json").write_bytes(b"before")
    (root / ".11111111-1111-4111-8111-111111111111.registry-stage").write_bytes(
        b"after!"
    )
    for path in root.iterdir():
        path.chmod(0o600)
    monkeypatch.setattr(
        posix,
        "_open_verified_parent",
        lambda *_: (os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)), None),
    )
    monkeypatch.setattr(posix, "_acl_absent", lambda *_: None)
    monkeypatch.setattr(posix, "_is_known_local_filesystem", lambda *_: True)
    owner = inspection.EffectiveOSOwner("posix_euid", str(uid))
    with native._held_linux_pair(
        root, ".11111111-1111-4111-8111-111111111111.registry-stage", owner, 6, 6
    ) as check:
        assert check() is State.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
        assert check() is State.PREPARED_IDENTITIES_OBSERVED_NO_WRITE


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native handle exercise")
def test_real_windows_share_safe_handles_on_disposable_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Real Windows file IDs; ACL decisions mocked for disposable scratch only."""
    from pds_core import _teacher_private_windows_preflight as wincheck
    from pds_core import _teacher_private_windows_provision as wincreate
    from pds_core._teacher_private_native_preflight import NativePrivatePreflightState

    root = tmp_path / "private"
    root.mkdir()
    stage_name = ".11111111-1111-4111-8111-111111111111.registry-stage"
    (root / "registry.json").write_bytes(b"old")
    (root / stage_name).write_bytes(b"new!")
    granted = NativePrivatePreflightState.RESTRICTIVE_UNQUALIFIED
    monkeypatch.setattr(wincreate, "_known_fixed_local_volume", lambda *_: True)
    monkeypatch.setattr(wincheck, "_native_windows_walk", lambda *_: granted)
    monkeypatch.setattr(wincheck, "_handle_dacl_state", lambda *_: granted)
    owner = inspection.EffectiveOSOwner("windows_token_sid", "SYNTHETIC-ONLY")
    monkeypatch.setattr(ordered, "_owner", lambda: owner)
    with native._held_windows_pair(root, stage_name, owner, 3, 4) as check:
        assert check() is State.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
        assert check() is State.PREPARED_IDENTITIES_OBSERVED_NO_WRITE
