# Core #238 — Slice 3G95: fresh-process checkpoint recovery, scratch only

## Scope and relationship to 3G94

The accepted 3G94 synthetic checkpoint model executes journal checkpoints and
explicit resumption within one Python interpreter. 3G95 extends **the same
seven checkpoints and four conflict classifications** across independent
Python interpreters. The source creates a new disposable, fixed-content
synthetic registry/descriptor/stage/journal directory each invocation. Its only
public argument is an exact enum. No teacher workspace, private-root path,
owner identity, real file content, transaction, handle, or callback is supplied
by callers. It never reaches a production registry or Notes service.

## Executable process boundary

For each of the seven cuts:

1. A producer process acquires the existing cooperative lock, executes exactly
   the selected number of 3G94 journal and file transitions, then exits with
   `os._exit(80 + checkpoint_index)` instead of orderly returning. The OS closes
   its handles and releases the lock; this is an interpreter/process-stop test,
   **not** a power-loss simulation.
2. A separate inspector process reacquires the lock and classifies the journal
   and actual exact file images. The parent verifies a byte-for-byte snapshot
   is unchanged across this read-only inspection.
3. A distinct, explicitly launched recovery process reacquires the lock and
   calls 3G94's bounded `_explicit_resume` using on-disk evidence, not the
   producer's claimed phase. It must reach `both_pending_review`, leaving the
   journal present, with exact registry and descriptor afterimages.
4. A fourth new recovery interpreter reopens the same evidence and confirms a
   zero-step no-op with no evidence mutation.

For four conflict inputs (corrupt canonical journal, changed registry bytes,
changed stage bytes, and an orphan `.next` checkpoint), three separate processes
are used: producer, inspector and attempted recovery. Both inspector and
recoverer must classify conflict, with **zero steps** and **identical on-disk
file images** before and after. No automatic reset, retry, repair, or journal
retirement is attempted. Expected interpreter launches: 7×4 + 4×3 = 40.

## Explicit limitations

- These are fixed disposable file names and synthetic payloads under the local
  OS temp directory. TemporaryDirectory cleanup after the independent probe is
  **not** permission to discard uncertain evidence in production.
- Child processes use `python -I`, a bounded internal role/enum vocabulary, and
  only the package root derived from the module's own installed/source path.
  Child output is a sanitized JSON classification with no paths/identities.
- The cooperative file lock serializes *participating* processes only. It does
  not exclude arbitrary same-OS-user mutation or supply an atomic file-content
  CAS, a handle-relative two-root operation, atomic two-file commit, or
  guaranteed filesystem durability.
- An unclean process exit is not proof of an OS crash, abrupt termination at
  every syscall boundary, or power-failure restart behavior. File fsync requests
  in 3G94 do not imply directory-fsync ordering across Linux/Windows.
- No production write admission, initial binding, Notes records, automatic
  recovery/replay, automatic retry, journal retirement, or portability exists.
  The nine production-operation readiness blockers remain unqualified and
  the public terminal capability set is unchanged.
- macOS/unsupported platforms explicitly refuse before scratch creation.

## Qualification

Nineteen new source tests exercise seven interruption/resume cuts, four
non-mutating conflicts, five malformed inputs, requirement drift, unsupported
platform, and narrow public API/negative capability boundary. A 27th installed
Core wheel gate repeats every scenario using 40 independent interpreters,
checks wheel provenance, no repository scratch mutation, exact bounded outcomes,
no authority flags and a sanitized evidence report. All 26 predecessor gates
are retained. Source qualification requires Ruff, strict mypy for Linux and
Windows, focused pytest and an exact-scope guarded conditional commit/push.

## Next gate

3G96 should measure persistence ordering and cold-process inspection under
platform-specific native flush support, including mid-checkpoint transient
states, while preserving uncertain evidence. Do not promote synthetic
fresh-process completion into production crash durability or a real binding
permit without separately qualifying the OS owner, native custody and full
recovery transaction.


## Slice 3G95 Repair 1 - source lint qualification

The initial Windows qualification stopped immediately after the 168-test
focused suite (12 native/platform skips), when Ruff F401 found an unused
module-scope `import os`. The process producer independently imports `os`
inside its isolated child program; the outer module does not reference it.
Removing only the outer unused import changes no child process, assertions,
scratch filesystem actions, recovery decisions, journal, or production boundary.
The source qualification runner, 27 installed-wheel gates, and CI workflow
remain unchanged. The guarded repair authenticates the exact five-file
stopped worktree, then resumes the original full qualification.

All nine production-operation requirements remain blocked. No automatic replay,
journal retirement, binding, or Notes records become available.
