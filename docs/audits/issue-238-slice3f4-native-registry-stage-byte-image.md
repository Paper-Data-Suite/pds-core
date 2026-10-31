# Core #238 — Slice 3F4: native exact registry-stage image, read-only

Baseline: feature `698eb7bef87dee4518c34cfccb279d9491baa911`; `main` `a0d5e1a50580bbe025f0cad23c7e8524203a52ec`.

## Scope

Add `pds_core/_teacher_private_registry_stage_image_snapshot.py` and synthetic tests. No existing source edits, no new public capabilities, no Notes data or service activation.

The internal reader handles one `.{uuid4}.registry-stage` file in the qualified local private root. It requires the effective OS owner; rejects symlinks, hard links, unsafe protection/backing and changed file identity; bounds and validates the exact canonical private-registry bytes, including owner. Linux reads through a no-follow directory file descriptor with `0600`/ACL/local-backing checks. Windows opens a native read-only no-write-sharing handle, checks DACL, FileId and native metadata on retained and reopened handles, and refuses reparse points. Neither uses caller input as a filesystem path.

The outer API validates an existing non-initialize canonical transaction intent, retains the existing ordered locks and three native guard layers, inventories stage names before and after, and performs two independent exact-byte reads of the named stage. It compares their bytes to each other and to the proposed registry after-image, then verifies the effective owner. The native readers are called **internally**, never via lock-reacquiring public entrypoints. A successful exit from the retained guard is required for any matching observation.

## Explicit refusals and limitations

All output messages are bounded and sanitized. Returned public results contain no stage path, principal, transaction identifier, after-image bytes, handle, approval, CAS token, or storage scope. The internal native-read function retains a private byte image only for its immediate caller; it is never a write capability. No metadata, registry, stage, journal, workspace descriptor, or Notes file is created, rewritten, replaced, moved, or deleted.

A stage-byte match **does not** prove journal admission, stage durability, atomic registry replacement, sidecar commit, cross-process/cloud synchronization, or crash-safe replay. An unqualified inventory or a foreign/corrupt stage must not be ignored. Same-OS-user malware and non-cooperating sync writers remain outside the local lock boundary.

## Qualification gates

Windows Core must pass focused pytest, Ruff lint and formatting, strict mypy, full pytest, Git exact-file scope and exact remote/pinned-blob checks before commit/push. Linux/native simulation is supplemental, not a substitute for native Windows validation.

## Follow-up

A separately reviewed coordinator must prove journal-stage linkage, protected write-target identity, exact-before CAS, persisted transition ordering, and crash-recovery handling before replacing `registry.json`. Initial binding requires a separate verified absence and creation protocol. No `notes.records.v1` or `notes.cli.v1` is introduced here.
