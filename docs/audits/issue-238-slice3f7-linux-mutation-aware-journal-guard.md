# Core #238 — Slice 3F7: Linux mutation-aware journal creation guard

**Baseline:** qualified Slice 3F6 `dca4c74083a4d376e91eb2e86a32dd3e976e1b24`.
**Scope:** one *additive*, internal, Linux-only retained journal-creation guard; synthetic regression tests; this audit. Existing read-only guards are unchanged.

## The narrower guard

`hold_expected_private_journal_creation(proposed, private_root, workspace_root)` is a context manager. It returns **no handle, write token, transaction authority, path, or result object**. It does **not** write any files or call the journal provisioner itself. A future internal coordinator may invoke the already existing create-only journal primitive within this scope, but neither API is wired to a public service. Windows and other platforms fail closed with `UNSUPPORTED`, pending an independent native proof of parent/entry continuity.

For the Linux path, the scope:

1. Canonicalizes/redecodes an existing non-`INITIALIZE` intent and validates requested roots before locks or mutation.
2. Acquires the established **ordered local registry/workspace locks**, then retains the existing protected registry file and workspace association descriptor using their private native scopes. Calling their public wrappers would reacquire the immutable retained journal guard and make the expected journal-directory timestamp change a false refusal.
3. Opens and retains the native private `transactions/` directory via the existing qualified owner-private POSIX parent opener. Before yielding, verifies its native inode/device/mode/owner/link count against the present path, ACL and known local backing; demands **two empty directory observations**.
4. On normal scope exit, allows *only the directory metadata timestamps* to change; rechecks handle/path native identity, ACL and backing. Demands exactly the one UUID-derived `.json` entry, owner-private regular-file protections, same backing, one hard link and expected size. Calls the native journal image reader **twice**, requiring both canonical byte images to exactly match the proposed intent, and rechecks the final directory entry set and owner.
5. Lets the enclosing registry/descriptor scopes and ordered coordination validate their own anchors at exit. No automatic removal, retry, rollback, staging, rename, registry replacement or Notes access occurs.

## Important limits and failure handling

- Directory timestamp changes are expected for Linux file creation but **do not establish causality**. A non-cooperating same-user writer can still race and restore a namespace between observations. Local ordered locks are not distributed arbitration.
- If a caller raises during creation, this scope lets the exception propagate; it does not infer that no bytes were written or remove partial artifacts. A later independent recovery review is required. If scope exit rejects a file or directory, preserve all observed evidence.
- The guard is **not durable journal admission**. File `fsync` and parent `fsync` ordering is the responsibility of the underlying create-only primitive; this scope does not establish reliable Windows namespace durability, general power-loss guarantees, or a cross-file transaction protocol.
- The existing immutable guard remains in use by every read-only observation. This separate guard can validate *one journal creation* only; it is not usable to create a registry stage beside `registry.json` because that requires its own mutation-aware private-root parent contract. It does not create or authorize registry metadata CAS or a workspace descriptor write.
- `INITIALIZE` remains unsupported until a distinct verified-absence protocol exists. Cloud/network filesystem arbitration and untrusted workspace sync remain out of scope.

## Regression matrix and qualification

Portable synthetic tests reject changed inode, owner, mode, symlink, ACL, remote backing, additional entries, hard links, wrong owner, short/wrong byte images and native-read refusal. Non-root Linux native temporary-directory tests exercise a normal single create, missing entry, foreign entry, preexisting collision, mode refusal, hard-link refusal and unexpected additional entry. No real PDS user store is touched.

No new public capability is advertised; no `READY`, binding commit, metadata replacement, recovery writer, or Notes record is introduced. **A passing result is a guarded observation, not write authorization.**
