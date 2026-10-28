# Core #238 — Slice 3D3: native journal directory identity anchor

**Pinned parent:** `9da5d9b462bddfca1a7bad5d49e59167fb0612c3` (Slice 3D2).
**Authority:** approved #238 D0 design, `docs/teacher_private_storage_contract_v1.md` §5.
**Status:** internal, read-only, advisory, not a commit or journal-admission primitive.

## Problem and bounded implementation

Slice 3D2 already combines metadata-currentness and pending-journal review under both local locks. Its Windows directory census still uses path-based observations, and Linux evidence is not retained across later service calls. A writer must not infer native object continuity or mutation permission from the old advisory checks. Slice 3D3 adds a **separate native directory-identity observation** for the owner-private `transactions/` directory. This is an intentionally additive foundation for a future handle-retained writer; it does not change or strengthen the 3D2 review result itself.

`review_existing_native_journal_anchor(existing_private_root, existing_workspace_root)` validates candidate syntax, acquires the existing registry lock **before** the workspace lock using 3C9, samples native OS ownership, and inspects the exact owner-local `transactions/` directory. Locks are released when inspection ends. It neither creates files nor reads a journal entry. It does not return a file ID, path, SID, UID, descriptor or handle.

On **Linux**, a vetted no-follow FD walk through the existing owner-private ancestry retains the directory FD while its `fstat` identity is compared to repeated non-following pathname observations. Protection, ownership, effective ACL absence and known local filesystem backing are required by the shared verified-parent primitive. Directory replacement or changing identity is refused; root execution and unknown native behavior are refused.

On **Windows**, the existing native directory/DACL/volume preflight is followed by a non-following `CreateFileW` directory handle requesting only file-attribute and security-descriptor access. While that first handle remains open, Core opens the path a second time and compares `GetFileInformationByHandleEx(FileIdInfo=18)` volume serial + 128-bit file ID. It rechecks each opened handle's directory/reparse attributes, restrictive native DACL, qualified local volume and current native path walk. Both native handles close on all outcomes. A missing/unsupported file ID fails closed rather than substituting Python `stat` as evidence. The structure and selector follow Microsoft's `FILE_ID_INFO` and `GetFileInformationByHandleEx` contracts.

## What is still **not** proven

This is an **observation**, not a time-independent capability. The first handle is closed before return, and nothing prevents replacement after the observation. The two existing local locks do **not** serialize cloud writers or independent hostile processes. On Windows, ancestor handles from the existing native walk are not retained. The helper does not enumerate or verify transaction entries, prove absence of a pending journal, inspect exact registry/descriptor bytes, reserve a CAS transition, or authorize any mutation. Same-owner malicious code/privileged administrators are outside this trust model. No cross-tree atomicity or cloud synchronization guarantee is claimed.

The only positive outcome is `IDENTITY_OBSERVED_UNQUALIFIED`. All exceptional or unverified conditions use bounded, private-data-free refusal states. No public Notes API, `READY` state, `notes.records.v1`, Notes menu/CLI, or journal commit capability is introduced.

## Evidence and handoff

Tests assert native Linux fd identity on a non-root account, observed pathname replacement, synthetic Windows FileIdInfo layout and identity mismatch, DACL refusal, unqualified backing, native API absence, and exact handle closure on partial failure. Additional tests cover lock scope, owner drift, malformed input, unsupported platforms and unchanged teacher capabilities. An isolated non-root Linux harness reported 16 passed; installed Windows/native Core qualification is a distinct gate.

Future journal admission must integrate directory enumeration **using a retained qualified native handle**, exact protected registry and workspace before-byte CAS under the complete lock set, pending-intent detection, crash-safe durable journal creation, explicit teacher-confirmed plan verification, and a documented recovery protocol. This slice does not expose a write-capable handle or combine these checks into authority.
