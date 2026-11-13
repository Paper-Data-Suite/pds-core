# Core #238 — Slice 3B6: Existing-file cross-process coordination primitive

**Baseline:** `72b31a24088f105388f937098ea7f043dd9003f9` (Slice 3B5).
**Stage:** Internal, noncreating native lock mechanism. D0 security/transaction decisions remain subject to owner approval; this is neither native private-store qualification nor permission to persist teacher Notes.

## Implemented boundary

`pds_core._teacher_private_file_lock.hold_existing_private_lock(path)` acquires a nonblocking exclusive OS lock on the first byte of an **already-existing, nonempty, single-link regular file**. It neither creates a lock file nor writes or truncates its contents. The helper refuses relative paths, symlinks and obvious aliases, checks an opened descriptor against its observed file identity, uses POSIX `flock` on Linux/macOS and Windows `msvcrt.locking` on Windows, and reliably releases its lock/descriptor on normal or exceptional exit. Contention returns the sanitized `BUSY` failure; it never waits indefinitely, removes a purported stale lock or changes permissions.

**Windows note:** Windows byte-range locking is a coordination primitive, not ACL verification. `CreateFileW`-based ancestor/owner/DACL/reparse checks in the prior refusal probes are nonauthorizing snapshots. A later protected writer must hold and reverify qualified native handles, effective ACL, actual local-filesystem backing and transaction revisions while coordinating descriptor and registry locks. This helper's `os.open` on Windows is not claimed to be a no-follow, directory-handle-secure operation.

**POSIX note:** Require 0600 single-link owner-owned file and `O_NOFOLLOW` on the final component. Parent ancestry, POSIX ACL and filesystem-locality validation remain the consuming guarded service's responsibility. Holding `flock` on one file does not serialize writers that ignore or replace that file, and the operation is **not safe to use as a universal private-store authorization**.

An intentionally nonempty lock file must be **provisioned by a future qualified, explicit storage-initialization operation** with protective permissions from its first moment. This slice does not provision such a file or touch the real OS-user Notes location.

## Tests and exclusions

`tests/test_teacher_private_file_lock.py` uses synthetic `tmp_path` files and verifies no implicit creation; nonmutation; unsafe modes, symlinks, hard links and empty targets; nested contention; process-to-process contention; release after exceptions; bounded errors; and the exact negative Notes capability contract. On Windows native tests exercise `msvcrt` where run; on Linux native tests exercise `fcntl`. Actual native installed-wheel and supported-filesystem qualification remain Slice 7, and macOS native qualification remains unproven unless separately run.

No workspace `.pds` descriptor, private registry, transaction journal or Notes/Task record is created by the production API. No change to existing `workspace.py`, Core CLI/menu or producer repositories; no new capability token or release claim. Further required slices: D0 accepted security policy; protected directory/lock-file creation with ACL and effective-locality proof; two-lock ordering; journal persistence and atomic metadata updates; recovery of interrupted writes; explicit reviewed bind/move/fork; D1 adversarial and D2 native installed qualification.
