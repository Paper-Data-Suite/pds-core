"""#238 Slice 3B6: existing-file, no-create cross-process coordination."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from pds_core import _teacher_private_file_lock as locking
from pds_core.teacher_experience import get_teacher_experience_capabilities


def lock_file(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic-existing.lock"
    path.write_bytes(b"0")
    if sys.platform != "win32":
        path.chmod(0o600)
    return path


def test_lock_existing_file_preserves_exact_content_and_metadata(
    tmp_path: Path,
) -> None:
    path = lock_file(tmp_path)
    before = path.read_bytes()
    before_metadata = path.stat()
    with locking.hold_existing_private_lock(path) as result:
        assert result is None
        # Windows byte-range locks block other handles from reading the locked
        # byte. Verify unchanged contents only after releasing the lock.
    assert path.read_bytes() == before
    after_metadata = path.stat()
    assert (after_metadata.st_size, after_metadata.st_mtime_ns) == (
        before_metadata.st_size,
        before_metadata.st_mtime_ns,
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == [path.name]


def test_missing_file_refused_without_creation(tmp_path: Path) -> None:
    path = tmp_path / "missing.lock"
    with pytest.raises(locking.PrivateExistingFileLockError) as error:
        with locking.hold_existing_private_lock(path):
            pytest.fail("must not acquire absent lock")
    assert error.value.code is locking.PrivateExistingFileLockCode.MISSING
    assert list(tmp_path.iterdir()) == []


def test_relative_path_refused_without_write(tmp_path: Path) -> None:
    with pytest.raises(locking.PrivateExistingFileLockError) as error:
        with locking.hold_existing_private_lock(Path("relative.lock")):
            pytest.fail("must not acquire relative path")
    assert error.value.code is locking.PrivateExistingFileLockCode.INVALID_PATH
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["directory", "empty", "hardlink"])
def test_unsafe_lock_target_refused(tmp_path: Path, kind: str) -> None:
    path = lock_file(tmp_path)
    if kind == "directory":
        path.unlink()
        path.mkdir()
    elif kind == "empty":
        path.write_bytes(b"")
    else:
        alias = tmp_path / "link.lock"
        try:
            os.link(path, alias)
        except (OSError, NotImplementedError):
            pytest.skip("hardlink unsupported by fixture filesystem")
    with pytest.raises(locking.PrivateExistingFileLockError) as error:
        with locking.hold_existing_private_lock(path):
            pytest.fail("unsafe lock should be refused")
    assert error.value.code is locking.PrivateExistingFileLockCode.UNSAFE_FILE


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes required")
def test_permissive_mode_refused(tmp_path: Path) -> None:
    path = lock_file(tmp_path)
    path.chmod(0o644)
    with pytest.raises(locking.PrivateExistingFileLockError) as error:
        with locking.hold_existing_private_lock(path):
            pytest.fail("permissive lock should be refused")
    assert error.value.code is locking.PrivateExistingFileLockCode.UNSAFE_FILE


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks required")
def test_symlink_to_existing_lock_refused(tmp_path: Path) -> None:
    path = lock_file(tmp_path)
    alias = tmp_path / "alias.lock"
    alias.symlink_to(path)
    with pytest.raises(locking.PrivateExistingFileLockError) as error:
        with locking.hold_existing_private_lock(alias):
            pytest.fail("linked lock should be refused")
    assert error.value.code is locking.PrivateExistingFileLockCode.UNSAFE_FILE


def test_nested_independent_open_refuses_busy_and_recovers(tmp_path: Path) -> None:
    path = lock_file(tmp_path)
    with locking.hold_existing_private_lock(path):
        with pytest.raises(locking.PrivateExistingFileLockError) as error:
            with locking.hold_existing_private_lock(path):
                pytest.fail("second exclusive acquisition must refuse")
        assert error.value.code is locking.PrivateExistingFileLockCode.BUSY
    with locking.hold_existing_private_lock(path):
        pass


def test_exception_in_locked_body_releases_lock(tmp_path: Path) -> None:
    path = lock_file(tmp_path)
    with pytest.raises(ValueError, match="fixture"):
        with locking.hold_existing_private_lock(path):
            raise ValueError("fixture")
    with locking.hold_existing_private_lock(path):
        pass


def test_other_process_contends_for_same_existing_lock(tmp_path: Path) -> None:
    path = lock_file(tmp_path)
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(repo), env.get("PYTHONPATH", "")))
    code = """from pathlib import Path
import sys
from pds_core._teacher_private_file_lock import (
    hold_existing_private_lock, PrivateExistingFileLockError,
)
try:
    with hold_existing_private_lock(Path(sys.argv[1])):
        print("ACQUIRED")
except PrivateExistingFileLockError as exc:
    print(exc.code.value)
"""

    def contender() -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 - fixed interpreter and program
            [sys.executable, "-B", "-c", code, str(path)],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    with locking.hold_existing_private_lock(path):
        busy = contender()
        assert busy.returncode == 0, busy.stderr
        assert busy.stdout.strip() == "busy"
    allowed = contender()
    assert allowed.returncode == 0, allowed.stderr
    assert allowed.stdout.strip() == "ACQUIRED"
    assert path.read_bytes() == b"0"


def test_invalid_errors_do_not_echo_private_path(tmp_path: Path) -> None:
    secret = tmp_path / "do-not-print-teacher-folder.lock"
    with pytest.raises(locking.PrivateExistingFileLockError) as error:
        with locking.hold_existing_private_lock(secret):
            pass
    assert secret.name not in str(error.value)
    assert str(tmp_path) not in str(error.value)


def test_no_public_storage_service_or_capability() -> None:
    assert not hasattr(locking, "create_private_storage")
    assert not hasattr(locking, "commit_private_transaction")
    assert get_teacher_experience_capabilities() == frozenset(
        {"terminal.header.v1", "terminal.notes_command.v1"}
    )
