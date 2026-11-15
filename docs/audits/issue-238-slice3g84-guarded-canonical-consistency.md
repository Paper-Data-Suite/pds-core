# Core #238 — Slice 3G84: guarded canonical pending-intent and exact-image consistency

**Baseline:** `5ad3e5a1abf237d932f3acb8de9c64b084c7167f` (3G83 accepted after CI), draft PR #247. **Candidate:** Core 0.6.6; no new release.

## Decision

3G83 qualified a read-only retained private/workspace operation scope. 3G84 strengthens it to check **journal-derived, canonically decoded transaction intent** and the exact protected registry/descriptor/stage images while the *same* existing ordered local locks and retained descriptor/registry guard remain held. A caller supplies only an existing workspace root and a canonical UUID4 transaction-id lookup hint; the caller cannot supply the journal bytes, registry, owner, private root, native handles, bypass flags, guard, callback, or a proposed intent. All actual intent bytes must be read from a protected native journal handle, re-encoded canonically and matched to its filename UUID.

## Sequence (read-only)

1. Reject invalid platform, workspace path, transaction ID, drifted nine-blocker contract or non-blocking 3G82 preconditions **before** attempting a native guard.
2. Derive the current private root from the OS and inspect the effective process principal. Enter Core's existing `_hold_existing_retained_descriptor_guard` (ordered registry/workspace locks, private/journal/registry and descriptor retained handles). Refuse changed process owner and root during this held scope.
3. Recheck native custody of the existing private root. Examine current journal/stage namespace and exact stage inventory under the held guard, rejecting unknown or changed entries.
4. Read journal, registry, workspace descriptor and (if present) registry stage through the pre-existing native exact-image readers. Decode the journal with Core's strict `decode_private_transaction_intent`, require a byte-for-byte canonical round trip, exact transaction UUID, supported non-INITIALIZE operation, canonical before/after registries and revision witness. Require the registry owner SID/euid to match the observed process owner and the resulting association binding to name the exact existing workspace root.
5. Accept only a **blocked advisory classification** for one of three exact checkpoints: stage present + registry and descriptor before-images; stage absent + registry after and descriptor before-images; stage absent + registry and descriptor after-images. In all cases the journal remains pending. No stage, journal, registry or descriptor is written, replaced, renamed or deleted.
6. Repeat all current native image and namespace observations inside the held guard; refuse differing bytes, stage inventory, root or principal. Only then release the guard and return a sanitized enum. No path, principal, UUID, handle, raw image, lock or write capability escapes.

## Qualification

Pure checkpoint tests cover the three canonical outcomes and refusals for malformed/noncanonical journal bytes, wrong transaction UUID, process owner, accepted workspace root, revision/image mismatch, and invalid hint. Mocked held-guard tests check the temporal ordering of two image observations, byte drift, guard refusal and no returned authorization. The installed-wheel gate uses an intentionally invalid request with no filesystem mutation and checks the nine permanent production blockers. CI retains all prior 15 installed-wheel gates and adds a sixteenth sanitized gate on Windows and Linux.

## Remaining production barriers

Even a positive native exact-image observation protects only cooperative local activity during the review. It is **not** a production writer-held, hostile-writer-resistant exclusive lock, a cross-machine/cloud CAS mechanism, proof of atomic two-root commit, durable persistence or recovery after power loss. It does not authorize initial binding, automatic replay, journal retirement, Notes records, or any PDS private mutations. All nine production requirements remain unqualified.

## Next

3G85 should address operation-owned native mutation pre-admission **without executing writes**, including fresh current image/namespace and registry revision comparison under a writer-specific continuously held exclusive guard; preserve blocked state until qualified ownership, two-root CAS, durability and recovery requirements are actually implemented.


## Slice 3G84 Repair 1 — platform-independent pure checkpoint fixture

The stopped Windows local run failed the first checkpoint test because `Path("/synthetic_fork")` uses host-native Windows path spelling, while `_canonical_fork_intent()` intentionally constructs a POSIX-owner registry with the exact accepted root `/synthetic_fork`. Correctly, the owner/binding classifier refused the mismatched spelling. This repair makes the *pure lexical classifier* accept `PurePath` in its type annotation and feeds `PurePosixPath` to the synthetic POSIX image tests on both OSes. The production review still requires the host-native `Path` type and runs all native owner, retained-guard, namespace and byte-image checks without relaxation. A new test confirms Windows path spelling does not satisfy a POSIX binding and verifies Windows binding case semantics. No write path, lock, security ACL, installed verifier or CI workflow is changed.

Requalify focused pytest, Ruff, strict Linux/Windows mypy, and all sixteen installed-wheel gates before committing; retain all nine unqualified production requirements and disabled Notes/replay/retirement authority.


## Slice 3G84 Repair 2 — native held-scope fixture type consistency

Repair 1 changed the *pure lexical canonical classifier* tests to `PurePosixPath`, but inadvertently also changed the POSIX arm of `_held_setup()` to `PurePosixPath`. That setup models a native operation accepting `Path` and is annotated to return `tuple[Path, ...]`. Strict mypy correctly rejected the `Path | PurePosixPath` result, even though focused pytest and Ruff passed. Repair 2 restores `Path("/synthetic_fork")` **only** in the POSIX branch of the native held-scope test fixture. Pure canonical classifier tests remain explicitly `PurePosixPath` and still reject Windows lexical path substitution.

No production implementation, public signature, native owner/ACL rule, canonical intent check, verifier, or CI workflow changes. All sixteen installed-wheel gates and permanent production-write refusal remain required.
