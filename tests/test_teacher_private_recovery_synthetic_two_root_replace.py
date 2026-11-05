"""Core #238 3G31: two-root native prepared replacement on disposable bytes."""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Iterator, cast

import pytest

from pds_core import _teacher_private_recovery_synthetic_native_writer as scratch
from pds_core import _teacher_private_recovery_synthetic_owned_scope as owned
from pds_core import _teacher_private_recovery_synthetic_two_root_replace as two
from pds_core import _teacher_private_recovery_synthetic_writer_admission as admission

State = two.PrivateTwoRootState
Fault = two.PrivateTwoRootFault
Step = admission.PrivateScratchWriterStep


def test_never_reread_byte_locked_by_native_scratch_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On Windows a second read of the locked byte raises PermissionError.

    Do not remove or weaken the lock to appease the failing test; the evidence
    census must use lockfile metadata and native identity instead.
    """
    original = two._exact
    seen = [0]

    def refuse_locked_byte(path: Path, expected: bytes) -> bool:
        if path.name == scratch._LOCK:
            raise PermissionError("Win32 byte-range lock denied read")
        seen[0] += 1
        return original(path, expected)

    monkeypatch.setattr(two, "_exact", refuse_locked_byte)
    assert (
        two.rehearse_synthetic_private_two_root_replace().state
        is State.SCRATCH_TWO_ROOT_REPLACEMENT_UNQUALIFIED
    )
    assert seen[0] >= 4


def test_lockfile_shape_requires_regular_single_link_one_byte(tmp_path: Path) -> None:
    lock = tmp_path / scratch._LOCK
    lock.write_bytes(b"0")
    assert two._locked_file_shape(lock)
    lock.write_bytes(b"00")
    assert not two._locked_file_shape(lock)
    lock.unlink()
    lock.mkdir()
    assert not two._locked_file_shape(lock)


def test_lock_metadata_conflict_stops_before_replace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = [0]

    def bad_shape(_path: Path) -> bool:
        return False

    def forbidden(*_args: object, **_kwargs: object) -> None:
        seen[0] += 1
        raise AssertionError("Must refuse before replacement")

    monkeypatch.setattr(two, "_locked_file_shape", bad_shape)
    monkeypatch.setattr(os, "replace", forbidden)
    assert (
        two.rehearse_synthetic_private_two_root_replace().state
        is State.PREIMAGE_REFUSED
    )
    assert seen == [0]


def test_real_scratch_two_root_replacement_is_non_authorizing() -> None:
    outcome = two.rehearse_synthetic_private_two_root_replace()
    assert outcome.state is State.SCRATCH_TWO_ROOT_REPLACEMENT_UNQUALIFIED
    assert "no production" in outcome.message.lower()
    assert not any(
        hasattr(outcome, name)
        for name in ("permit", "token", "path", "handle", "bytes", "owner")
    )


@pytest.mark.skipif(
    sys.platform != "win32", reason="real native Win32 directory handles"
)
def test_real_win32_four_handle_replacement() -> None:
    assert (
        two.rehearse_synthetic_private_two_root_replace().state
        is State.SCRATCH_TWO_ROOT_REPLACEMENT_UNQUALIFIED
    )


@pytest.mark.parametrize("fault", [item for item in Fault if item is not Fault.NONE])
def test_all_interruption_boundaries_preserve(fault: Fault) -> None:
    result = two.rehearse_synthetic_private_two_root_replace(interruption=fault)
    assert result.state is State.INTERRUPTED_PRESERVE


@pytest.mark.parametrize(
    "step", [item for item in Step if item is not Step.STAGE_TO_REGISTRY]
)
def test_unsupported_operations_do_not_access_filesystem(
    monkeypatch: pytest.MonkeyPatch, step: Step
) -> None:
    monkeypatch.setattr(
        tempfile,
        "TemporaryDirectory",
        lambda **_kw: pytest.fail("non-admitted operation attempted scratch"),
    )
    assert (
        two.rehearse_synthetic_private_two_root_replace(step).state
        is State.OPERATION_NOT_ADMITTED
    )


@pytest.mark.parametrize("bad", [None, True, 0, "stage_to_registry", (), object()])
def test_invalid_step_refused_before_scratch(
    monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    monkeypatch.setattr(
        tempfile,
        "TemporaryDirectory",
        lambda **_kw: pytest.fail("invalid step attempted scratch"),
    )
    assert (
        two.rehearse_synthetic_private_two_root_replace(cast(Step, bad)).state
        is State.INVALID_REQUEST
    )


@pytest.mark.parametrize("bad", [None, True, 0, "none", (), object()])
def test_invalid_interruption_refused_before_scratch(
    monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    monkeypatch.setattr(
        tempfile,
        "TemporaryDirectory",
        lambda **_kw: pytest.fail("invalid fault attempted scratch"),
    )
    assert (
        two.rehearse_synthetic_private_two_root_replace(
            interruption=cast(Fault, bad)
        ).state
        is State.INVALID_REQUEST
    )


def test_unsupported_platform_never_enters_scratch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "unsupported")
    monkeypatch.setattr(
        tempfile,
        "TemporaryDirectory",
        lambda **_kw: pytest.fail("unsupported platform created files"),
    )
    assert two.rehearse_synthetic_private_two_root_replace().state is State.UNSUPPORTED


@pytest.mark.parametrize(
    "name", [scratch._REGISTRY, scratch._STAGE, two._TX, two._ASSOC]
)
def test_invalid_initial_image_preserves_before_replacement(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    original = scratch._write_new
    calls = [0]

    def altered(root: Path, filename: str, value: bytes) -> None:
        original(root, filename, value + (b"CORRUPT" if filename == name else b""))

    def blocked(*_args: object, **_kwargs: object) -> None:
        calls[0] += 1
        raise AssertionError("replace should not happen")

    monkeypatch.setattr(scratch, "_write_new", altered)
    monkeypatch.setattr(os, "replace", blocked)
    assert (
        two.rehearse_synthetic_private_two_root_replace().state
        is State.PREIMAGE_REFUSED
    )
    assert calls == [0]


@pytest.mark.parametrize(
    "directory", ["private", "transactions", "workspace", "association_dir"]
)
def test_extra_namespace_entry_refused(
    monkeypatch: pytest.MonkeyPatch, directory: str
) -> None:
    original = two._make_layout

    def bad(base: Path) -> two._Paths:
        paths = original(base)
        (getattr(paths, directory) / "unreviewed-artifact").write_bytes(b"foreign")
        return paths

    monkeypatch.setattr(two, "_make_layout", bad)
    assert (
        two.rehearse_synthetic_private_two_root_replace().state
        is State.NAMESPACE_CONFLICT_PRESERVE
    )


@pytest.mark.parametrize("index", range(4))
def test_any_retained_parent_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch, index: int
) -> None:
    original = owned._held_native_parent
    calls = [0]

    @contextmanager
    def guard(path: Path) -> Iterator[object]:
        current = calls[0]
        calls[0] += 1
        with original(path) as checker:
            if current == index:
                yield lambda: False
            else:
                yield checker

    monkeypatch.setattr(owned, "_held_native_parent", guard)
    assert (
        two.rehearse_synthetic_private_two_root_replace().state
        is State.PARENT_IDENTITY_CONFLICT_PRESERVE
    )
    assert calls == [4]


@pytest.mark.parametrize("at", [1, 2, 3, 4, 5])
def test_precheck_drift_before_native_replace_refused(
    monkeypatch: pytest.MonkeyPatch, at: int
) -> None:
    original = two._precheck
    count = [0]

    def changed(
        paths: two._Paths, evidence: two._Evidence, checks: tuple[object, ...]
    ) -> bool:
        count[0] += 1
        return False if count[0] == at else original(paths, evidence, checks)

    monkeypatch.setattr(two, "_precheck", changed)
    state = two.rehearse_synthetic_private_two_root_replace().state
    assert state is (
        State.PREIMAGE_REFUSED if at == 1 else State.ADMISSION_DRIFT_PRESERVE
    )
    assert count[0] == at


def test_native_reader_closed_before_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    real_reader = two._reader
    actual = os.replace
    opened = [False]
    closed = [False]

    @contextmanager
    def tracked(path: Path, fid: two._FileID) -> Iterator[None]:
        assert not opened[0]
        opened[0] = True
        try:
            with real_reader(path, fid):
                yield
        finally:
            opened[0] = False
            closed[0] = True

    def replacement(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        assert not opened[0] and closed[0]
        actual(source, target)

    monkeypatch.setattr(two, "_reader", tracked)
    monkeypatch.setattr(os, "replace", replacement)
    assert (
        two.rehearse_synthetic_private_two_root_replace().state
        is State.SCRATCH_TWO_ROOT_REPLACEMENT_UNQUALIFIED
    )
    assert closed == [True]


def test_reader_identity_conflict_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def failed(_path: Path, _fid: two._FileID) -> Iterator[None]:
        raise two._ReaderConflict
        yield  # pragma: no cover

    monkeypatch.setattr(two, "_reader", failed)
    assert (
        two.rehearse_synthetic_private_two_root_replace().state
        is State.READER_CONFLICT_PRESERVE
    )


@pytest.mark.parametrize(
    "error",
    [PermissionError("synthetic share refusal"), OSError("synthetic unexpected error")],
)
def test_replace_error_is_never_success(
    monkeypatch: pytest.MonkeyPatch, error: OSError
) -> None:
    monkeypatch.setattr(os, "replace", lambda *_args: (_ for _ in ()).throw(error))
    expected = (
        State.REPLACEMENT_REFUSED_PRESERVE
        if isinstance(error, PermissionError)
        else State.IO_ERROR
    )
    assert two.rehearse_synthetic_private_two_root_replace().state is expected


@pytest.mark.parametrize("item", [scratch._REGISTRY, two._TX, two._ASSOC])
def test_tampering_after_replace_detected(
    monkeypatch: pytest.MonkeyPatch, item: str
) -> None:
    original = os.replace

    def tampered(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        original(source, target)
        private = Path(target).parent
        directory = (
            private / "transactions"
            if item == two._TX
            else private.parent / "workspace" / ".pds"
            if item == two._ASSOC
            else private
        )
        (directory / item).write_bytes(b"TAMPER")

    monkeypatch.setattr(os, "replace", tampered)
    assert (
        two.rehearse_synthetic_private_two_root_replace().state
        is State.POSTIMAGE_CONFLICT_PRESERVE
    )


def test_postreplacement_native_identity_conflict_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = two._evidence

    def wrong(paths: two._Paths, *, stage: bool) -> two._Evidence:
        observed = original(paths, stage=stage)
        if not stage:
            return replace(
                observed,
                registry_id=(observed.registry_id[0], observed.registry_id[1] + 100),
            )
        return observed

    monkeypatch.setattr(two, "_evidence", wrong)
    assert (
        two.rehearse_synthetic_private_two_root_replace().state
        is State.FILE_IDENTITY_CONFLICT_PRESERVE
    )


def test_parent_mismatch_after_mutation_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = two._still_held
    calls = [0]

    def drift(checks: tuple[object, ...]) -> bool:
        calls[0] += 1
        if calls[0] >= 7:
            return False
        return original(checks)

    monkeypatch.setattr(two, "_still_held", drift)
    assert (
        two.rehearse_synthetic_private_two_root_replace().state
        is State.PARENT_IDENTITY_CONFLICT_PRESERVE
    )


def test_guard_refusal_does_not_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def refused(_path: Path) -> Iterator[None]:
        raise scratch._GuardRefused
        yield  # pragma: no cover

    monkeypatch.setattr(scratch, "_scratch_lock", refused)
    assert (
        two.rehearse_synthetic_private_two_root_replace().state is State.GUARD_REFUSED
    )


def test_file_sync_failure_is_not_durable_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scratch,
        "_sync_target",
        lambda *_args: (_ for _ in ()).throw(OSError("fsync error")),
    )
    assert two.rehearse_synthetic_private_two_root_replace().state is State.IO_ERROR


def test_scratch_paths_are_disjoint_and_cleaned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = two._make_layout
    seen: list[Path] = []

    def capture(base: Path) -> two._Paths:
        result = original(base)
        assert result.private != result.workspace
        assert result.transactions.parent == result.private
        assert result.association_dir.parent == result.workspace
        assert len(set(two._parents(result))) == 4
        seen.append(base)
        return result

    monkeypatch.setattr(two, "_make_layout", capture)
    assert (
        two.rehearse_synthetic_private_two_root_replace().state
        is State.SCRATCH_TWO_ROOT_REPLACEMENT_UNQUALIFIED
    )
    assert len(seen) == 1 and not seen[0].exists()


def test_postimage_checks_twice_and_preserves_journal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = two._postcheck
    calls = [0]

    def checked(
        paths: two._Paths, before: two._Evidence, checks: tuple[object, ...]
    ) -> None:
        calls[0] += 1
        assert (paths.transactions / two._TX).read_bytes() == scratch._JOURNAL
        original(paths, before, checks)

    monkeypatch.setattr(two, "_postcheck", checked)
    assert (
        two.rehearse_synthetic_private_two_root_replace().state
        is State.SCRATCH_TWO_ROOT_REPLACEMENT_UNQUALIFIED
    )
    assert calls == [2]


@pytest.mark.parametrize("state", list(State))
def test_all_states_are_sanitized_and_immutable(state: State) -> None:
    result = two._result(state)
    assert (
        result.message
        and "C:\\" not in result.message
        and "/tmp/" not in result.message
    )
    assert not any(
        hasattr(result, name)
        for name in ("path", "permit", "writer", "handle", "token", "bytes")
    )
    with pytest.raises(FrozenInstanceError):
        setattr(result, "state", State.INVALID_REQUEST)


def test_public_entry_has_no_path_or_callback_arguments() -> None:
    assert set(
        inspect.signature(two.rehearse_synthetic_private_two_root_replace).parameters
    ) == {"step", "interruption"}
    assert not hasattr(two, "commit_protected_registry")
