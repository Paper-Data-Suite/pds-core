"""Core #238 3G58: real hard child-process death, separate restart inspection.

All mutation is contained in a disposable, nonce-marked temporary directory.
The child uses the scratch-only 3G57 rehearsal, never a protected writer.
These tests do not simulate system power loss or establish durable commit.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from pds_core import _teacher_private_recovery_canonical_journaled_restart as canonical
from pds_core import (
    _teacher_private_recovery_canonical_native_parent_restart as parents,
)
from pds_core import _teacher_private_recovery_durable_scratch_sequence as durable
from pds_core import _teacher_private_recovery_journaled_restart_drill as restart
from pds_core import _teacher_private_recovery_scratch_dual_stage_attempt as drill
from pds_core import _teacher_private_transaction_intent as intents


F = drill.PrivateScratchDualStageFault
CP = canonical.PrivateCanonicalRestartCheckpoint
_CHILD = Path(__file__).with_name("_core238_3g58_child_worker.py")
_HARD_EXIT = 93
_MARKER = ".core238-3g58-synthetic-only"


@pytest.fixture(scope="module")
def native_disposable_scope() -> None:
    if sys.platform not in {"linux", "win32"}:
        pytest.skip("Native disposable scope unavailable")
    result = drill.rehearse_canonical_dual_stage_one_shot()
    if result.state in {
        drill.PrivateScratchDualStageState.PARENT_NATIVE_CUSTODY_REFUSED,
        drill.PrivateScratchDualStageState.STAGE_NATIVE_CUSTODY_REFUSED,
        drill.PrivateScratchDualStageState.PREPARATION_FLUSH_REFUSED_HOLD,
    }:
        pytest.skip("Native scratch locking, flush, or stage custody unavailable")
    assert (
        result.state
        is drill.PrivateScratchDualStageState.SCRATCH_BOTH_STAGE_IDENTITIES_REOBSERVED_UNQUALIFIED
    )
    assert result.journal_seen_at_restart


def _child(
    root: Path, token: str, boundary: str, *, timeout: int = 30
) -> subprocess.CompletedProcess[bytes]:
    repository = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository)
    return subprocess.run(
        [sys.executable, str(_CHILD), str(root), token, boundary],
        cwd=repository,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def _images(paths: tuple[Path, ...]) -> tuple[bytes | None, ...]:
    observed: list[bytes | None] = []
    for path in paths:
        observed.append(path.read_bytes() if path.is_file() else None)
    return tuple(observed)


@pytest.mark.parametrize(
    ("boundary", "expected"),
    [
        (F.AFTER_PREPARED, CP.PREPARED_HOLD),
        (F.AFTER_REGISTRY_MARK, CP.PREPARED_HOLD),
        (F.AFTER_REGISTRY_REPLACE, CP.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD),
        (F.AFTER_REGISTRY_FLUSH, CP.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD),
        (F.AFTER_DESCRIPTOR_MARK, CP.REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD),
        (F.AFTER_DESCRIPTOR_REPLACE, CP.BOTH_AFTER_JOURNAL_PENDING_HOLD),
        (F.AFTER_DESCRIPTOR_FLUSH, CP.BOTH_AFTER_JOURNAL_PENDING_HOLD),
        (F.AFTER_RELEASE, CP.BOTH_AFTER_JOURNAL_PENDING_HOLD),
    ],
)
def test_abrupt_child_exit_requires_fresh_pending_journal_hold(
    native_disposable_scope: None,
    boundary: drill.PrivateScratchDualStageFault,
    expected: canonical.PrivateCanonicalRestartCheckpoint,
) -> None:
    with tempfile.TemporaryDirectory(prefix="core238_3g58_crash_") as scratch:
        root = Path(scratch)
        token = secrets.token_hex(16)
        (root / _MARKER).write_bytes(b"core238-3g58:" + token.encode("ascii"))
        outcome = _child(root, token, boundary.value)
        assert outcome.returncode == _HARD_EXIT, (
            boundary.value,
            outcome.returncode,
            "hard-exit worker refused or returned before the selected boundary",
        )
        assert not outcome.stdout
        checked = canonical._canonical_fork_intent()
        raw = intents.encode_private_transaction_intent(checked)
        private = root / "private"
        association = root / "workspace" / ".pds"
        names = canonical._paths(private, association)
        registry, registry_stage, descriptor, descriptor_stage, journal = names
        assert durable._exact(journal, raw)
        assert registry.is_file() and descriptor.is_file()
        assert registry_stage.is_file() is (expected is CP.PREPARED_HOLD)
        assert descriptor_stage.is_file() is (
            expected is not CP.BOTH_AFTER_JOURNAL_PENDING_HOLD
        )
        before = _images(names)
        # The separate parent process obtains NEW OS locks and directory handles.
        with restart._held_existing_restart_lock(private / ".native-lock"):
            with parents._hold_four_parents(
                parents._parent_roots(private, association)
            ) as fresh:
                parents._require_held(fresh)
                observed = canonical._checkpoint(private, association, checked)
                parents._require_held(fresh)
        assert observed is expected
        assert durable._exact(journal, raw)
        assert _images(names) == before  # Independent restart is read-only.
        assert (private / "transactions").is_dir()
        # Do not retry the replacement or retire the pending journal.
        assert journal.exists()


@pytest.mark.parametrize(
    ("token", "boundary"),
    [
        ("not-a-valid-token", F.AFTER_REGISTRY_REPLACE.value),
        ("0" * 32, F.AFTER_REGISTRY_REPLACE.value),
        ("A" * 32, F.AFTER_REGISTRY_REPLACE.value),
        ("0" * 32, "unrecognized-boundary"),
    ],
)
def test_child_refuses_unqualified_request_without_writing(
    token: str, boundary: str
) -> None:
    with tempfile.TemporaryDirectory(prefix="core238_3g58_crash_") as scratch:
        root = Path(scratch)
        (root / _MARKER).write_bytes(b"core238-3g58:" + (b"1" * 32))
        before = tuple((p.name, p.read_bytes()) for p in root.iterdir())
        outcome = _child(root, token, boundary)
        assert outcome.returncode == 2
        assert not outcome.stdout
        assert tuple((p.name, p.read_bytes()) for p in root.iterdir()) == before


def test_child_refuses_unreserved_scratch_path() -> None:
    with tempfile.TemporaryDirectory(prefix="core238_3g58_crash_") as scratch:
        root = Path(scratch)
        outcome = _child(root, "0" * 32, F.AFTER_PREPARED.value)
        assert outcome.returncode == 2
        assert not tuple(root.iterdir())


def test_child_refuses_non_direct_temp_directory() -> None:
    with tempfile.TemporaryDirectory(prefix="core238_3g58_crash_") as scratch:
        root = Path(scratch)
        nested = root / "core238_3g58_crash_nested"
        nested.mkdir()
        token = "1" * 32
        (nested / _MARKER).write_bytes(b"core238-3g58:" + token.encode("ascii"))
        outcome = _child(nested, token, F.AFTER_PREPARED.value)
        assert outcome.returncode == 2
        assert not (nested / "private").exists()


def test_worker_has_no_installable_production_main() -> None:
    assert _CHILD.is_file()
    assert _CHILD.parent.name == "tests"
    assert not hasattr(drill, "_hard_process_termination_writer")
