# Core #238 — Slice 3G82: operation-boundary production precondition inventory

**Baseline:** `a6a61e8a492192214bef72489bd81ab08d25d08c`; draft PR #247. **Core version:** 0.6.6 candidate (not a new release).

## Scope and decision

Retain all nine production security requirements. Add a **parameterless, non-authorizing** operation-boundary inventory that combines the existing OS-owner/root observation (3G79), read-only retained native-root custody (3G80), Windows protected fixture evidence (3G81), and canonical synthetic-intent production write barrier. Do **not** elevate any standalone proof to production authority.

The new `review_private_operation_preconditions()` checks the exact nine requirements against the permanent production barrier **before native probes**. It observes the current preliminary root, invokes the existing production readiness check and native retained-root custody review, verifies the canonical synthetic intent still gets `production_blocked`, and compares initial and final private-root observations to refuse detectable drift. It returns sanitized enums and permanent `False` capability fields. No caller-controlled path, identity claim, guard, callback, intent, owner SID/UID, descriptor, journal, handle, lock, transaction or write capability is accepted or returned.

The initial/final observation comparison is **not a continuously held production guard**. Native custody obtained by 3G80 is released after its observation and **cannot** qualify the live two-root descriptor+registry+journal operation. No production-root creation, ACL repair, Notes CRUD, replay, journal retirement, lock or directory persistence is implemented. A positive result is still `production_blocked`.

## Acceptance

- Exact nine-item contract drift is refused before native probes.
- Read-only native owner/root observations and internally generated canonical intent return no production authority, including the synthetic positive retained-root case.
- Changing preliminary root between observations, unavailable owner, and canonical-intent/barrier mismatch all fail closed.
- No raw filesystem path, owner identifier or transaction bytes enter the review repr or installed-wheel JSON; no new teacher-experience capabilities are added.
- Both Linux and Windows: focused tests, Ruff, strict mypy, installed Core wheel isolated from checkout, the previous thirteen installed-wheel gates, and a fourteenth installed operation-preconditions gate. The shared wheel SHA is verified across all fourteen gates.
- Native Windows protected fixture remains an actual SID/DACL gate. Neither its scratch result nor this inventory grants READY/private store authorization.

## Next

3G83 must establish a **real operation-owned, continuously held two-root native scope** (private registry/journal and workspace descriptor), with canonical intent and exact identity/path rechecks while that scope is held. The 3G82 inventory is a read-only prerequisite map, never the guard itself; production writes remain disabled pending all nine qualifications.
