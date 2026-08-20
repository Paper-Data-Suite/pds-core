"""Internal exclusive-write coordination for canonical class rosters."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class RosterWriteLockError(RuntimeError):
    """Raised when the internal roster write lock cannot be managed safely."""


class RosterWriteLockConflictError(RosterWriteLockError):
    """Raised when another canonical roster writer already holds the lock."""


def roster_write_lock_path(roster_path: str | Path) -> Path:
    """Return the hidden lock path paired with one canonical roster path."""
    return Path(roster_path).parent / ".roster.write.lock"


@contextmanager
def acquire_roster_write_lock(
    roster_path: str | Path,
    *,
    create_parent: bool = False,
) -> Iterator[None]:
    """Exclusively coordinate a canonical class-roster write.

    The lock is intentionally a small internal filesystem primitive. Callers
    are responsible for validating expected roster state while the lock is
    held. Generic roster writes preserve their existing missing-parent error;
    guarded first-import commits may explicitly create the canonical class
    directory before acquiring the lock.
    """
    target_path = Path(roster_path)
    target_dir = target_path.parent
    lock_path = roster_write_lock_path(target_path)

    if create_parent:
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise RosterWriteLockError(
                f"Could not create roster directory {target_dir}: {error}"
            ) from error

    lock_created = False
    try:
        try:
            with lock_path.open("x", encoding="utf-8", newline=""):
                lock_created = True
        except FileExistsError as error:
            raise RosterWriteLockConflictError(
                f"Roster write lock already exists: {lock_path}"
            ) from error
        except OSError as error:
            raise RosterWriteLockError(
                f"Could not acquire roster write lock {lock_path}: {error}"
            ) from error

        yield
    finally:
        if lock_created:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                # Match Core's other lock-file writers: a cleanup failure must
                # not mask the result of the canonical write that already ran.
                pass
