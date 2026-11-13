"""3G61: cooperative recovery locking cannot prevent uncooperative same-owner writes.

Only nonce-marked synthetic scratch files are mutated. This explicitly shows
why native identity, exact byte images and fail-closed recovery are necessary.
A lock grants neither OS-private protection nor transaction replay authority.
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

_PHASES = (
    drill.PrivateScratchDualStageFault.AFTER_PREPARED,
    drill.PrivateScratchDualStageFault.AFTER_REGISTRY_REPLACE,
    drill.PrivateScratchDualStageFault.AFTER_DESCRIPTOR_REPLACE,
    drill.PrivateScratchDualStageFault.AFTER_DESCRIPTOR_FLUSH,
)
_MODES = ("journal", "registry", "descriptor", "namespace")
_FIRST = Path(__file__).with_name("_core238_3g59_parent_kill_worker.py")
_RECOVERY = Path(__file__).with_name("_core238_3g60_recovery_worker.py")
_MUTATOR = Path(__file__).with_name("_core238_3g61_uncooperative_mutator.py")
_RESERVATION = ".core238-3g59-synthetic-only"
_FIRST_READY = ".core238-3g59-held-boundary"
_RECOVERY_READY = ".core238-3g60-recovery-held"


@pytest.fixture(scope="module")
def native_scratch_available() -> None:
    if sys.platform not in {"win32", "linux"}:
        pytest.skip("Native scratch recovery tests unavailable")
    result = drill.rehearse_canonical_dual_stage_one_shot()
    if result.state in {
        drill.PrivateScratchDualStageState.PARENT_NATIVE_CUSTODY_REFUSED,
        drill.PrivateScratchDualStageState.STAGE_NATIVE_CUSTODY_REFUSED,
        drill.PrivateScratchDualStageState.PREPARATION_FLUSH_REFUSED_HOLD,
    }:
        pytest.skip("Native disposable stage custody unavailable")
    assert (
        result.state
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


def _run(worker: Path, root: Path, token: str, mode: str) -> tuple[int, bytes, bytes]:
    process = _spawn(worker, root, token, mode)
    try:
        out, error = process.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=15)
        raise
    assert process.returncode is not None
    return process.returncode, out, error


def _ready(process: subprocess.Popen[bytes], marker: Path, expected: bytes) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        assert process.poll() is None, "Synthetic native-lock holder exited prematurely"
        if marker.is_file() and not marker.is_symlink():
            try:
                if marker.read_bytes() == expected:
                    return
            except OSError:
                pass
        time.sleep(0.03)
    raise AssertionError("Disposable native lock handshake not observed")


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.kill()
    out, error = process.communicate(timeout=15)
    assert process.returncode not in (None, 0)
    assert out == b"" and error == b""


def _snapshot(root: Path) -> tuple[tuple[str, bytes], ...]:
    private = root / "private"
    association = root / "workspace" / ".pds"
    candidates = (
        *canonical._paths(private, association),
        private / ".core238-3g61-unexpected-registry-stage",
    )
    return tuple(
        (str(path.relative_to(root)), path.read_bytes())
        for path in candidates
        if path.is_file()
    )


@pytest.mark.parametrize("phase", _PHASES)
@pytest.mark.parametrize("mutation", _MODES)
def test_uncooperative_mutation_forces_conflict_after_killed_recovery_holder(
    native_scratch_available: None,
    phase: drill.PrivateScratchDualStageFault,
    mutation: str,
) -> None:
    token = secrets.token_hex(16)
    with _scratch(token) as root:
        original = _spawn(_FIRST, root, token, phase.value)
        try:
            _ready(
                original,
                root / _FIRST_READY,
                b"core238-3g59-held:"
                + token.encode("ascii")
                + b":"
                + phase.value.encode("ascii"),
            )
            _terminate(original)
        finally:
            if original.poll() is None:
                _terminate(original)

        private = root / "private"
        association = root / "workspace" / ".pds"
        before = canonical._checkpoint(
            private, association, canonical._canonical_fork_intent()
        )
        assert (
            before is not canonical.PrivateCanonicalRestartCheckpoint.CONFLICT_PRESERVE
        )
        holder = _spawn(_RECOVERY, root, token, "hold")
        try:
            _ready(
                holder,
                root / _RECOVERY_READY,
                b"core238-3g60-recovery-held:"
                + token.encode("ascii")
                + b":"
                + before.value.encode("ascii"),
            )
            # A cooperative competitor is refused, but a separate same-user
            # process that ignores the lock can alter disposable file content.
            code, output, errors = _run(_RECOVERY, root, token, "probe")
            assert code == 3 and output == b"" and errors == b""
            code, output, errors = _run(_MUTATOR, root, token, mutation)
            assert code == 0 and output == b"" and errors == b""
            code, output, errors = _run(_RECOVERY, root, token, "probe")
            assert code == 3 and output == b"" and errors == b""
            frozen = _snapshot(root)
            _terminate(holder)
        finally:
            if holder.poll() is None:
                _terminate(holder)
        code, output, errors = _run(_RECOVERY, root, token, "inspect")
        assert code == 0
        assert output == b"conflict_preserve\n" and errors == b""
        assert _snapshot(root) == frozen
        assert canonical._paths(private, association)[4].is_file()


@pytest.mark.parametrize(
    ("bad_token", "mode"),
    (("x" * 32, "journal"), ("0" * 31, "registry"), ("f" * 32, "unrecognized")),
)
def test_disposable_mutator_rejects_invalid_reservation_or_mode(
    bad_token: str, mode: str
) -> None:
    token = secrets.token_hex(16)
    with _scratch(token) as root:
        initial = tuple(path.name for path in root.iterdir())
        result, output, error = _run(_MUTATOR, root, bad_token, mode)
        assert result == 2 and output == b"" and error == b""
        assert tuple(path.name for path in root.iterdir()) == initial


def test_disposable_mutator_has_no_production_authority() -> None:
    source = _MUTATOR.read_text(encoding="utf-8")
    assert "pds_core/teacher_private_storage.py" not in source
    assert "_held_existing_restart_lock(" not in source
    assert "os.replace(" not in source
