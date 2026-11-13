# Core #238 — Slice 3G19: Disposable native writer rehearsal

**Status:** candidate for guarded Windows qualification; not a production recovery writer.

## Intent and scope

This slice moves one specific mechanism beyond the caller-reported phase traces of 3G18: it exercises a **real `os.replace` native filesystem operation** on **fixed synthetic bytes**, created inside a fresh `tempfile.TemporaryDirectory`. The operation is performed while an OS-native **advisory lock on an internal synthetic lockfile** is held. The module checks the exact preimages and scratch namespace, performs the replacement, checks exact postimages and namespace, issues a file-only `os.fsync` request, checks images again, and releases the lock. It reuses 3G18's internal phase-order validator. The result is a sanitized enum and fixed message.

The module's entry point accepts **only an exact interruption enum**. It accepts no path, workspace hint, byte image, transaction intent, owner, callback, file descriptor, token, or native writer delegate. It cannot reach real teacher-private files through its public arguments. Every file it directly creates has a fixed synthetic name and byte sequence; its temporary directory is disposed when the rehearsal ends. The code supports native Windows (`msvcrt.locking`) and Linux (`fcntl.flock`) rehearsal, not a production fallback on other platforms.

## Rehearsal sequence

1. Allocate one private temporary scratch directory and create four regular synthetic files: registry before-image, registry after-image stage, descriptor, and pending journal. Their bytes are deliberately **not** real private metadata.
2. Create a one-byte synthetic lockfile and acquire a nonblocking exclusive native advisory lock.
3. Under the lock, validate expected names, file types, link counts, and exact bounded bytes.
4. Run a real `os.replace(stage, registry)` under the same lock. The stage and registry are created on the same scratch directory.
5. Under the lock, revalidate registry after-image, descriptor, journal, absent stage, and complete filename namespace.
6. Request file-only sync of the replaced registry, then revalidate postimages and phase ordering again.
7. Release the scratch lock; only after releasing, return `PERSISTENCE_UNQUALIFIED`. The result is not a durable success status.

Controlled interruption injection at guard acquisition, precheck, native replacement return, postcheck, and file-sync completion returns `INTERRUPTED_PRESERVE`. This is **in-process fault injection**, not a simulated process kill, power failure, or crash-recovery proof. An actual `KeyboardInterrupt` also receives this sanitized preserve result. Filesystem and lock refusals are fail-closed.

## Security and unsupported claims

- **No production mutation:** The only writer target is a newly created temporary synthetic directory. No user-selected path or user-supplied data enters this API. Scratch disposal is appropriate because it contains no teacher data.
- **No production guard proof:** The synthetic lock is a native **advisory** file lock, not the Core retained descriptor/journal/registry guard. It coordinates only lock-honoring rehearsal participants. It does not prove safety against a hostile same-user process, reparse/symlink races, another OS identity, network-backed temporary storage, antivirus interference, or files not under the synthetic lock.
- **No durable commit:** A successful `os.replace` return and file `fsync` cannot certify durable namespace changes, Windows directory flush semantics, the ordering of parent-directory persistence, power-loss crash replay, or the lifetime of pending journal data. The only successful state is `PERSISTENCE_UNQUALIFIED`.
- **No journal retirement:** The pending synthetic journal is deliberately retained throughout the operation. The module cannot retire a journal, repair an association descriptor, create an initial binding, emit Notes capabilities, or authorize application behavior.
- **No recovery replay semantics:** The operation's fixed, noncanonical scratch byte literals are not an encoded `PrivateTransactionIntent`. This tests native operation sequencing and fail-closed image checks, **not** the end-to-end association binding, expected-revision CAS, transaction recovery, native file-ID custody, or cross-process consistency.
- **Fail-closed response:** A missing/tampered preimage refuses the writer. A returned operation with incorrect postimage is classified as conflict. Unexpected I/O, sync and lock failures never return a qualified commit or mutation token.

## Qualification requirements

The guarded runner must validate the exact 3G18 feature-branch commit and `main`, remote heads, inherited Git blobs, source manifest, and clean checkout. It must run the new regression suite, the full focused Core #238 selection, Ruff, strict mypy, and the periodic full Core pytest integration checkpoint before committing or pushing. Failure must leave the candidate files for targeted repair without reset/stash/cleanup.

## Future work

3G20 should investigate native guard custody and file identity at the actual descriptor/journal/registry boundary, especially Windows native replace behavior after test-order interaction and cross-process lock ownership. **Do not reuse this synthetic rehearsal entry point as a production writer.** Separate native persistence, directory-flush/retirement protocols, initialization, and Notes authorization remain independently gated under #238 and successor tickets.
