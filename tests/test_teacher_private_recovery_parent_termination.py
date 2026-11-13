"""Core #238 3G59: forced parent kill, conflicting reader, fresh native restart.

All writing is confined to nonce-marked disposable scratch; no live teacher
workspace, private data or Notes is accessed. A process kill is not power loss.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from pds_core import _teacher_private_recovery_canonical_journaled_restart as canonical
from pds_core import (
    _teacher_private_recovery_canonical_native_parent_restart as parents,
)
from pds_core import _teacher_private_recovery_durable_scratch_sequence as durable
from pds_core import _teacher_private_recovery_journaled_restart_drill as restart
from pds_core import _teacher_private_recovery_scratch_dual_stage_attempt as drill
from pds_core import _teacher_private_transaction_intent as intents

_F = drill.PrivateScratchDualStageFault
_CP = canonical.PrivateCanonicalRestartCheckpoint
_WORKER = Path(__file__).with_name("_core238_3g59_parent_kill_worker.py")
_MARKER = ".core238-3g59-synthetic-only"
_READY = ".core238-3g59-held-boundary"
_PHASES = (
    (_F.AFTER_PREPARED, _CP.PREPARED_HOLD),
    (_F.AFTER_REGISTRY_REPLACE, _CP.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD),
    (_F.AFTER_DESCRIPTOR_REPLACE, _CP.BOTH_AFTER_JOURNAL_PENDING_HOLD),
    (_F.AFTER_DESCRIPTOR_FLUSH, _CP.BOTH_AFTER_JOURNAL_PENDING_HOLD),
)


@pytest.fixture(scope="module")
def native_scratch_available() -> None:
    if sys.platform not in {"win32", "linux"}:
        pytest.skip("Native scratch execution unavailable")
    result = drill.rehearse_canonical_dual_stage_one_shot()
    if result.state in {
        drill.PrivateScratchDualStageState.PARENT_NATIVE_CUSTODY_REFUSED,
        drill.PrivateScratchDualStageState.STAGE_NATIVE_CUSTODY_REFUSED,
        drill.PrivateScratchDualStageState.PREPARATION_FLUSH_REFUSED_HOLD,
    }:
        pytest.skip("Native scratch custody/flush is unavailable")
    assert (
        result.state
        is drill.PrivateScratchDualStageState.SCRATCH_BOTH_STAGE_IDENTITIES_REOBSERVED_UNQUALIFIED
    )


def _run_worker(root: Path, token: str, phase: str) -> subprocess.Popen[bytes]:
    repository = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository)
    return subprocess.Popen(
        [sys.executable, str(_WORKER), str(root), token, phase],
        cwd=repository,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _await_held(
    process: subprocess.Popen[bytes], root: Path, token: str, phase: str
) -> None:
    expected = (
        b"core238-3g59-held:" + token.encode("ascii") + b":" + phase.encode("ascii")
    )
    ready = root / _READY
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(
                "Synthetic worker exited before retained-lock handshake"
            )
        if ready.is_file() and not ready.is_symlink():
            try:
                if ready.read_bytes() == expected:
                    return
            except (OSError, PermissionError):
                pass
        time.sleep(0.03)
    raise AssertionError("Synthetic worker did not retain the expected lock boundary")


def _terminate(process: subprocess.Popen[bytes]) -> tuple[bytes, bytes]:
    if process.poll() is None:
        process.kill()  # Windows TerminateProcess; POSIX SIGKILL.
    output, errors = process.communicate(timeout=15)
    assert process.returncode not in (None, 0, 4)
    assert output == b"" and errors == b""
    return output, errors


@contextmanager
def _scratch(token: str) -> Iterator[Path]:
    # Used only in a test-managed, nonce-marked direct child of the system temp.
    with tempfile.TemporaryDirectory(prefix="core238_3g59_parent_kill_") as directory:
        root = Path(directory)
        (root / _MARKER).write_bytes(b"core238-3g59:" + token.encode("ascii"))
        yield root


def _images(names: tuple[Path, ...]) -> tuple[bytes | None, ...]:
    return tuple(path.read_bytes() if path.is_file() else None for path in names)


def _fresh_checkpoint(root: Path) -> canonical.PrivateCanonicalRestartCheckpoint:
    checked = canonical._canonical_fork_intent()
    private = root / "private"
    association = root / "workspace" / ".pds"
    with restart._held_existing_restart_lock(private / ".native-lock"):
        with parents._hold_four_parents(
            parents._parent_roots(private, association)
        ) as retained:
            parents._require_held(retained)
            found = canonical._checkpoint(private, association, checked)
            parents._require_held(retained)
    return found


@pytest.mark.parametrize(("phase", "expected"), _PHASES)
def test_parent_kill_releases_contended_lock_and_preserves_pending_checkpoint(
    native_scratch_available: None,
    phase: drill.PrivateScratchDualStageFault,
    expected: canonical.PrivateCanonicalRestartCheckpoint,
) -> None:
    token = secrets.token_hex(16)
    with _scratch(token) as root:
        process = _run_worker(root, token, phase.value)
        try:
            _await_held(process, root, token, phase.value)
            private = root / "private"
            association = root / "workspace" / ".pds"
            checked = canonical._canonical_fork_intent()
            names = canonical._paths(private, association)
            journal = names[4]
            original = _images(names)
            assert durable._exact(
                journal, intents.encode_private_transaction_intent(checked)
            )
            # A separate prospective recovery process cannot enter while the
            # original worker actually holds its nonblocking OS lock.
            with pytest.raises(restart._RestartGuardRefused):
                with restart._held_existing_restart_lock(private / ".native-lock"):
                    pytest.fail("Contended restart guard unexpectedly admitted")
            assert _images(names) == original
            _terminate(process)
            assert _fresh_checkpoint(root) is expected
            assert _images(names) == original
            assert journal.is_file()
            assert durable._exact(
                journal, intents.encode_private_transaction_intent(checked)
            )
        finally:
            if process.poll() is None:
                _terminate(process)


@pytest.mark.parametrize("phase", (_F.AFTER_PREPARED, _F.AFTER_REGISTRY_REPLACE))
def test_corrupted_pending_journal_after_parent_kill_fails_closed(
    native_scratch_available: None,
    phase: drill.PrivateScratchDualStageFault,
) -> None:
    token = secrets.token_hex(16)
    with _scratch(token) as root:
        process = _run_worker(root, token, phase.value)
        try:
            _await_held(process, root, token, phase.value)
            _terminate(process)
            private = root / "private"
            association = root / "workspace" / ".pds"
            journal = canonical._paths(private, association)[4]
            journal.write_bytes(b"corrupt-pending-intent")  # Disposable fixture ONLY.
            before = _images(canonical._paths(private, association))
            assert _fresh_checkpoint(root) is _CP.CONFLICT_PRESERVE
            assert _images(canonical._paths(private, association)) == before
            assert journal.read_bytes() == b"corrupt-pending-intent"
        finally:
            if process.poll() is None:
                _terminate(process)


@pytest.mark.parametrize("invalid", ("badtoken", "X" * 32, "0" * 32))
def test_worker_rejects_invalid_reservation_without_mutating(invalid: str) -> None:
    token = secrets.token_hex(16)
    with _scratch(token) as root:
        process = _run_worker(root, invalid, _F.AFTER_PREPARED.value)
        output, errors = process.communicate(timeout=15)
        assert process.returncode == 2
        assert output == b"" and errors == b""
        assert not (root / "private").exists()
        assert not (root / _READY).exists()


def test_worker_rejects_unsupported_boundary() -> None:
    token = secrets.token_hex(16)
    with _scratch(token) as root:
        process = _run_worker(root, token, "AFTER_COMPLETION")
        output, errors = process.communicate(timeout=15)
        assert process.returncode == 2
        assert output == b"" and errors == b""
        assert not (root / "private").exists()


def test_parent_kill_worker_has_no_production_entrypoint() -> None:
    assert _WORKER.is_file()
    assert _WORKER.parent.name == "tests"
    assert not hasattr(drill, "_parent_kill_production_writer")
