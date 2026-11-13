# Core #238 Slice 3E9 — Guarded intent-candidate creation

## Scope

This is the first **composed write** after the read-only 3E1–3E8 qualification sequence. It is intentionally restricted to **exclusive creation of a single immutable transaction-intent candidate** for an already-existing private registry and workspace descriptor during an explicitly invoked internal operation. It calls the previously introduced native create-only journal primitive only after the complete guarded preflight. It does **not** write either metadata document, initialize an unbound workspace, resolve a collection, grant a token, retire a journal, repair a crash, or expose a Notes capability.

## Guarded ordering

1. Require Linux or Windows and validate the caller's current private-root/workspace-root syntax, exact intent type, canonical encoding, and a non-initialization transition.
2. Hold the existing triple-retained descriptor guard, which owns the ordered local locks and native journal-directory, registry and descriptor anchors throughout this operation. Read the effective OS principal.
3. Verify the protected journal directory and perform an empty **native** journal census. Any existing entry, invalid directory, unsupported protection, or changed census refuses creation; nothing is cleaned up.
4. Read the protected registry and the untrusted workspace descriptor with the internal no-reacquisition native readers; repeat both reads in reverse order. Require canonical qualified images, byte-for-byte stability, and exact equality with the validated intent's **before-images**. A SHA-only match is insufficient.
5. Recheck the effective owner and repeat the empty journal census immediately before requesting creation.
6. Invoke `create_private_transaction_intent_file` exactly once. This helper uses exclusive creation of a protected journal candidate and applies its platform-specific file flush and native protection checks. Refuse collisions and ambiguous creation results.
7. Re-read the created named journal **twice**, requiring native validation and exact equality with the intended canonical bytes. Recheck the principal before leaving the guard. A retained-guard exit failure overrides the candidate result.

No public reader is called from a retained-lock scope: those methods would attempt recursive locking.

## Deliberately unqualified properties

- `CREATED_UNQUALIFIED` means a protected candidate was observed, **not** a durably admitted or committed transaction, writable reservation, or authorization for metadata mutation. A Windows `FlushFileBuffers` on a file does **not** establish unconditional directory-entry durability.
- The local guards do not coordinate with remote/cloud/sync actors, malicious same-user processes, or unrelated machines. File replacement is checked only at bounded native observations; no cross-filesystem atomic transaction is claimed.
- A candidate may persist if the create primitive, post-create reread, owner check, retained guard exit or process fails. **Never retry blindly, truncate, overwrite, or delete it.** A later explicit recovery review must first classify every pending entry.
- There are no Notes records, student links, private collection handles, public service dispatch, or storage capabilities in this slice.
- `INITIALIZE` remains excluded because a missing descriptor/registry requires a different guarded absence and bootstrap protocol.

## Regression and qualification

Synthetic regression cases cover first and second journal census refusal, four protected metadata read failures, four changed observations, foreign before-images, exclusive-create collision and ambiguous creation, two post-create read failures, post-create image drift, owner changes before and after creation, retained-guard entry and exit failure, explicit initialization exclusion, malformed requests, unsupported platforms, sanitized messages, and capability boundaries. The isolated substitute-dependency harness passed 33 tests. It is **not** native Core qualification.

The guarded Windows runner must verify the exact 3E8 source and remote baseline, one three-file additive scope, focused pytest, Ruff lint/format, strict mypy, full Core pytest, and Git hygiene **before** committing and pushing. Native Windows and Linux fault-injection, directory durability, CAS write-target continuity, metadata commit ordering, transaction replay/retirement and installed wheel acceptance remain separate, unqualified work.
