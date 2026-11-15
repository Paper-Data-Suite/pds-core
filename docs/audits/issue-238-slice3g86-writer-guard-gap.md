# Core #238 — Slice 3G86: production writer-owned exclusivity gap

## Bounded objective

The accepted 3G85 review is a non-authorizing, cooperative two-root *read* scope.
3G86 prevents that result from being recast as a writer-owned transaction and
qualifies the limitation of a separate lock file using two real, independent
native processes on disposable scratch files. It does **not** enable a writer.

## Testable native counterexample

1. Hold the installed Core lock primitive on an already existing, one-byte,
   owner-local `.registry.lock` in a private disposable scratch directory.
2. A fresh interpreter attempts the **same** lock: refusal is required while
   the parent guard holds it.
3. A different fresh interpreter, ignoring the lock protocol, atomically
   replaces a separate scratch `registry.json`: the replace **succeeds**.
4. The parent observes changed exact bytes while its cooperative lock remains
   held. Only that invocation's disposable files are deleted.

This test deliberately measures the missing guarantee, not a production attack
surface: it establishes that locking a dedicated coordination file alone cannot
stop a same-user writer from changing *another* file. Native parent/file-handle
custody, sharing/replace semantics, exact in-guard CAS, interrupted-operation
handling and durability still require dedicated engineering and qualification.
It neither assumes an OS can exclude malware/same-user arbitrary mutation nor
claims any cloud-synchronized path is safe for cross-device coordination.

## Production boundary

`_teacher_private_writer_guard_gap` accepts only an untrusted workspace lookup,
transaction ID and expected revision. It reuses the exact 3G85 inventory and
returns a frozen sanitized refusal. Even an accepted prepared read review maps
to `prepared_but_exclusivity_unqualified`. No native handle, writer callback,
path, owner SID/UID, image bytes, journal or write permit escapes. The nine
permanent production blockers and the #239/#240/#243 boundaries stay unchanged.

## Native installed-artifact gate

The candidate wheel must be installed in an isolated interpreter outside the
checkout; the checker validates module provenance, unchanged terminal capability
set, actual cross-process lock contention, a concurrent uncooperative scratch
replacement and an exact postimage change. The JSON evidence is bounded to
fixed labels and wheel hash. CI adds an eighteenth Core #238 native gate on
Windows and Ubuntu, without weakening any previous gate.

## Next required work

Design and qualify the actual operation-owned native transaction guard covering
both current parent directories and live file identities **through the mutation
window**, not only the separate coordination lock. Require a reviewed fail-closed
replacement API, exact in-guard image CAS, recoverable partial-failure/journal
protocol, native Windows sharing coverage and Linux directory durability tests
before even considering production write admission.
