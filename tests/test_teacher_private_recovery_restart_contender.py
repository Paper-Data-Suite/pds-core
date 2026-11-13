"""Core #238 3G60: crash a recovery holder, fence contenders, inspect afresh.

Every path belongs to a nonce-marked disposable Core test. Process death does
not prove cross-device ordering, power-loss durability or replay authority.
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
from pds_core import _teacher_private_recovery_scratch_dual_stage_attempt as drill

_PHASE = drill.PrivateScratchDualStageFault
_CHECKPOINT = canonical.PrivateCanonicalRestartCheckpoint
_RESERVATION = ".core238-3g59-synthetic-only"
_FIRST_READY = ".core238-3g59-held-boundary"
_SECOND_READY = ".core238-3g60-recovery-held"
_FIRST = Path(__file__).with_name("_core238_3g59_parent_kill_worker.py")
_SECOND = Path(__file__).with_name("_core238_3g60_recovery_worker.py")
_PHASES = (
    (_PHASE.AFTER_PREPARED, _CHECKPOINT.PREPARED_HOLD),
    (_PHASE.AFTER_REGISTRY_REPLACE, _CHECKPOINT.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD),
    (_PHASE.AFTER_DESCRIPTOR_REPLACE, _CHECKPOINT.BOTH_AFTER_JOURNAL_PENDING_HOLD),
    (_PHASE.AFTER_DESCRIPTOR_FLUSH, _CHECKPOINT.BOTH_AFTER_JOURNAL_PENDING_HOLD),
)


@pytest.fixture(scope="module")
def native_scratch_available() -> None:
    if sys.platform not in {"win32", "linux"}:
        pytest.skip("Native disposable checkpoint testing unavailable")
    outcome = drill.rehearse_canonical_dual_stage_one_shot()
    if outcome.state in {
        drill.PrivateScratchDualStageState.PARENT_NATIVE_CUSTODY_REFUSED,
        drill.PrivateScratchDualStageState.STAGE_NATIVE_CUSTODY_REFUSED,
        drill.PrivateScratchDualStageState.PREPARATION_FLUSH_REFUSED_HOLD,
    }:
        pytest.skip("Native scratch custody or directory flush unavailable")
    assert (
        outcome.state
        is drill.PrivateScratchDualStageState.SCRATCH_BOTH_STAGE_IDENTITIES_REOBSERVED_UNQUALIFIED
    )


@contextmanager
def _scratch(token: str) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="core238_3g59_parent_kill_") as value:
        root = Path(value)
        (root / _RESERVATION).write_bytes(b"core238-3g59:" + token.encode("ascii"))
        yield root


def _spawn(worker: Path, root: Path, token: str, mode: str) -> subprocess.Popen[bytes]:
    repository = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository)
    return subprocess.Popen(
        [sys.executable, str(worker), str(root), token, mode],
        cwd=repository,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _ready(process: subprocess.Popen[bytes], path: Path, expected: bytes) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        assert process.poll() is None, "Synthetic retained-lock worker exited early"
        if path.is_file() and not path.is_symlink():
            try:
                if path.read_bytes() == expected:
                    return
            except OSError:
                pass
        time.sleep(0.03)
    raise AssertionError("Synthetic retained-lock handshake was not observed")


def _kill(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.kill()
    output, errors = process.communicate(timeout=15)
    assert process.returncode not in (None, 0)
    assert output == b"" and errors == b""


def _run(worker: Path, root: Path, token: str, mode: str) -> tuple[int, bytes, bytes]:
    process = _spawn(worker, root, token, mode)
    output, errors = process.communicate(timeout=15)
    code = process.returncode
    assert code is not None
    return code, output, errors


def _images(root: Path) -> tuple[bytes | None, ...]:
    paths = canonical._paths(root / "private", root / "workspace" / ".pds")
    return tuple(path.read_bytes() if path.is_file() else None for path in paths)


def _prepared_after_parent_kill(
    root: Path, token: str, phase: drill.PrivateScratchDualStageFault
) -> None:
    process = _spawn(_FIRST, root, token, phase.value)
    try:
        expected = (
            b"core238-3g59-held:"
            + token.encode("ascii")
            + b":"
            + phase.value.encode("ascii")
        )
        _ready(process, root / _FIRST_READY, expected)
        _kill(process)
    finally:
        if process.poll() is None:
            _kill(process)


@pytest.mark.parametrize(("phase", "expected"), _PHASES)
def test_killed_recovery_holder_releases_fence_for_fresh_readers(
    native_scratch_available: None,
    phase: drill.PrivateScratchDualStageFault,
    expected: canonical.PrivateCanonicalRestartCheckpoint,
) -> None:
    token = secrets.token_hex(16)
    with _scratch(token) as root:
        _prepared_after_parent_kill(root, token, phase)
        original = _images(root)
        holder = _spawn(_SECOND, root, token, "hold")
        try:
            _ready(
                holder,
                root / _SECOND_READY,
                b"core238-3g60-recovery-held:"
                + token.encode("ascii")
                + b":"
                + expected.value.encode("ascii"),
            )
            # A third process must not enter a recovery scope while the new
            # reader still holds the native lock after the first crash.
            code, output, errors = _run(_SECOND, root, token, "probe")
            assert code == 3 and output == b"" and errors == b""
            assert _images(root) == original
            _kill(holder)
        finally:
            if holder.poll() is None:
                _kill(holder)
        code, output, errors = _run(_SECOND, root, token, "inspect")
        assert code == 0 and output == (expected.value + "\n").encode("ascii")
        assert errors == b""
        assert _images(root) == original
        # Pending journal survives: no replay or retirement took place.
        assert canonical._paths(root / "private", root / "workspace" / ".pds")[
            4
        ].is_file()


@pytest.mark.parametrize("bad", ("nothex", "f" * 31))
def test_recovery_worker_rejects_invalid_reservation_without_changes(bad: str) -> None:
    token = secrets.token_hex(16)
    with _scratch(token) as root:
        before = tuple(path.name for path in root.iterdir())
        code, output, errors = _run(_SECOND, root, bad, "inspect")
        assert code == 2 and output == b"" and errors == b""
        assert tuple(path.name for path in root.iterdir()) == before


def test_recovery_worker_rejects_unsupported_mode_without_changes() -> None:
    token = secrets.token_hex(16)
    with _scratch(token) as root:
        before = tuple(path.name for path in root.iterdir())
        code, output, errors = _run(_SECOND, root, token, "replay")
        assert code == 2 and output == b"" and errors == b""
        assert tuple(path.name for path in root.iterdir()) == before


def test_recovery_worker_has_no_production_replay_entrypoint() -> None:
    assert _SECOND.is_file()
    assert _SECOND.parent.name == "tests"
    assert not hasattr(drill, "resume_production_private_fork")
