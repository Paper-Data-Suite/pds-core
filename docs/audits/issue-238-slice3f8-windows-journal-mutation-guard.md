# Core #238 — Slice 3F8: expected Windows journal creation scope

**Baseline:** `59f1918e0987f59c955104db89c9f2bfcd690163` (3F7). **Change:** one internal Windows-only guard module and associated regression tests; existing read-only and Linux mutation-aware guards are unchanged.

## Native guard composition

The new context validates a canonical non-initialization transaction and existing private/workspace roots before entering. It retains existing local registry-then-workspace coordination, the registry HANDLE, workspace descriptor parent/file HANDLEs, and the journal-directory HANDLE. Native journal-directory `FileIdInfo`, DACL, reparse refusal, local fixed backing and owner checks are delegated to the existing retained native Windows guards and rechecked at scope exit. In contrast to POSIX read-only guard contracts, those existing Windows identity checks do not require the journal directory's timestamps to remain immutable during one explicitly expected creation.

Within the retained scope, the implementation refuses any pre-existing journal entries, verifies two native canonical exact-before registry and descriptor images, and rechecks the empty namespace and effective principal. At successful body exit it requires exactly one entry named for the proposed transaction; reads the new intent twice using the native protected Windows journal reader; compares both exact bytes to the canonical proposed intent; rechecks both metadata before-images; and repeats the namespace, owner and native handle protections before successful exit. A missing/extra file, bad native security, owner drift, inconsistent metadata or changed namespace refuses. Nothing is removed, retried, overwritten, replayed or authorized for commit; on failure the original evidence remains.

## Explicit limits

- **No durable admission:** Windows file write-through and `FlushFileBuffers` do not by themselves establish independently durable journal directory-entry persistence or atomicity across metadata files. The existing create-only provisioner remains a separate call and must be reviewed for write-through and failure behavior.
- **No distributed mutex:** two directory enumerations under local locks are not an atomic namespace snapshot against malicious same-user or external/cloud sync writers. Native handle continuity narrows but does not eliminate races. The result is *advisory candidate verification*, not a transaction-write token.
- **No metadata mutation:** the guard never replaces `registry.json`, workspace association, or any staged file; no durable transaction state machine or crash recovery is promoted. Neither an empty journal directory nor a matching intent proves the absence of orphan registry stages. Cross-filesystem moves remain prohibited.
- **No public storage:** `teacher_experience` capabilities and Notes storage remain unchanged. The Linux guard retains its separate 3F7 implementation. First binding/INITIALIZE remains refused.
- **Synthetic Windows tests:** tests simulate native guard/read behavior with mocks in a disposable local directory and cannot themselves prove real Windows ACL, Defender, directory flush or filesystem behavior. Windows qualification will run in the user's Core environment.

## Follow-through

The next integration milestone must coordinate the two platform-specific journal guards with the stage namespace, preserve exact-before state and all directory/handle guards, and implement explicit ambiguous-result crash recovery before any target compare-and-swap or public binding. Before promoting durable writes, native Windows fault injection (access denied, sharing violation, pending delete, reparse, interruption) and physical filesystem validation are required.
