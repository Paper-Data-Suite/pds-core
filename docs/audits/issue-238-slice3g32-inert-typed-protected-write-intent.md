# Core #238 — Slice 3G32: Inert typed protected write-intent description

**Baseline:** qualified 3G31 commit `a781450b81034021f142ca9700330f8bd6e08616`.

## Objective

Introduce a typed, bounded description of the proposed **prepared stage-to-registry**
transition, grounded in the existing canonical `PrivateTransactionIntent` bytes.
This makes the prospective write boundary explicit without building a callable
writer, accepting a production filesystem path, exporting an FD/HANDLE, passing
a callback, or turning 3G30's *released* read-only scope into authorization.

## Public contract within the private module

`describe_private_prepared_stage_write_intent(step, expected_revision, proposed)`
accepts only the exact `PrivateScratchWriterStep`, exact positive integer revision,
and exact `PrivateTransactionIntent` type. It refuses initialize, descriptor
completion, and journal retirement before serialization. It obtains the existing
canonical encoder/decoder's exact round trip and rejects noncanonical or
inconsistent bytes. Only existing `REBIND_MOVE` and `FORK_COPY` witnesses may
be described; first binding is explicitly refused. The preceding revision
must be positive and the successor revision exactly one greater.

For a matching canonical prepared image it returns a `PrivatePreparedWriteDescription`
wrapped in a sanitized `PrivatePreparedWriteIntentReview`. That frozen, slot-based
and redacted description carries only: the typed step and binding kind, expected
and resulting revisions, internal transaction identifier, and SHA-256 fingerprints
of the canonical pending journal, before registry, staged after registry, and
before/after descriptor images. It never carries the original bytes or locations.
The transaction identifier and fingerprints are hidden from `repr`.

Every refused state has a `None` description. A successful description is **plain
forgeable metadata**, not a trustworthy origin or a write capability. The
producer performs no native IO and cannot prove that a matching journal, stage,
registry, descriptor, OS owner, restrictive DACL, protected backing volume,
lock, or retained HANDLE exists or remains current.

## Acceptance and testing

- Exact input type and operation refusal before encoding.
- Existing canonical encode/decode/encode roundtrip; strict bytes, size, witness,
  image-presence, revision, and digest validation.
- No path, payload, callback, handle, lock, guard, token, or mutating method.
- Independent malformed image, stale revision, tampered witness, invalid
  serialization, interruption and unexpected-exception refusal cases.
- Frozen, non-executable, redactable descriptions (including explicit test that
  a copied/altered description is forgeable and therefore never authorization).
- Windows qualification: focused Core #238 suite, Ruff and strict mypy before
  commit/push; previous periodic full Core checkpoint at 3G30: 6,191 passed,
  176 skipped. Full suite not repeated for this narrowly scoped additive slice.

## Required follow-on work

3G33 must keep the protected native guard **owned by the operation**, independently
rechecking the complete canonical transaction and write-description fingerprints
at the last pre-operation boundary. It must not accept a previously released
3G30 review or this description as a permit. Any mutating path requires separate
qualification for native identity/owner/ACL custody, atomic replacement and
postimage checks, error recovery, durable directory/file persistence, safe
journal retirement and hostile/noncooperating-writer limitations.

**No production registry/descriptor mutation, durable commit, journal retirement,
new initial binding, or Notes activation is authorized by 3G32.**
