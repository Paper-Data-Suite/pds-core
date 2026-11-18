# Core #238 — Slice 3G96: persistence ordering and uncertain-state review

## Exact baseline and trust boundary

The accepted 3G95 Repair 1 commit is `d22697c58c6c124902d50de34c983bf7ea3d021b`, after successful local qualification (168 passed, 12 skipped, 27 isolated installed-wheel gates) and GitHub CI (15/15). 3G94–3G95 establish a synthetic, versioned journal and independent, manually invoked recovery across seven interruption points. This slice **does not extend production authority**; it separately verifies which ambiguous post-interruption states must be held without recovery, especially where a persisted phase may not be synchronously durable with the directory namespace.

The public probe accepts **one exact enum**. It creates one random temporary root with fixed synthetic registry, descriptor, stage, journal and lock files. It never receives a caller path, owner identity, payload, operation ID, callback, or real private root. All leaf creation uses the existing 3G94 exclusive owner-only (0600) routine. A 3G95 child producer holds Core's existing-file coordination lock, executes the specified operations and hard-exits without executing context-manager cleanup; a separate inspector reacquires the lock to read only the on-disk evidence. The parent independently compares byte-for-byte snapshots before/after that inspection. No explicit recovery process is launched.

## Seven case matrix

| Scenario | Producer cut / injected evidence | Required evidence classification | Permitted action |
| --- | --- | --- | --- |
| Orphan checkpoint temporary | Prepared; exclusive `pending-journal.next` exists | `conflict_preserve`, no trusted phase | Hold without deleting `.next` |
| Registry rename before journal acknowledgement | `registry_installed`: registry afterimage exists, registry stage missing, journal says `registry_intent` | `confirm_registry` / `registry_intent` | **Uncertain hold**; do not advance automatically |
| Descriptor rename before journal acknowledgement | `descriptor_installed`: descriptor afterimage exists, descriptor stage missing, journal says `descriptor_intent` | `confirm_descriptor` / `descriptor_intent` | **Uncertain hold**; do not advance automatically |
| Both documents complete, journal still present | `both_pending_review` | `complete_hold` / `both_pending_review` | Pending manual review; **no retirement** |
| Corrupt canonical journal | Prepared; canonical journal corrupted | `conflict_preserve`, no trusted phase | Hold; preserve evidence |
| Acknowledged phase mismatches registry bytes | `registry_confirmed`; live registry bytes then changed | `conflict_preserve` / `registry_done` | Hold; preserve evidence |
| Linux parent directory `fsync` request | `both_pending_review`; call `fsync` on opened directory, checking its identity before and after | `complete_hold` / `both_pending_review` | Linux: syscall observed, **still pending review**; Windows: explicitly unqualified without file creation |

No scenario calls `_explicit_resume`, deletes evidence, retires the journal, or changes the real Core registry. Some 3G95 synthetic states would be explicitly resumable through a separate deliberately invoked API, but this persistence-ordering gate never interprets a journal as proof of crash-stable ordering. The conservative hold is intentional and does not override 3G95's bounded synthetic outcome.

## Native semantics and limitations

3G94 requests file `fsync` on exclusive file creation and checkpoints, then performs same-directory `os.replace`, but does **not** request a directory `fsync` at each rename. On Linux, opening the directory with `O_DIRECTORY` and requesting a native `fsync` provides a measured system-call outcome for **one** scratch checkpoint. It is not a blanket durability guarantee for all filesystem, mount, power-loss, journal, or staged document orderings. On Windows, directory `fsync` is explicitly unqualified in this gate; no POSIX fallback is invented.

A positive Linux syscall result does not establish the real application's filesystem protection, parent-handle continuity or transaction ordering. A synthetic process hard-exit is not a power loss, and the test does not simulate durability loss by deleting arbitrary data. A cooperative lock excludes only participating writers; it does not establish exclusion of arbitrary same-OS-user code or atomic expected-content compare-and-swap.

## Qualification

New source tests cover all seven scenarios, five invalid inputs, unsupported-platform and requirement-drift refusal, and public API/capability isolation. The **28th** installed-wheel gate repeats all scenarios, checks isolated installed Core provenance, counts exactly 14 Linux or 12 Windows independent child interpreters, checks untouched evidence, fixed result labels and no-authority flags. Preserve all 27 predecessor gates, Ruff, strict mypy (both Linux and Windows), focused pytest, guarded baseline/CI/worktree checks and conditional commit/push. A failed gate must preserve the stopped checkout and not reset, stash, auto-repair or delete any unowned file.

## Subsequent gate

3G97: enumerate and conservatively qualify interrupted checkpoint re-entry after an actual fresh process restart with native owner/custody checks, without treating directory flush as a license to replay or retire a real journal. The nine production-operation blockers, no-binding/no-Notes barrier and no-auto-replay policy remain in force.
