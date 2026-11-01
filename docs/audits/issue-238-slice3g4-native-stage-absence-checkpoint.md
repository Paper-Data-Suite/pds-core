# Core #238 — Slice 3G4: retained native stage-absence checkpoint

**Baseline:** qualified 3G3 `58f77b2d492b773310d6224a223afbdd79b5aaa7`.

## Purpose

Slice 3G2's retained checkpoint requires the proposed registry-stage artifact to be
present. Slice 3G3 introduced the *pure* classifier for the different recovery
windows after a future stage consumption, but `observed_stage=None` is
caller-supplied and does not attest native filesystem absence. Slice 3G4
adds an **internal read-only native stage-absent observation** using the
existing locked journal/registry/descriptor native guard, repeated exact
image readers, strict stage inventory, and 3G3 transition classifier.

This is one side of the recovery observation contract, **not** the registry
replacement primitive, a durable transaction, a safe replay determination,
or a new supported private Notes capability.

## Scope and observation order

1. Validate exact canonical non-initialize transaction intent and qualified
   existing Windows/Linux private and workspace root requests.
2. Retain the existing ordered private locks and protected journal-directory,
   live registry, and workspace descriptor native handles throughout this
   read-only review. **Do not** acquire the locks recursively.
3. Under the retained scope, observe both entire namespaces twice, require
   exactly the proposed transaction journal, and refuse any stage-like entry.
4. Require the native stage inventory to report an empty qualified stage
   namespace, rather than trusting a missing stage filename alone.
5. Read journal, registry, descriptor, descriptor, registry, journal via the
   already-qualified protected native image readers, and reject changed,
   noncanonical, missing, owner-unqualified, or inconsistent images.
6. Invoke the pure 3G3 classifier **with `observed_stage=None` only after
   stage absence and native images have been checked**. Distinguish
   `REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW_REQUIRED`,
   `BOTH_AFTER_STAGE_ABSENT_REVIEW_REQUIRED`, and two explicit
   stage-missing-before/partial refusal statuses.
7. Recheck stage inventory, both namespaces, effective owner, and retained
   native handles before returning a sanitized advisory result.

All error states fail closed. No parent or lock is created, no journal or
stage is deleted, no registry is opened for writing, no descriptor is changed,
and no handles, raw byte images, principal IDs, or private paths are returned.

## Security interpretation

An absent stage **cannot establish that a rename occurred**. It could have
been absent for other reasons. Even when native registry bytes match the
proposed after-image, the checkpoint does not establish write-through,
durable directory-entry ordering, authorization, cross-file atomicity, a
confirmed teacher decision, journal retirement, or permission to expose Notes.
The retained local locks and repeated directory enumeration do not exclude
hostile same-OS-user, network, or cloud-synchronization races. Windows file
sharing and source/target handle continuity for a future *mutating* registry
replacement require a separate, mutation-aware guard; existing immutable
read-only guards MUST NOT be reused across rename/replacement.

`INITIALIZE` remains refused pending its separately guarded absence protocol.
No `notes.records.v1`, Notes menu, Notes CLI or portability capability is
advertised. All test identifiers, roots and metadata contents are synthetic.

## Qualification and next boundary

24 isolated synthetic regression cases passed before packaging. Windows
checkout qualification still requires the guarded runner: exact source tree
and remote pins, 56-file focused selection, Ruff lint/format, strict mypy and
Git hygiene. Full Core pytest may be deferred from the 3G3 integration
checkpoint (4,485 passed; 174 skipped). This source qualification is **not**
D2 native Windows/Linux/macOS, installed-wheel crash/recovery, or the supported
storage API.

The next implementation boundary is a native mutation-aware registry target
replacement design/protocol with strict exact-before validation and explicit
crash durability and replay ownership. No writer should be enabled by this
read-only checkpoint alone.
