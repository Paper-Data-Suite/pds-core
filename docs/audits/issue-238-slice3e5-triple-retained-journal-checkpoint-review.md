# Core #238 — Slice 3E5: triple-retained journal checkpoint review

**Basis:** feature branch `238-establish-private-teacher-workspace-storage` at `05cfacd9851f2435292997290dd1b7b89424ba50`; `main` `a0d5e1a50580bbe025f0cad23c7e8524203a52ec`.

## Scope

Add one **read-only, non-authorizing** internal composition, `review_retained_private_journal_checkpoint`, for **an existing** workspace descriptor/private registry and **one named existing** transaction. It composes Core #238 3E0 retained workspace descriptor, 3D7 retained registry and 3D5 retained journal-directory guards; the 3E4 native journal-image internal reader; 3C5 paired metadata snapshots; and 3E3 journal crash-checkpoint classification.

The function holds the existing *two ordered local locks and three native guards* throughout the read sequence and obtains the effective local OS principal twice. It **does not reacquire locks** by calling the public 3E4 reader. It instead invokes the already-reviewed internal native reader twice with all outer guards active. Both journal images must be canonical for the named UUID and effective OS owner, agree byte-for-byte, and survive their per-read native identity/permission checks. It obtains two registry and two descriptor snapshots; the pair must be internally stable and qualified. **Caller-supplied, untrusted** registry and descriptor image bytes are bounded, and their SHA-256 values must match the independently observed metadata snapshot digests before they can be passed to 3E3 for one of four *review-required* checkpoint outcomes. All failures map to sanitized refusal results without returning bytes, owner, UUID, paths, or handles.

`INITIALIZE` is refused by this route: an absent descriptor/private registry requires separate native absence and write-target qualification rather than a pretend existing handle. A missing journal cannot be promoted to an unjournaled transaction; this route is deliberately specific to a **present** named journal. A refusal raised on exit from any enclosing guard overrides an otherwise successful intermediate classification.

## Boundaries not solved

- The separately opened journal file is **not continuously retained across both reads**; content agreement is not continuous file-ID retention and does not exclude a malicious or non-cooperating replacement between reads. This is an **advisory observation only**.
- Registry and descriptor **image bytes are supplied by the caller**, and are compared to protected snapshots by digest; the function does **not** prove direct byte extraction from native handles, atomic multi-file snapshots, cryptographic collision resistance beyond the SHA-256 assumption, or consent.
- Existing local locks are cooperative; synced/network workspace participants cannot be coordinated. Retained directory/registry/descriptor handles do not make the cross-filesystem transaction atomic.
- The presence of bytes does **not** demonstrate a successfully flushed journal or durable directory entry. No journal admission, CAS reservation, metadata write, cleanup, recovery replay, journal retirement, or Notes record service is exposed.
- MacOS remains unqualified, as do native installed-wheel D2 security acceptance and full cross-platform CI. No public capabilities are added. Only `terminal.header.v1` and `terminal.notes_command.v1` remain advertised.
- Other journal directory entries are **not enumerated** by this one-journal review. A future global recovery census must not assume it establishes sole-pending-transaction status.

## Regression/qualification

Test the precise double journal-read ordering under all retained guards, all 3E3 journaled checkpoint categories, refused first and second native journal reads, journal bytes drift, registry/descriptor snapshot drift, OS principal drift, supplied image digest mismatch, refused classifier states, and entry/exit guard refusal. Synthetic isolated dependency-substitute suite: **31 tests passed**. That suite is **not** native Windows qualification.

The packaged Windows runner must guard exact repository, branch, origin, HEAD, remote heads and pinned files, use additive three-file scope, run focused pytest, Ruff, strict mypy, full pytest, `git diff --check`, and commit/push **only after** every gate passes. A failure leaves the checkout uncommitted for targeted repair.

## Remaining work

Native retained journal *file* identity across full recovery observation; qualified exact image provenance; complete pending-journal set review; durable journal admission and parent directory flush semantics, native exact-before CAS, crash-safe registry/descriptor metadata writes, replay/retirement, installed-wheel and native acceptance. No publication or activation authorized by this slice.
