# Core #238 — Slice 3G94: explicit synthetic checkpoint/recovery protocol

## Purpose

3G89–3G93 established that Linux/Windows rename and replace operations do not
atomically compare a previously checked file's identity or contents. The next
engineering step is a **bounded, executable cooperating-writer checkpoint
protocol** rather than another OS primitive counterexample. This exercise
accepts only an exact scenario enum and uses one freshly allocated temporary
root with fixed synthetic registry/descriptor/stage/journal bytes. It never
opens a real teacher workspace or private root, accepts a caller path/identity,
or enables Notes records, binding or production mutation.

## Monotonic journal and operation

The canonical versioned journal has a fixed synthetic operation identifier,
exact before/after images, a journal phase, and an explicit prohibited-retirement
field. It is initially `prepared`; each checkpoint rewrite uses an exclusive
`.next` file, fsync on the file and a same-directory atomic rename. The
registry and descriptor each have their own staged afterimage. The cooperative
lock remains held for every individual synthetic operation; the lock is released
between interruption and explicit resume.

Journal/mutation steps:

1. Persist `registry_intent` checkpoint.
2. Rename staged registry to live registry.
3. Persist `registry_done` checkpoint.
4. Persist `descriptor_intent` checkpoint.
5. Rename staged descriptor to live descriptor.
6. Persist `both_pending_review` checkpoint; **do not retire journal**.

Seven cut points include the initial `prepared` checkpoint, before and after
each file mutation, confirmed registry, and the final pending-review journal.
The synthetic explicit resume function reads **journal and actual exact file
images**, not a caller-supplied phase. It safely recognizes when a staged
mutation occurred before its journal acknowledgment, advances the remaining
steps, and then rechecks that a repeated resume is a no-op. The journal remains
pending after apparent completion, because the production commit/retirement
protocol is unqualified.

## Conservative conflict policy

Four injected disruptions—corrupt canonical journal, altered live registry,
altered stage, and interrupted `.next` checkpoint temporary—must result in an
explicit conflict/hold with **no resume mutation and no deletion of evidence
inside the disposable exercise**. An interrupted checkpoint rewrite is not
blindly retried, overwritten or cleaned. Temporary roots are discarded only
when the entire independent synthetic test exits; this is not a production
evidence-retention mechanism.

## Nonclaims

- This is **not** production crash durability, power-loss simulation, native
  handle-relative replacement, or atomic two-document commit. File fsync
  requests are not complete directory durability or recovery guarantees.
- A cooperating lock does not prevent arbitrary same-owner code from modifying
  paths between checks. The modeled explicit resume is not a production API,
  automatically invoked replay, arbitrary file recovery, or write permit.
- A successful synthetic journal checkpoint is never sufficient to qualify
  the actual descriptor/registry/owner ACL binding or private Notes service.
- Unsupported platforms refuse before scratch setup. All **nine** production readiness blockers, the production write barrier,
  existing terminal capability set, and no-auto-replay/no-retirement/no-Notes
  boundaries remain unchanged.

## Qualification

Nineteen focused source cases cover seven interruption/resume checkpoints,
four conflicts, five untrusted scenario values, taxonomy drift, and public API
boundary. The 26th isolated installed-wheel gate repeats every fixed scenario,
checks wheel provenance, exact bounded states, idempotence, pending journal,
negative authority fields and sanitized evidence. Preserve all 25 predecessor
gates, strict Linux and Windows mypy, Ruff and conditional exact-scope commit.

## Next

3G95 should add fresh-process interruption and conservative checkpoint
reclassification, with durable ordering and platform differences explicitly
separated; never mistake a simulated stop for a crash/power-loss guarantee.

## Slice 3G94 Repair 1 — Linux lock-file creation mode

The original 3G94 Windows local qualification passed, committed and pushed,
but GitHub Actions Linux runners reported 11 failures in the checkpoint
scenarios. All returned `scratch_custody_refused` before completing; the
installed-wheel Linux gate also refused. Investigation of Core's native
`hold_existing_private_lock` contract isolated a creation-mode defect:
`Path.open("xb")` uses default mode `0666 & ~umask`, normally `0644` on
GitHub Linux runners, while the existing-file lock refuses any POSIX mode other
than owner-only `0600`. This is a concrete regression in the synthetic lock
fixture, not evidence of an authorized production storage operation.

The repair changes only the synthetic `_exclusive` file creator to use
`os.open(O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW, 0o600)` on POSIX, with
`O_BINARY` where supported for exact byte images on Windows. It requires
a full-sized write, fsync request, and descriptor closure. The `0600` mode
is established **at creation**, not repaired with a delayed chmod. A native
Linux regression test proves the new lock can be acquired by Core's unchanged
existing-file lock primitive. No OS ownership or ACL production claims follow
from the synthetic result.

All checkpoint states, journal transitions, existing installed-wheel
contracts, and CI workflow steps are unchanged. The original 26 native
installed-wheel gates, Ruff, dual-platform mypy, focused pytest and
conditional guarded commit/push must be rerun. All nine production blockers,
no-auto-replay, no-journal-retirement and no-Notes guarantees remain intact.
